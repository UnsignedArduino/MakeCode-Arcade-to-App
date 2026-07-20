import logging
import subprocess
from pathlib import Path

from mkcd2app.utils.logger import create_logger

logger = create_logger(name=__name__, level=logging.INFO)


class BuildError(Exception):
    def __init__(self, command, cwd, returncode, output):
        self.command, self.cwd, self.returncode, self.output = command, cwd, returncode, output
        super().__init__(f"{command} failed ({returncode}) in {cwd}")


def run_cmd(command: str, cwd: Path | str) -> str:
    """
    Runs a command and captures its output.

    :param command: The command to run - this is executed as a shell command!
    :param cwd: The current working directory to execute the command in.
    :return: The stdout
    :raises BuildError: If the command fails.
    """
    logger.debug(f"Running command `{command}` in {cwd}")
    proc = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise BuildError(command, cwd, proc.returncode, proc.stdout + proc.stderr)
    return proc.stdout
