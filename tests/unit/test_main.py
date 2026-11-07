import stat
from pathlib import Path

import pytest

from mkcd2app.main import _clear_build_dir
from mkcd2app.utils.paths import get_redun_db_for_build_path


def test_clear_build_dir_missing_is_fine(tmp_path: Path) -> None:
    _clear_build_dir(tmp_path / "missing")
    assert not (tmp_path / "missing").exists()


def test_clear_build_dir_empty_is_fine(tmp_path: Path) -> None:
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    _clear_build_dir(build_dir)
    assert build_dir.is_dir()


def test_clear_build_dir_with_cache_db_deletes_it(tmp_path: Path) -> None:
    build_dir = tmp_path / "build"
    (build_dir / "game-source").mkdir(parents=True)
    (build_dir / "game-source" / "main.ts").write_text("x", encoding="utf-8")
    get_redun_db_for_build_path(build_dir).write_text("db", encoding="utf-8")
    _clear_build_dir(build_dir)
    assert not build_dir.exists()
    assert tmp_path.is_dir()


def test_clear_build_dir_deletes_read_only_files(tmp_path: Path) -> None:
    # A git source's .git has read-only files, which fail a plain rmtree on Windows
    build_dir = tmp_path / "build"
    read_only = build_dir / "game-source" / ".git" / "objects" / "pack"
    read_only.parent.mkdir(parents=True)
    read_only.write_text("x", encoding="utf-8")
    read_only.chmod(stat.S_IREAD)
    get_redun_db_for_build_path(build_dir).write_text("db", encoding="utf-8")
    _clear_build_dir(build_dir)
    assert not build_dir.exists()


def test_clear_build_dir_refuses_without_cache_db(tmp_path: Path) -> None:
    # e.g. a typo in build_dir, or `build_dir: "."` in a project folder
    important = tmp_path / "important.txt"
    important.write_text("keep me", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Refusing to clear"):
        _clear_build_dir(tmp_path)
    assert important.read_text("utf-8") == "keep me"
