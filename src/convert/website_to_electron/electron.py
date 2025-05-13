import json
import logging
from pathlib import Path
from typing import Callable

from convert.mkcd_to_website.config import Config, SourceType
from utils.cmd import run_shell_command
from utils.filesystem import copy_these, delete_these
from utils.logger import create_logger

logger = create_logger(name=__name__, level=logging.INFO)


def generate_electron(config: Config, prj_name: str, template_dir: Path, dist_dir: Path, cwd: Path):
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
        run_shell_command(f"npx --yes create-electron-app@latest {prj_name} --template=webpack", cwd=cwd)
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
    for file_name in ("forge.config.js", "webpack.main.config.js", "webpack.renderer.config.js", "webpack.rules.js"):
        copy_template(file_name)
    # yarn
    run_shell_command("yarn", cwd=new_dir)
    # Copy dist directory
    copy_these(list([p.name for p in dist_dir.glob("*")]), dist_dir, prj_src_dir)
