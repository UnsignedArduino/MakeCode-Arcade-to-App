"""Shared helpers for the tests (a plain module, since pytest won't collect it)."""

import hashlib
import json
import logging
import os
import shutil
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any

import pytest
import requests
import yaml
from redun.file import ContentDir, ContentFile
from redun.task import Task, get_task_registry

from mkcd2app.main import main
from mkcd2app.utils.paths import get_sim_html_path
from mkcd2app.utils.run import BuildError

TARGET_VERSION = "4.0.14"
FIXTURES = Path(__file__).parent / "fixtures"
FAKE_SIM_URL = "https://sim.example.com/---simulator"


def make_config_yaml(
    build_dir: Path,
    code: dict[str, Any] | None = None,
    icon: dict[str, Any] | None = None,
    project: dict[str, Any] | None = None,
    target: str = TARGET_VERSION,
    outputs: list[dict[str, Any]] | None = None,
) -> str:
    """
    Build a version 1 config as YAML text, like the contents of a config file.

    :param build_dir: The config's build_dir.
    :param code: The inputs.code source. Defaults to a path source that doesn't exist,
     for tests that never read it.
    :param icon: The inputs.assets.icon source, or None for no icon.
    :param project: Keys to override in the project section.
    :param target: The MakeCode Arcade target version.
    :param outputs: The outputs. Defaults to only a static website.
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
            "outputs": outputs or [{"type": "static"}],
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


class FakeResponse:
    """Stands in for the ``requests.Response`` that ``requests.get`` returns."""

    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code

    @property
    def text(self) -> str:
        # What requests falls back to when the server sends no charset
        return self.content.decode("iso-8859-1")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


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


# ---------------------------------------------------- integration test harness ---


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def command_name(command: list[str]) -> str:
    """A command without its arguments, like ``mkc build`` or ``npm run build``."""
    return " ".join(command[:3] if command[:2] == ["npm", "run"] else command[:2])


class FakeToolchain:
    """
    Stands in for ``run_cmd`` everywhere: does to the disk what each ``mkc`` and ``npm``
    command would, and fails the test on any other command. Like the real commands,
    these need their inputs to exist, and their output depends on those inputs, so a
    changed game really does produce a different website.
    """

    def __init__(self) -> None:
        self.commands: list[str] = []
        # Names (see command_name) of the commands that should fail
        self.failing: set[str] = set()

    def __call__(
        self,
        command: list[str],
        cwd: Path | str,
        which_path: str | os.PathLike[str] | None = None,
    ) -> str:
        name = command_name(command)
        self.commands.append(name)
        if name in self.failing:
            raise BuildError(command, cwd, 1, f"fake {name} output")
        path = Path(cwd)
        match command:
            case ["mkc", "build", "-j"]:
                self._mkc_build(path)
            case ["mkc", "download", url]:
                self._mkc_download(path, url)
            case ["npm", "ci", *args]:
                self._npm_ci(path, args)
            case ["npm", "run", "build"]:
                self._npm_run_build(path)
            case ["npm", "run", "build:singlefile"]:
                self._npm_run_build_singlefile(path)
            case _:
                raise AssertionError(f"Unexpected command {command} in {cwd}")
        return ""

    @staticmethod
    def _mkc_build(cwd: Path) -> None:
        mkc_json = json.loads((cwd / "mkc.json").read_text(encoding="utf-8"))
        meta = {
            "simUrl": FAKE_SIM_URL,
            "cdnUrl": "https://cdn.example.com/",
            "version": "v0.0.0",
            "target": "arcade",
            "targetVersion": mkc_json["targetWebsite"].rsplit("/v", 1)[1],
        }
        source = _digest(json.dumps(tree_digest(cwd), sort_keys=True).encode())
        (cwd / "built").mkdir()
        (cwd / "built" / "binary.js").write_text(
            f"// meta={json.dumps(meta)}\n// built from {source}\n", encoding="utf-8"
        )

    @staticmethod
    def _mkc_download(cwd: Path, url: str) -> None:
        (cwd / "pxt.json").write_text('{"name": "downloaded"}', encoding="utf-8")
        (cwd / "main.ts").write_text(f"// downloaded from {url}\n", encoding="utf-8")

    @staticmethod
    def _npm_ci(cwd: Path, args: list[str]) -> None:
        lockfile = _digest((cwd / "package-lock.json").read_bytes())
        package = cwd / "node_modules" / "package"
        package.mkdir(parents=True)
        (package / "index.js").write_text(f"// {lockfile}\n", encoding="utf-8")
        (cwd / "node_modules" / ".bin").mkdir()
        if sys.platform != "win32":  # npm makes .cmd shims on Windows instead
            (cwd / "node_modules" / ".bin" / "tool").symlink_to(
                Path("..") / "package" / "index.js"
            )
        if "--prefer-online" in args:
            cache = Path(args[args.index("--cache") + 1])
            cache.mkdir(parents=True, exist_ok=True)
            (cache / lockfile).write_text("cached", encoding="utf-8")

    @staticmethod
    def _built_index_html(cwd: Path) -> str:
        assert (cwd / "node_modules" / "package" / "index.js").is_file()
        index_html = (cwd / "index.html").read_text(encoding="utf-8")
        assets = cwd / "src" / "assets"
        binary = (assets / "binary.js").read_text(encoding="utf-8")
        sim = (assets / "---simulator.html").read_text(encoding="utf-8")
        return f"{index_html}\n<!-- {binary} -->\n<!-- {sim} -->\n"

    def _npm_run_build(self, cwd: Path) -> None:
        index_html = self._built_index_html(cwd)
        assets = cwd / "dist" / "assets"
        assets.mkdir(parents=True)
        (cwd / "dist" / "index.html").write_text(index_html, encoding="utf-8")
        (assets / "index.js").write_text("run()\n", encoding="utf-8")

    def _npm_run_build_singlefile(self, cwd: Path) -> None:
        index_html = self._built_index_html(cwd)
        (cwd / "dist").mkdir()
        (cwd / "dist" / "index.html").write_text(index_html, encoding="utf-8")


class TaskSpy:
    """
    Wraps every mkcd2app task to record the ones that really run (a cache hit doesn't
    call the function), and what each ContentDir/ContentFile held when it was returned.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.ran: list[str] = []
        self.returned: dict[Path, dict[str, str]] = {}
        for task in get_task_registry():  # type: ignore[no-untyped-call]
            if task.namespace == "mkcd2app":
                monkeypatch.setattr(task, "func", self._wrap(task))

    def _wrap(self, task: Task[Any, Any]) -> Callable[..., Any]:
        func = task.func

        @wraps(func)
        def spy(*args: Any, **kwargs: Any) -> Any:
            result = func(*args, **kwargs)
            self.ran.append(task.name)
            if isinstance(result, ContentDir | ContentFile):
                path = Path(result.path)
                self.returned[path] = current_contents(path)
            return result

        return spy


