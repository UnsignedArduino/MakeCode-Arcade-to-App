import logging
import os
import shutil
import subprocess
from pathlib import Path

from mkcd2app.utils.logger import create_logger

logger = create_logger(name=__name__, level=logging.INFO)


class BuildError(Exception):
    def __init__(self, command, cwd, returncode, output):
        self.command, self.cwd, self.returncode, self.output = command, cwd, returncode, output
        super().__init__(f"{command} failed ({returncode}) in {cwd}")


def run_cmd(command: list[str], cwd: Path | str) -> str:
    """
    Runs a command (as a list, no shell) and captures its output.

    The executable in ``command[0]`` is resolved via ``shutil.which()`` so
    the platform-appropriate variant is used (e.g. ``npm.cmd`` on Windows,
    ``npm`` on Unix).

    :param command: The command as a list of arguments, e.g. ``["npm", "ci"]``.
    :param cwd: The working directory to execute the command in.
    :return: The stdout.
    :raises BuildError: If the command fails.
    :raises FileNotFoundError: If the executable cannot be found on PATH.
    """
    resolved = shutil.which(command[0])
    if resolved is None:
        raise FileNotFoundError(
            f"Executable '{command[0]}' not found on PATH. "
            f"Current PATH: {os.environ.get('PATH', '')}"
        )
    cmd_list = [resolved, *command[1:]]
    logger.debug(f"Running {command} in {cwd}")
    proc = subprocess.run(cmd_list, shell=False, cwd=cwd, capture_output=True,
                          text=True)
    if proc.returncode != 0:
        raise BuildError(command, cwd, proc.returncode, proc.stdout + proc.stderr)
    return proc.stdout
