import logging
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from helpers import Cli, FakeToolchain, GameProject, TaskSpy, install_fake_target

import mkcd2app.build_project as build_project_module
from mkcd2app.build_project import website
from mkcd2app.build_project.inputs import code
from mkcd2app.target import install as target_install
from mkcd2app.toolchain import install as toolchain_install
from mkcd2app.utils.resources import get_resource_template_path

TESTS_DIR = Path(__file__).parent
TIERS = ("unit", "integration", "e2e")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """
    Mark each test with its tier by its directory, so `-m unit` selects them.

    CI runs each tier as a separate workflow, so a test outside these directories would
    run in none of them; fail collection instead of skipping it quietly.
    """
    for item in items:
        parts = item.path.relative_to(TESTS_DIR).parts
        if len(parts) < 2 or parts[0] not in TIERS:
            raise pytest.UsageError(
                f"{item.nodeid}: tests must live under "
                f"{', '.join(f'tests/{tier}' for tier in TIERS)}"
            )
        item.add_marker(parts[0])


@pytest.fixture
def mkcd2app_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point MKCD2APP_HOME at a temp dir, so the test can't touch the real user dirs."""
    home = tmp_path / "mkcd2app-home"
    monkeypatch.setenv("MKCD2APP_HOME", str(home))
    return home


@pytest.fixture
def restore_log_levels() -> Iterator[None]:
    """Put back every logger's level, since set_all_stdout_logger_levels changes all."""
    all_loggers = logging.Logger.manager.loggerDict
    before = {
        name: (lgr.level, [(h, h.level) for h in lgr.handlers])
        for name, lgr in all_loggers.items()
        if isinstance(lgr, logging.Logger)
    }
    yield
    for name, lgr in all_loggers.items():
        if isinstance(lgr, logging.Logger):
            level, handlers = before.get(name, (logging.NOTSET, []))
            lgr.setLevel(level)
            for handler, handler_level in handlers:
                handler.setLevel(handler_level)


# ---------------------------------------------------- integration test harness ---


@pytest.fixture
def fake_toolchain(monkeypatch: pytest.MonkeyPatch) -> FakeToolchain:
    """Replace `run_cmd` everywhere it's used, so no `npm` or `mkc` really runs."""
    fake = FakeToolchain()
    for module in (code, website, toolchain_install, target_install):
        monkeypatch.setattr(module, "run_cmd", fake)
    return fake


@pytest.fixture
def task_spy(monkeypatch: pytest.MonkeyPatch) -> TaskSpy:
    return TaskSpy(monkeypatch)


@pytest.fixture
def cli(
    mkcd2app_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_toolchain: FakeToolchain,
    task_spy: TaskSpy,
) -> Cli:
    return Cli(monkeypatch, fake_toolchain, task_spy)


@pytest.fixture
def template_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    A copy of the real bundled template that builds use, so a test can change it. The
    tests that change nothing about it still get drift in the real one caught.
    """
    dst = tmp_path / "vite-project"
    with get_resource_template_path("vite-project") as src:
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("node_modules", "dist"))

    @contextmanager
    def fake_get_resource_template_path(name: str | None = None) -> Iterator[Path]:
        assert name == "vite-project"
        yield dst

    monkeypatch.setattr(
        build_project_module,
        "get_resource_template_path",
        fake_get_resource_template_path,
    )
    return dst


@pytest.fixture
def project(tmp_path: Path, cli: Cli, template_dir: Path) -> GameProject:
    """A game ready to build: its config is written and its target is installed."""
    install_fake_target()
    root = tmp_path / "project"
    root.mkdir()
    return GameProject(root, cli)
