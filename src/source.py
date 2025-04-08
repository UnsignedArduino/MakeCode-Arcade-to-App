import logging
import shutil
from pathlib import Path
from typing import Optional

from config import Config, SourceType
from src.utils.cmd import run_command
from utils.logger import create_logger

logger = create_logger(name=__name__, level=logging.DEBUG)


def download_source(config: Config, cwd: Path,
                    no_cache: Optional[bool] = False) -> Path:
    """
    Downloads the source code based on the provided configuration.

    :param config: The configuration object containing source information.
    :param cwd: The current working directory where the source code folder will be
     downloaded.
    :param no_cache: If True, forces a fresh download of the source code.
    :return: The path to the downloaded source code.
    """
    source_code_path = cwd / f"{config.name} source"
    if no_cache:
        logger.debug("Checking for existing source code to remove")
        if source_code_path.exists():
            logger.debug(f"Removing {source_code_path}")
            try:
                shutil.rmtree(source_code_path)
            except PermissionError as e:
                logger.error(e)
                logger.error("Permission denied. If it's a .git object, you may need "
                             "to delete it with admin/superuser privileges.")
                raise e
    elif source_code_path.exists():
        logger.debug(f"Source code already exists at {source_code_path}")
        if config.source_type == SourceType.GITHUB:
            logger.debug("Checking for updates")
            run_command(["git", "checkout", config.source_checkout],
                        cwd=source_code_path)
            run_command(["git", "pull"], cwd=source_code_path)
        return source_code_path
    if config.source_type == SourceType.GITHUB:
        logger.info(f"Downloading source from GitHub")
        # Assume it's `git clone`able
        run_command(["git", "clone", config.source, source_code_path], cwd=cwd)
        logger.info(f"Checking out {config.source_checkout}")
        run_command(["git", "checkout", config.source_checkout], cwd=source_code_path)
    else:
        raise NotImplementedError("Only GitHub source is supported for now")
    logger.debug(f"Source code path: {source_code_path}")
    return source_code_path
