import json
import logging
import shutil
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory

import requests
from bs4 import BeautifulSoup
from redun import task
from redun.file import ContentDir, ContentFile

from mkcd2app.models.metadata import BinaryJSMetadata
from mkcd2app.utils.logger import create_logger
from mkcd2app.utils.paths import (
    get_js_tools_bin_dir,
    get_sim_html_path,
)
from mkcd2app.utils.resources import get_resource_empty_project_path
from mkcd2app.utils.run import run_cmd
from mkcd2app.utils.text import extract_meta_comment

logger = create_logger(name=__name__, level=logging.INFO)


@task(namespace="mkcd2app")
def warm_mkc_cache_for_version_and_get_binary_js_metadata(
    empty_prj: ContentDir, version: str
) -> str:
    """
    Warm the mkc compiler cache by building an empty project for the target MakeCode
    Arcade version in a temporary directory.

    :param empty_prj: The ContentDir pointing to the directory containing the empty
     MakeCode Arcade project.
    :param version: The MakeCode Arcade version to target. E.g., "4.0.14". Must be
     explicit 3 num sem ver, not just like "4.0" or "4", and do not include a "v".
    :return: A BinaryJSMetadata model dumped to a JSON string.
    """
    logger.info(f"Warming mkc compiler cache for MakeCode Arcade version {version}")

    empty_prj_path = Path(empty_prj.path)

    with TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)

        logger.debug(f"Copying {empty_prj_path} to {tmp_dir_path}")
        shutil.copytree(empty_prj_path, tmp_dir_path, dirs_exist_ok=True)

        mkc_json_path = tmp_dir_path / "mkc.json"
        logger.debug("Writing mkc.json")
        mkc_json = {"targetWebsite": f"https://arcade.makecode.com/v{version}"}
        mkc_json_path.write_text(json.dumps(mkc_json))

        logger.debug("Running build to warm cache")
        run_cmd(
            ["mkc", "build", "-j"], cwd=tmp_dir_path, which_path=get_js_tools_bin_dir()
        )

        binary_js_path = tmp_dir_path / "built" / "binary.js"
        logger.debug(f"binary.js available at {binary_js_path}")

        logger.debug("Finished mkc cache warming, extracting binary.js metadata")
        metadata = extract_meta_comment(binary_js_path)
        logger.debug(f"{metadata=}")
        return metadata.model_dump_json()


@task(namespace="mkcd2app")
def download_sim(bin_js_metadata: str, version: str) -> ContentFile:
    """
    Download the simulator HTML and the supporting files needed to run binary.js for the
    website.

    :param bin_js_metadata: The binary JS metadata JSON as a string.
    :param version: The MakeCode Arcade version to target. E.g., "4.0.14". Must be
     explicit 3 num sem ver, not just like "4.0" or "4", and do not include a "v".
    :return: A ContentFile that points to the ---simulator.html.
    """
    metadata = BinaryJSMetadata.model_validate_json(bin_js_metadata)
    logger.info(
        f"Downloading simulator for MakeCode Arcade version {metadata.targetVersion}"
    )

    logger.debug(f"Downloading main simulator file from {metadata.simUrl}")
    res = requests.get(str(metadata.simUrl))
    res.raise_for_status()
    sim_html = res.text

    logger.debug(
        f"Analyzing sim HTML ({len(sim_html)} chars) for required CSS and JS files"
    )
    soup = BeautifulSoup(sim_html, features="html.parser")
    css_links = soup.find_all("link", rel="stylesheet")
    js_scripts = soup.find_all("script")
    logger.debug(f"Found {len(css_links)} CSS links and {len(js_scripts)} JS scripts")
    for css in css_links:
        url = css.get("href")
        if url:
            logger.debug(f"Downloading CSS file {url}")
            res = requests.get(str(url))
            res.raise_for_status()
            style_tag = soup.new_tag("style")
            style_tag.string = res.text
            css.replace_with(style_tag)
            logger.debug(f"Inlined CSS from {url}")
    for js in js_scripts:
        url = js.get("src")
        if url:
            logger.debug(f"Downloading JS file {url}")
            res = requests.get(str(url))
            res.raise_for_status()
            js.string = res.text
            del js["src"]
            logger.debug(f"Inlined JS from {url}")
    new_sim_html = soup.prettify(formatter="html5")

    path = get_sim_html_path(version)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_sim_html)

    logger.debug(f"Wrote simulator HTML to {path}")

    return ContentFile(str(path))


@task(namespace="mkcd2app")
def install_target(version: str) -> ContentFile:
    """
    Install a MakeCode Arcade target version for this mkcd2app version.

    :param version: The MakeCode Arcade version to target. E.g., "4.0.14". Must be
     explicit 3 num sem ver, not just like "4.0" or "4", and do not include a "v".
    :return: A ContentFile that points to the ---simulator.html for the installed version.
    """
    logger.info(f"Installing MakeCode Arcade target version {version}")

    with ExitStack() as stack:
        empty_prj_path = stack.enter_context(get_resource_empty_project_path())

        # `mkc build -j` an empty project with the correct version
        metadata = warm_mkc_cache_for_version_and_get_binary_js_metadata(
            ContentDir(str(empty_prj_path)), version
        )
        # Download ---simulator.html and supporting files, mod into single HTML file
        sim_html = download_sim(metadata, version)

        return sim_html
