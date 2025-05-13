import logging
import shutil
from pathlib import Path

from .logger import create_logger

logger = create_logger(name=__name__, level=logging.INFO)


def copy_these(dirs_and_files: list[str], src_dir: Path, dest_dir: Path):
    """
    Copies the specified directories and files in the src_dir to the dest_dir.
    
    :param dirs_and_files: A list of file names to copy.
    :param src_dir: The source directory from which to copy the files.
    :param dest_dir: The destination directory to which the files will be copied.
    """
    logger.debug(f"Copying {len(dirs_and_files)} directories and files")
    for file in dirs_and_files:
        src_path = src_dir / file
        dest_path = dest_dir / file
        if src_path.exists():
            logger.debug(f"Copying {src_path} to {dest_path}")
            if src_path.is_dir():
                shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
            else:
                shutil.copy2(src_path, dest_path)
        else:
            logger.debug(f"{src_path} does not exist, skipping copy.")


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
            logger.debug(f"Deleting {file_path}")
            if file_path.is_dir():
                shutil.rmtree(file_path)
            else:
                file_path.unlink()
        else:
            logger.debug(f"{file_path} does not exist, skipping deletion.")
