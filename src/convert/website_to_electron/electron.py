import json
import logging
import shutil
from io import BytesIO
from pathlib import Path
from typing import Callable

import requests
from PIL import Image

from convert.mkcd_to_website.config import Config, IconSourceType, SourceType
from utils.cmd import run_shell_command
from utils.filesystem import copy_these, delete_these
from utils.logger import create_logger

logger = create_logger(name=__name__, level=logging.INFO)


def get_icon(config: Config, src_dir: Path):
    """
    Prepares the icon for the Electron app. If the icon is a URL, it downloads the icon
    and saves it to the specified path. If the icon is a local file, it copies the file
    to the specified path. Then it will convert it to ICO for Windows, ICNS for Mac, and
    PNG for Linux.

    :param config: The configuration object containing the project information.
    :param src_dir: The src directory of the Electron app - the icon will be saved here.
    """
    if config.icon is None:
        logger.debug("No icon specified, skipping icon generation.")
        return
    logger.debug(f"Preparing icon")
    icon_dir = src_dir / "assets" / "icons"
    icon_dir.mkdir(parents=True, exist_ok=True)
    if config.icon_source_type == IconSourceType.PATH:
        path = Path(config.icon)
        source_icon_path = icon_dir / f"source{path.suffix}"
        logger.debug(f"Copying icon from {path} to {source_icon_path}")
        shutil.copy(path, source_icon_path)
    else:
        url = config.icon
        logger.debug(f"Downloading icon from {url}")
        res = requests.get(url)
        if not res.ok:
            logger.error(f"Failed to download icon from {url}")
            raise Exception(f"Failed to download icon from {url}")
        buffer = BytesIO(res.content)
        logger.debug(
            f"Downloaded image size {round(buffer.getbuffer().nbytes / 1024)} kb")
        img = Image.open(buffer)
        source_icon_path = icon_dir / f"source.png"
        img.save(source_icon_path)
        logger.debug(f"Saved icon to {source_icon_path}")

    formats = ["ico", "icns", "png"]
    source_img = Image.open(source_icon_path)
    for format in formats:
        icon_path = icon_dir / f"icon.{format}"
        logger.debug(f"Converting icon to {format} and saving to {icon_path}")
        source_img.save(icon_path, format=format.upper(),
                        sizes=[(256, 256)] if format == "ico" else None)


def generate_electron(config: Config, prj_name: str, template_dir: Path, dist_dir: Path,
                      cwd: Path):
    """
    Generate the Electron app from static HTML, CSS, and JS files. Assumes index.html
    is the entry point.

    :param config: The configuration object containing the project information.
    :param prj_name: The name of the project.
    :param template_dir: The directory containing the template files.
    :param dist_dir: The dist directory with all the static HTML, CSS, and JS files.
    :param cwd: The current working directory where the project will be created.
    """
    logger.debug(f"Creating Electron app for {prj_name}")
    # Initialize an Electron project
    prj_dir = cwd / prj_name
    prj_src_dir = prj_dir / "src"
    if prj_dir.exists():
        logger.debug(f"Project {prj_name} already exists, continuing...")
    else:
        run_shell_command(
            f"npx --yes create-electron-app@latest {prj_name} --template=webpack",
            cwd=cwd)
    delete_these(["package-lock.json"], prj_dir)
    delete_these(["index.html", "index.css"], prj_src_dir)
    # Start copying files from template
    old_dir = template_dir
    new_dir = prj_dir

    def copy_template(file_name: str, callback: Callable[[str], str] = lambda x: x):
        (new_dir / file_name).write_text(callback((old_dir / file_name).read_text()))

    logger.debug(f"Copying website files from {old_dir} to {new_dir}")
    # Modify package.json
    package_json = json.loads((old_dir / "package.json").read_text())
    package_json["name"] = prj_name
    package_json["productName"] = prj_name
    package_json["version"] = config.version
    package_json["description"] = config.description
    package_json["author"] = config.author
    (new_dir / "package.json").write_text(json.dumps(package_json, indent=2))
    # Copy README.md
    copy_template("README.md",
                  lambda x: x.format(WEBSITE_NAME=prj_name,
                                     SOURCE=f"{config.source} @ {config.source_checkout}" if config.source_type == SourceType.GITHUB else config.source))
    # Copy forge.config.js, webpack.main.config.js, etc.
    for file_name in ("forge.config.js", "webpack.main.config.js",
                      "webpack.renderer.config.js", "webpack.rules.js"):
        copy_template(file_name)
    # Copy src directory
    copy_these(list([p.name for p in (old_dir / "src").glob("*")]), old_dir / "src",
               prj_dir / "src")
    # Copy dist directory
    static_dir = prj_src_dir / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    copy_these(list([p.name for p in dist_dir.glob("*")]), dist_dir, static_dir)
    # Get icons
    get_icon(config, prj_src_dir)
    # yarn
    run_shell_command("yarn", cwd=new_dir)
