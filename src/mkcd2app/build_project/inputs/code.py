import logging
import shutil
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image
from bs4 import BeautifulSoup
from redun import task
from redun.file import ContentDir, ContentFile

from mkcd2app.config import load_config_from_yaml
from mkcd2app.config.model import GitHubCodeSource, PathAssetSource, PathCodeSource, \
    ShareLinkCodeSource, \
    UrlAssetSource
from mkcd2app.utils.logger import create_logger
from mkcd2app.utils.run import run_cmd

logger = create_logger(name=__name__, level=logging.INFO)


@task(namespace="mkcd2app")
def fetch_code(config_yaml: str, node_modules_for_mkc: ContentDir) -> ContentDir:
    """
    Download/clone/copy the source code to the build directory.

    Example input: config_yaml, ./node_modules
    Example output: ./racers-source

    :param config_yaml: The raw YAML text of the config file.
    :param node_modules_for_mkc: redun.ContentDir that points to the node_modules
     directory, this ensures that this task depends on `mkc` being installed.
    :return: A redun.ContentDir that points to the source code.
    """
    config = load_config_from_yaml(config_yaml)
    code_path = Path(config.build_dir) / f"{config.project.path_friendly_name}-source"
    logger.info(f"MakeCode Arcade source will be downloaded/copied to {code_path}")

    # Clean previous output, not wasteful because redun already checks our inputs
    # and outputs to see if they changed
    if code_path.exists():
        shutil.rmtree(code_path)

    # TODO: Implement source code download from GitHub
    # TODO: Implement source code copy
    match config.inputs.code.root:
        case ShareLinkCodeSource(value=url):
            logger.debug(f"Downloading source code from {url}")
            code_path.mkdir(parents=True)
            logger.debug(f"Using `mkc` from {node_modules_for_mkc}")
            run_cmd(["npx", "mkc", "download", str(url)], cwd=code_path)
        case GitHubCodeSource(value=url, checkout=checkout_target):
            logger.debug(f"Downloading source code from {url}@{checkout_target}")
        case PathCodeSource(value=path):
            logger.debug(f"Copying source code from {path}")

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
    run_cmd(["npx", "mkc", "build", "-j"], cwd=cwd)

    bin_js_path = cwd / "built" / "binary.js"
    logger.debug(f"binary.js available at {bin_js_path}")

    # Copy binary to a stable location outside code_dir so we don't
    # pollute fetch_code's ContentDir hash on subsequent runs.
    output_path = cwd.parent / f"{config.project.path_friendly_name}-binary-js" / "binary.js"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(bin_js_path, output_path)
    shutil.rmtree(cwd / "built")

    return ContentFile(str(output_path))


@task(namespace="mkcd2app")
def download_and_mod_supporting_files(config_yaml: str) -> ContentDir:
    """
    Download and modify all supporting files needed to run binary.js for the website

    Example input: config_yaml
    Example output: ./racers-binary-js-support

    :param config_yaml: The raw YAML text of the config file.
    :return: redun.ContentDir that points to a directory of files that should be copied
     to the website's public folder as is alongside the binary.js file.
    """
    config = load_config_from_yaml(config_yaml)
    support_path = Path(
        config.build_dir) / f"{config.project.path_friendly_name}-binary-js-support"
    logger.info(f"Downloading supporting files to {support_path}")

    # Clean previous output, not wasteful because redun handles caching
    if support_path.exists():
        shutil.rmtree(support_path)
    support_path.mkdir(parents=True)

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
            style_tag = soup.new_tag("style")
            style_tag.string = res.text
            css.replace_with(style_tag)
            logger.debug(f"Inlined CSS from {url}")
    for js in js_scripts:
        url = js.get("src")
        if url:
            logger.debug(f"Downloading JS file {url}")
            res = requests.get(url)
            res.raise_for_status()
            js.string = res.text
            del js["src"]
            logger.debug(f"Inlined JS from {url}")
    new_sim_html = soup.prettify(formatter="html5")
    path = support_path / "---simulator.html"
    path.write_text(new_sim_html)
    logger.debug(f"Wrote modified simulator HTML to {path}")

    if config.inputs.assets.icon:
        match config.inputs.assets.icon.root:
            case UrlAssetSource(value=url):
                logger.debug(f"Downloading icon from {url}")
                res = requests.get(str(url))
                res.raise_for_status()
                buffer = BytesIO(res.content)
                im = Image.open(buffer)
            case PathAssetSource(value=path):
                logger.debug(f"Opening icon from {path}")
                im = Image.open(path)
        favicon_path = support_path / "favicon.ico"
        logger.debug(f"Saving favicon to {favicon_path}")
        im.save(favicon_path)

    return ContentDir(str(support_path))
