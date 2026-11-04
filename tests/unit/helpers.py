"""Shared helpers for unit tests (a plain module, since pytest won't collect it)."""

import hashlib
import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

TARGET_VERSION = "4.0.14"


def make_config_yaml(
    build_dir: Path,
    code: dict[str, Any] | None = None,
    icon: dict[str, Any] | None = None,
    project: dict[str, Any] | None = None,
    target: str = TARGET_VERSION,
) -> str:
    """
    Build a version 1 config as YAML text, like the contents of a config file.

    :param build_dir: The config's build_dir.
    :param code: The inputs.code source. Defaults to a path source that doesn't exist,
     for tests that never read it.
    :param icon: The inputs.assets.icon source, or None for no icon.
    :param project: Keys to override in the project section.
    :param target: The MakeCode Arcade target version.
    """
    assets: dict[str, Any] = {"icon": icon} if icon else {}
    return yaml.safe_dump(
        {
            "version": 1,
            "project": {
                "name": "Test Game",
                "path_friendly_name": "test",
                "description": "A test game",
                "author": "Tester",
                "version": "1.2.3",
                **(project or {}),
            },
            "inputs": {
                "code": code or {"type": "path", "value": str(build_dir / "nowhere")},
                "assets": assets,
            },
            "build_dir": str(build_dir),
            "target": target,
            "outputs": [{"type": "static"}],
        }
    )


@dataclass
class CmdCall:
    command: list[str]
    cwd: Path
    which_path: str | os.PathLike[str] | None


class FakeRunCmd:
    """
    Stands in for ``run_cmd``: records each call, then runs ``on_run`` (if given) so
    the test can create the files the real command would have.
    """

    def __init__(self, on_run: Callable[[CmdCall], None] | None = None) -> None:
        self.calls: list[CmdCall] = []
        self.on_run = on_run

    def __call__(
        self,
        command: list[str],
        cwd: Path | str,
        which_path: str | os.PathLike[str] | None = None,
    ) -> str:
        call = CmdCall(command, Path(cwd), which_path)
        self.calls.append(call)
        if self.on_run:
            self.on_run(call)
        return ""


def tree_digest(root: Path) -> dict[str, str]:
    """Map each file under ``root`` (relative POSIX path) to its SHA-256."""
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@contextmanager
def capture_logger(
    caplog: pytest.LogCaptureFixture, logger: logging.Logger
) -> Iterator[pytest.LogCaptureFixture]:
    """
    Capture records from one of our loggers. ``create_logger`` sets
    ``propagate = False``, so caplog's root handler never sees them otherwise.
    """
    logger.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)
