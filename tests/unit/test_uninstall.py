"""
Uninstalls must really run every time, even across executions sharing a redun DB.

Regression: with caching on, the second ``uninstall`` after a reinstall was a cache
hit on the first (both return None), so it left the reinstalled files in place.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from mkcd2app.target.uninstall import uninstall_target
from mkcd2app.toolchain.uninstall import uninstall_toolchain
from mkcd2app.utils import paths
from mkcd2app.utils.run_redun_task import run_redun_task


def _fake_install(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "marker.txt").write_text("installed", encoding="utf-8")


@pytest.mark.parametrize(
    ("make_expr", "get_dir", "get_db"),
    [
        (
            uninstall_toolchain,
            paths.get_toolchain_dir,
            paths.get_redun_db_for_toolchain_path,
        ),
        (
            lambda: uninstall_target("4.0.14"),
            lambda: paths.get_target_version_dir("4.0.14"),
            paths.get_redun_db_for_target_path,
        ),
    ],
    ids=["toolchain", "target"],
)
def test_uninstall_runs_every_time(
    mkcd2app_home: Path,
    make_expr: Callable[[], Any],
    get_dir: Callable[[], Path],
    get_db: Callable[[], Path],
) -> None:
    directory, db = get_dir(), get_db()
    for _ in range(3):  # install -> uninstall, then reinstall -> uninstall again
        _fake_install(directory)
        run_redun_task(make_expr(), redun_db_path=db)
        assert not directory.exists()
    assert db.is_file()  # each round really shared the same DB


def test_uninstall_target_only_removes_that_version(mkcd2app_home: Path) -> None:
    _fake_install(paths.get_target_version_dir("4.0.14"))
    _fake_install(paths.get_target_version_dir("4.1.27"))
    db = paths.get_redun_db_for_target_path()
    run_redun_task(uninstall_target("4.0.14"), redun_db_path=db)
    assert not paths.get_target_version_dir("4.0.14").exists()
    assert paths.get_target_version_dir("4.1.27").is_dir()
