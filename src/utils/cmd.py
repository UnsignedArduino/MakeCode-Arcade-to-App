import logging
import subprocess
from os import PathLike
from pathlib import Path
from typing import Optional, Sequence

from .logger import create_logger

logger = create_logger(name=__name__, level=logging.DEBUG)


def run_command(command: str | bytes | PathLike[str] | PathLike[bytes] | Sequence[
    str | bytes | PathLike[str] | PathLike[bytes]], cwd: Optional[Path] = None):
    """
    Run a command in the specified directory.

    :param command: The command to run.
    :param cwd: The directory in which to run the command.
    """
    if cwd:
        logger.debug(f"Running command in {cwd}: {command}")
    else:
        logger.debug(f"Running command: {command}")
    subprocess.run(command, cwd=cwd, check=True)


def run_shell_command(command: str, cwd: Optional[Path] = None):
    """
    Run a shell command in the specified directory.

    :param command: The shell command to run.
    :param cwd: The directory in which to run the command.
    """
    if cwd:
        logger.debug(f"Running command in {cwd}: {command}")
    else:
        logger.debug(f"Running command: {command}")
    subprocess.run(command, cwd=cwd, shell=True, check=True)
