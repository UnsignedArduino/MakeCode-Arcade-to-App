import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from redun import task
from redun.file import ContentDir, ContentFile

from mkcd2app.config import BuildConfig
from mkcd2app.config.model import GitHubCodeSource, PathCodeSource, ShareLinkCodeSource
from mkcd2app.utils.logger import create_logger
from mkcd2app.utils.run import run_cmd

logger = create_logger(name=__name__, level=logging.INFO)


@task(namespace="mkcd2app")
def fetch_code(config: BuildConfig, node_modules_for_mkc: ContentDir) -> ContentDir:
    """
    Download/clone/copy the source code to the build directory.

    :param config: App build configuration
    :param node_modules_for_mkc: redun.ContentDir that points to the node_modules
     directory, this ensures that this task depends on `mkc` being installed.
    :return: A redun.ContentDir that points to the source code.
    """
    code_path = Path(config.build_dir) / f"{config.project.path_friendly_name}-source"
    logger.info(f"MakeCode Arcade source will be downloaded/copied to {code_path}")

    # TODO: Implement source code download from GitHub
    # TODO: Implement source code copy
    match config.inputs.code.root:
        case ShareLinkCodeSource(value=url):
            logger.debug(f"Downloading source code from {url}")
            code_path.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Using `mkc` from {node_modules_for_mkc}")
            run_cmd(f"npx mkc download {url}", cwd=code_path)
        case GitHubCodeSource(value=url, checkout=checkout_target):
            logger.debug(f"Downloading source code from {url}@{checkout_target}")
        case PathCodeSource(value=path):
            logger.debug(f"Copying source code from {path}")

    logger.debug("Source code downloaded")
    # TODO: Figure out why the cache keeps busting with fetch_code specifically
    return ContentDir(str(code_path))


@task(namespace="mkcd2app")
def build_binary_js(code_dir: ContentDir) -> ContentFile:
    """
    Build the MakeCode Arcade binary.js file

    :param code_dir: A redun.ContentDir where the code is stored.
    :return: A redun.ContentFile that points to binary.js
    """
    logger.info("Building MakeCode Arcade binary.js")

    cwd = Path(code_dir.path)
    logger.debug(f"Building in cwd {cwd}")
    run_cmd("npx mkc build -j", cwd=cwd)

    bin_js_path = cwd / "built" / "binary.js"
    logger.debug(f"binary.js available at {bin_js_path}")

    return ContentFile(str(bin_js_path))


@task(namespace="mkcd2app")
def download_supporting_files(config: BuildConfig) -> ContentDir:
    """
    Download all supporting files needed to run binary.js for the website

    :param config: App build configuration
    :return: redun.ContentDir that points to a directory of files that should be copied
     to the website's public folder as is alongside the binary.js file.
    """
    support_path = Path(
        config.build_dir) / f"{config.project.path_friendly_name}-binary-js-support"
    logger.info(f"Downloading supporting files to {support_path}")
    support_path.mkdir(parents=True, exist_ok=True)

    logger.debug(f"Downloading main simulator file")
    res = requests.get("https://trg-arcade.userpxt.io/---simulator")
    res.raise_for_status()
    sim_html = res.text

    logger.debug(f"Analyzing sim HTML ({len(sim_html)} chars) for required CSS and JS "
                 f"files")
    soup = BeautifulSoup(sim_html, features="html.parser")
    css_links = soup.find_all("link", rel="stylesheet")
    js_scripts = soup.find_all("script")
    logger.debug(f"Found {len(css_links)} CSS links and {len(js_scripts)} JS scripts")
    for css in css_links:
        url = css.get("href")
        if url:
            logger.debug(f"Downloading CSS file {url}")
            res = requests.get(url)
            res.raise_for_status()
            file_name = url.split("/")[-1]
            path = support_path / file_name
            path.write_text(res.text)
            css["href"] = f"./{file_name}"
            logger.debug(f"Wrote to {path}")
    for js in js_scripts:
        url = js.get("src")
        if url:
            logger.debug(f"Downloading JS file {url}")
            res = requests.get(url)
            res.raise_for_status()
            file_name = url.split("/")[-1]
            path = support_path / file_name
            path.write_text(res.text)
            js["src"] = f"./{file_name}"
            logger.debug(f"Wrote to {path}")
    new_sim_html = soup.prettify(formatter="html5")
    path = support_path / "---simulator.html"
    path.write_text(new_sim_html)
    logger.debug(f"Wrote modified simulator HTML to {path}")

    # TODO: Get specified icon in config.project.icon and download it to the
    #  support_path

    return ContentDir(str(support_path))
