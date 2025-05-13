import logging

from mkcd_to_app.config import Config
from utils.cmd import run_shell_command
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
    if (cwd / prj_name).exists():
        logger.debug(f"Project {prj_name} already exists, continuing...")
    else:
        run_shell_command(f"npx --yes create-electron-app {prj_name} --template=typescript", cwd=cwd)
