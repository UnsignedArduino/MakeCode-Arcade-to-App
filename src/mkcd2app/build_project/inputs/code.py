import json
import logging
import shutil
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image
from redun import task
from redun.file import ContentDir, ContentFile

from mkcd2app.build_project.inputs.embedded_source import extract_project
from mkcd2app.models.config import (
    AssetSource,
    CodeSource,
    FileCodeSource,
    GitCodeSource,
    GitHubCodeSource,
    PathAssetSource,
    PathCodeSource,
    ShareLinkCodeSource,
    UrlAssetSource,
)
from mkcd2app.utils.filesystem import rmtree_robust
from mkcd2app.utils.git import clone_and_checkout
from mkcd2app.utils.logger import create_logger
from mkcd2app.utils.paths import get_js_tools_bin_dir, get_sim_html_path
from mkcd2app.utils.run import run_cmd

logger = create_logger(name=__name__, level=logging.INFO)


def _warn_on_target_mismatch(pxt_json_path: Path, target: str) -> None:
    """Warn if the project was saved with a different Arcade version than target."""
    try:
        pxt_json = json.loads(pxt_json_path.read_text(encoding="utf-8"))
        saved = pxt_json["targetVersions"]["target"]
    except OSError, ValueError, KeyError, TypeError:
        logger.debug(f"Could not read targetVersions.target from {pxt_json_path}")
        return
    if saved != target:
        logger.warning(
            f"Project was saved with Arcade {saved}, building against {target}"
        )


@task(namespace="mkcd2app")
def fetch_code(code_source_json: str, target: str, code_dir: str) -> ContentDir:
    """
    Download/clone/copy the source code to the build directory.

    Example input: code_source_json, 4.0.14, ./racers-source
    Example output: ./racers-source

    :param code_source_json: The config's CodeSource dumped to a JSON string.
    :param target: The MakeCode Arcade version to target. E.g., "4.0.14".
    :param code_dir: The directory to put the source code in.
    :return: A redun.ContentDir that points to the source code.
    """
    code_path = Path(code_dir)
    logger.info(f"MakeCode Arcade source will be downloaded/copied to {code_path}")

    # Clean previous output, not wasteful because redun already checks our inputs
    # and outputs to see if they changed
    if code_path.exists():
        rmtree_robust(code_path)

    match CodeSource.model_validate_json(code_source_json).root:
        case ShareLinkCodeSource(value=url):
            logger.debug(f"Downloading source code from {url} with `mkc` CLI")
            code_path.mkdir(parents=True)
            run_cmd(
                ["mkc", "download", str(url)],
                cwd=code_path,
                which_path=get_js_tools_bin_dir(),
            )
        case (
            GitCodeSource(url=url, ref=ref) | GitHubCodeSource(value=url, checkout=ref)
        ):
            logger.debug(f"Cloning source code from {url}@{ref or 'default branch'}")
            code_path.parent.mkdir(parents=True, exist_ok=True)
            clone_and_checkout(str(url), code_path, ref)
        case PathCodeSource(value=path):
            logger.debug(f"Copying source code from {path}")
            shutil.copytree(path, code_path)
        case FileCodeSource(value=path):
            logger.debug(f"Extracting project from {path}")
            src_file = Path(path)
            if not src_file.is_file():
                raise FileNotFoundError(f"Code source file not found: {src_file}")
            # Raises EmbeddedSourceError (with the file path) if there's no project
            files = extract_project(src_file, code_path)
            logger.debug(f"Extracted {len(files)} files: {', '.join(files)}")
            _warn_on_target_mismatch(code_path / "pxt.json", target)

    mkc_json_path = code_path / "mkc.json"
    logger.debug("Writing mkc.json")
    mkc_json = {"targetWebsite": f"https://arcade.makecode.com/v{target}"}
    mkc_json_path.write_text(json.dumps(mkc_json), encoding="utf-8")

    logger.debug("Source code downloaded")
    return ContentDir(str(code_path))


@task(namespace="mkcd2app")
def build_binary_js(code_path: ContentDir, build_dir: str) -> ContentFile:
    """
    Make a copy of the source code, then build the MakeCode Arcade binary.js file in it.

    We copy so that we never mutate the ContentDir that fetch_code owns.

    Example input: ./racers-source, ./racers-binary-js-build
    Example output: ./racers-binary-js-build/built/binary.js

    :param code_path: A redun.ContentDir where the code is stored.
    :param build_dir: The directory to copy the source code to and build in.
    :return: A redun.ContentFile that points to binary.js
    """
    logger.info("Building MakeCode Arcade binary.js")

    cwd = Path(build_dir)
    # Robust because a git code source's copy has a .git directory
    if cwd.exists():
        rmtree_robust(cwd)
    shutil.copytree(code_path.path, cwd)

    logger.debug(f"Building in cwd {cwd}")
    run_cmd(
        ["mkc", "build", "-j"],
        cwd=cwd,
        which_path=get_js_tools_bin_dir(),
    )

    bin_js_path = cwd / "built" / "binary.js"
    logger.debug(f"binary.js available at {bin_js_path}")

    return ContentFile(str(bin_js_path))


@task(namespace="mkcd2app")
def copy_support_files(
    target: str, icon_source_json: str | None, support_dir: str
) -> ContentDir:
    """
    Download and modify all supporting files needed to run binary.js for the website

    Example input: 4.0.14, icon_source_json, ./racers-binary-js-support
    Example output: ./racers-binary-js-support

    :param target: The MakeCode Arcade version to target. E.g., "4.0.14".
    :param icon_source_json: The config's icon AssetSource dumped to a JSON string, or
     None if there is no icon.
    :param support_dir: The directory to put the files in.
    :return: redun.ContentDir that points to a directory of files that should be copied
     to the website's public folder as is alongside the binary.js file.
    """
    support_path = Path(support_dir)
    logger.info(
        f"Copying ---simulator.html for MakeCode Arcade {target} to {support_path}"
    )

    # Clean previous output, not wasteful because redun handles caching
    if support_path.exists():
        shutil.rmtree(support_path)
    support_path.mkdir(parents=True)
    # Only one file to copy
    shutil.copy(get_sim_html_path(target), support_path)

    if icon_source_json is not None:
        match AssetSource.model_validate_json(icon_source_json).root:
            case UrlAssetSource(value=icon_url):
                logger.debug(f"Downloading icon from {icon_url}")
                res = requests.get(str(icon_url))
                res.raise_for_status()
                buffer = BytesIO(res.content)
                im = Image.open(buffer)
            case PathAssetSource(value=icon_path):
                logger.debug(f"Opening icon from {icon_path}")
                im = Image.open(icon_path)
        favicon_path = support_path / "favicon.ico"
        logger.debug(f"Saving favicon to {favicon_path}")
        im.save(favicon_path)

    return ContentDir(str(support_path))
