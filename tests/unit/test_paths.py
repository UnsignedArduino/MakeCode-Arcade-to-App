from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path

import pytest

from mkcd2app.utils import paths

VERSION = version("mkcd2app")

DATA_PATHS: list[tuple[Callable[[], Path], str]] = [
    (paths.get_toolchain_dir, "toolchain"),
    (paths.get_js_tools_dir, "toolchain/js_tools"),
    (paths.get_js_tools_bin_dir, "toolchain/js_tools/node_modules/.bin"),
    (paths.get_templates_npm_cache_dir, "toolchain/templates_npm_cache"),
    (paths.get_target_dir, "target"),
    (lambda: paths.get_target_version_dir("4.0.14"), "target/4.0.14"),
    (lambda: paths.get_sim_html_path("4.0.14"), "target/4.0.14/---simulator.html"),
]
STATE_PATHS: list[tuple[Callable[[], Path], str]] = [
    (paths.get_redun_db_for_toolchain_path, "redun_db_for_toolchain.sqlite3"),
    (paths.get_redun_db_for_target_path, "redun_db_for_target.sqlite3"),
]


def test_version_matches_package() -> None:
    assert paths.get_mkcd2app_version() == VERSION


def test_home_override(mkcd2app_home: Path) -> None:
    assert paths.get_home_override_dir() == mkcd2app_home
    assert paths.get_user_data_dir() == mkcd2app_home / "data" / VERSION
    assert paths.get_user_state_dir() == mkcd2app_home / "state" / VERSION


@pytest.mark.parametrize(("get_path", "relative"), DATA_PATHS)
def test_data_paths_under_home(
    mkcd2app_home: Path, get_path: Callable[[], Path], relative: str
) -> None:
    assert get_path() == mkcd2app_home / "data" / VERSION / relative


@pytest.mark.parametrize(("get_path", "relative"), STATE_PATHS)
def test_state_paths_under_home(
    mkcd2app_home: Path, get_path: Callable[[], Path], relative: str
) -> None:
    assert get_path() == mkcd2app_home / "state" / VERSION / relative


@pytest.mark.parametrize("value", [None, ""])
def test_no_override_uses_platformdirs(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv(paths.HOME_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(paths.HOME_ENV_VAR, value)
    assert paths.get_home_override_dir() is None
    assert paths.get_user_data_dir() == Path(paths.DIRS.user_data_dir) / VERSION
    assert paths.get_user_state_dir() == Path(paths.DIRS.user_state_dir) / VERSION


# ------------------------------------------------ relative/tilde overrides ----


@pytest.fixture
def relative_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set MKCD2APP_HOME to a relative path from tmp_path; return where it points."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(paths.HOME_ENV_VAR, "home")
    return tmp_path / "home"


def test_relative_override_is_made_absolute(relative_home: Path) -> None:
    home = paths.get_home_override_dir()
    assert home is not None and home.is_absolute()
    assert home == relative_home.resolve()
    for get_path, _ in DATA_PATHS + STATE_PATHS:
        assert get_path().is_absolute()
        assert get_path().is_relative_to(relative_home.resolve())


def test_tilde_override_is_expanded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows
    monkeypatch.setenv(paths.HOME_ENV_VAR, str(Path("~") / "mkcd2app-home"))
    assert paths.get_home_override_dir() == (tmp_path / "mkcd2app-home").resolve()
