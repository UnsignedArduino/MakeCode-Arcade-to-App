import logging
import subprocess
from pathlib import Path

from config import Config, SourceType
from utils.logger import create_logger

logger = create_logger(name=__name__, level=logging.DEBUG)


def download_source(config: Config, cwd: Path) -> Path:
    """
    Downloads the source code based on the provided configuration.

    :param config: The configuration object containing source information.
    :param cwd: The current working directory where the source code folder will be
     downloaded.
    :return: The path to the downloaded source code.
    """
    if config.source_type == SourceType.GITHUB:
        logger.info(f"Downloading source from GitHub")
        if config.source_checkout is not None:
            raise NotImplementedError("Complex GitHub sources are not yet supported")
        # Assume it's `git clone`able
        subprocess.run(["git", "clone", config.source], cwd=cwd, check=True)
    else:
        raise NotImplementedError("Only GitHub sources are supported for now")
    # Since the cwd was just created, the source code is most likely going to be tbe
    # only directory in it
    source_code_path = None
    for path in cwd.iterdir():
        if path.is_dir():
            source_code_path = path
            break
    else:
        raise FileNotFoundError("No source code directory found after download")
    logger.debug(f"Source code path: {source_code_path}")
    return source_code_path