def current_contents(path: Path) -> dict[str, str]:
    """Map each file under ``path``, or ``path`` itself if a file, to its SHA-256."""
    return {"": _digest(path.read_bytes())} if path.is_file() else tree_digest(path)


@dataclass
class Ran:
    """What one CLI run did: the tasks that really ran, and the commands they ran."""

    tasks: set[str]
    commands: list[str]


class Cli:
    """Runs the real ``main()`` in this process, with the toolchain faked."""

    def __init__(
        self, monkeypatch: pytest.MonkeyPatch, toolchain: FakeToolchain, spy: TaskSpy
    ) -> None:
        self.monkeypatch = monkeypatch
        self.toolchain = toolchain
        self.spy = spy

    def run(self, *argv: str) -> Ran:
        """
        :param argv: The CLI arguments.
        :return: What this run did. If it raises instead, ``toolchain.commands`` and
         ``spy.ran`` still say what it did.
        """
        self.toolchain.commands.clear()
        self.spy.ran.clear()
        self.monkeypatch.setattr(sys, "argv", ["mkcd2app", *argv])
        main()
        return Ran(set(self.spy.ran), sorted(self.toolchain.commands))


def install_fake_target(version: str = TARGET_VERSION) -> None:
    """Put a simulator where ``mkcd2app target install`` would."""
    path = get_sim_html_path(version)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"<html>simulator {version}</html>", encoding="utf-8")


class GameProject:
    """A game in a folder of its own, with a config that uses paths relative to it."""

    def __init__(self, root: Path, cli: Cli) -> None:
        self.root = root
        self.cli = cli
        self.game = root / "game"
        self.build_dir = root / "build"
        self.config_path = root / "config.yaml"
        shutil.copytree(FIXTURES / "empty_game", self.game)
        self.config: dict[str, Any] = yaml.safe_load(
            make_config_yaml(
                Path("build"),
                code={"type": "path", "value": "./game"},
                outputs=[{"type": "static"}, {"type": "static-singlefile"}],
            )
        )
        self.write_config()

    def write_config(self, prefix: str = "") -> None:
        """Write ``self.config`` to the config file, after the text in ``prefix``."""
        self.config_path.write_text(
            prefix + yaml.safe_dump(self.config), encoding="utf-8"
        )

    def build(self, *args: str) -> Ran:
        return self.cli.run("build", str(self.config_path), *args)

    @property
    def website(self) -> Path:
        """The static website's index.html."""
        return self.build_dir / "test-website-filled-built" / "dist" / "index.html"

    @property
    def singlefile(self) -> Path:
        """The single-file website."""
        return (
            self.build_dir
            / "test-website-filled-singlefile-built"
            / "dist"
            / "index.html"
        )
