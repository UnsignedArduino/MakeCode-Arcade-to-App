import logging
import shutil
from pathlib import Path

from .logger import create_logger

logger = create_logger(name=__name__, level=logging.INFO)


def delete_these(dirs_and_files: list[str], dir: Path):
    """
    Deletes the specified directories and files from the given directory.

    :param dirs_and_files: A list of file names to delete.
    :param dir: The directory from which to delete the files.
    """
    logger.debug(f"Searching for {len(dirs_and_files)} directories and files to delete")
    for file in dirs_and_files:
        file_path = dir / file
        if file_path.exists():
            if file_path.is_dir():
                shutil.rmtree(file_path)
            else:
                file_path.unlink()
