import logging
from pathlib import Path

from mkcd_to_app.config import Config
from utils.cmd import run_shell_command
from utils.filesystem import copy_these, delete_these
from utils.logger import create_logger

logger = create_logger(name=__name__, level=logging.INFO)


def generate_electron(config: Config, prj_name: str, dist_dir: Path, cwd: Path):
    """
    Generate the Electron app from static HTML, CSS, and JS files. Assumes index.html
    is the entry point.

    :param config: The configuration object containing the project information.
    :param prj_name: The name of the project.
    :param dist_dir: The dist directory with all the static HTML, CSS, and JS files.
    :param cwd: The current working directory where the project will be created.
    """
    logger.debug(f"Creating Electron app for {prj_name}")
    # Initialize an Electron Forge project
    prj_dir = cwd / prj_name
    prj_src_dir = prj_dir / "src"
    if prj_dir.exists():
        logger.debug(f"Project {prj_name} already exists, continuing...")
    else:
        run_shell_command(f"npx --yes create-electron-app@latest {prj_name} --template=webpack", cwd=cwd)
    # Delete index.html and index.css
    delete_these(["index.html", "index.css"], prj_src_dir)
    # Start copying files
    old_dir = dist_dir
    new_dir = prj_src_dir
    logger.debug(f"Copying HTML, CSS, and JS from {old_dir} to {new_dir}")
    # Copy all files in old_dir to new_dir
    copy_these(list([p.name for p in old_dir.glob("*")]), old_dir, new_dir)
