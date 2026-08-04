import logging
import shutil
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image
from redun import task
from redun.file import ContentDir, ContentFile

from mkcd2app.config import load_config_from_yaml
from mkcd2app.models.config import (
    GitHubCodeSource,
    PathAssetSource,
    PathCodeSource,
    ShareLinkCodeSource,
    UrlAssetSource,
)
from mkcd2app.utils.filesystem import rmtree_robust
from mkcd2app.utils.logger import create_logger
from mkcd2app.utils.paths import get_js_tools_bin_dir, get_sim_html_path
from mkcd2app.utils.run import run_cmd

logger = create_logger(name=__name__, level=logging.INFO)


@task(namespace="mkcd2app")
def fetch_code(config_yaml: str) -> ContentDir:
    """
    Download/clone/copy the source code to the build directory.

    Example input: config_yaml, ./node_modules
    Example output: ./racers-source

    :param config_yaml: The raw YAML text of the config file.
    :return: A redun.ContentDir that points to the source code.
    """
    config = load_config_from_yaml(config_yaml)
    code_path = Path(config.build_dir) / f"{config.project.path_friendly_name}-source"
    logger.info(f"MakeCode Arcade source will be downloaded/copied to {code_path}")

    # Clean previous output, not wasteful because redun already checks our inputs
    # and outputs to see if they changed
    if code_path.exists():
        rmtree_robust(code_path)

    match config.inputs.code.root:
        case ShareLinkCodeSource(value=url):
            logger.debug(f"Downloading source code from {url} with `mkc` CLI")
            code_path.mkdir(parents=True)
            run_cmd(
                ["mkc", "download", str(url)],
                cwd=code_path,
                which_path=get_js_tools_bin_dir(),
            )
        case GitHubCodeSource(value=url, checkout=checkout_target):
            logger.debug(f"Cloning source code from {url}@{checkout_target}")
            abs_code_path = code_path.resolve()
            abs_code_path.parent.mkdir(parents=True, exist_ok=True)
            run_cmd(
                [
                    "git",
                    "clone",
                    "--filter=blob:none",
                    "--no-checkout",
                    str(url),
                    str(abs_code_path),
                ],
                cwd=abs_code_path.parent,
            )
            run_cmd(["git", "checkout", checkout_target], cwd=abs_code_path)
        case PathCodeSource(value=path):
            logger.debug(f"Copying source code from {path}")
            shutil.copytree(path, code_path)

    logger.debug("Source code downloaded")
    return ContentDir(str(code_path))


@task(namespace="mkcd2app")
def build_binary_js(config_yaml: str, code_path: ContentDir) -> ContentFile:
    """
    Build the MakeCode Arcade binary.js file

    Example input: config_yaml, ./racers-source
    Example output: ./racers-binary-js/binary.js

    :param config_yaml: The raw YAML text of the config file.
    :param code_path: A redun.ContentDir where the code is stored.
    :return: A redun.ContentFile that points to binary.js
    """
    config = load_config_from_yaml(config_yaml)

    logger.info("Building MakeCode Arcade binary.js")

    cwd = Path(code_path.path)
    logger.debug(f"Building in cwd {cwd}")
    run_cmd(
        ["mkc", "build", "-j"],
        cwd=cwd,
        which_path=get_js_tools_bin_dir(),
    )

    bin_js_path = cwd / "built" / "binary.js"
    logger.debug(f"binary.js available at {bin_js_path}")

    # Copy binary to a stable location outside code_dir so we don't
    # pollute fetch_code's ContentDir hash on subsequent runs.
    output_path = (
        cwd.parent / f"{config.project.path_friendly_name}-binary-js" / "binary.js"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(bin_js_path, output_path)
    shutil.rmtree(cwd / "built")

    return ContentFile(str(output_path))


@task(namespace="mkcd2app")
def copy_support_files(config_yaml: str) -> ContentDir:
    """
    Download and modify all supporting files needed to run binary.js for the website

    Example input: config_yaml
    Example output: ./racers-binary-js-support

    :param config_yaml: The raw YAML text of the config file.
    :return: redun.ContentDir that points to a directory of files that should be copied
     to the website's public folder as is alongside the binary.js file.
    """
    config = load_config_from_yaml(config_yaml)
    support_path = (
        Path(config.build_dir)
        / f"{config.project.path_friendly_name}-binary-js-support"
    )
    target = config.target
    logger.info(
        f"Copying ---simulator.html for MakeCode Arcade {target} to {support_path}"
    )

    # Clean previous output, not wasteful because redun handles caching
    if support_path.exists():
        shutil.rmtree(support_path)
    support_path.mkdir(parents=True)
    # Only one file to copy
    shutil.copy(get_sim_html_path(target), support_path)

    if config.inputs.assets.icon:
        match config.inputs.assets.icon.root:
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
