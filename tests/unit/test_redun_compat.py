import os
from collections.abc import Callable
from pathlib import Path

import pytest
import redun.file
from redun.file import ContentDir, Dir, File

# Importing mkcd2app applies the patches
from mkcd2app._redun_compat import (
    _orig_get_proto,
    _patched_get_proto,
    assert_pinned_redun_version,
)


def test_pinned_redun_version() -> None:
    assert_pinned_redun_version()


# ------------------------------------------------------------- get_proto ------


def test_get_proto_is_patched() -> None:
    assert redun.file.get_proto is _patched_get_proto


@pytest.mark.parametrize(
    "url", ["C:\\Users\\me\\game", "c:\\x", "E:/build/x", "z:/"]
)  # fmt: skip
def test_windows_drive_paths_are_local(url: str) -> None:
    assert _orig_get_proto(url) != "local"  # the bug the patch works around
    assert redun.file.get_proto(url) == "local"


@pytest.mark.parametrize(
    ("url", "proto"),
    [
        ("/tmp/x", "local"),
        ("relative/x", "local"),
        ("", "local"),
        (None, "local"),
        ("s3://bucket/key", "s3"),
        ("gs://bucket/key", "gs"),
        ("http://example.com/x", "http"),
        ("C:x", "c"),  # drive-relative, not a drive path: left to urlparse
        ("1:/x", "local"),  # not a letter, so not patched; urlparse has no scheme
    ],
)
def test_other_urls_unchanged(url: str | None, proto: str) -> None:
    assert redun.file.get_proto(url) == _orig_get_proto(url) == proto


def test_file_with_drive_letter_uses_local_filesystem() -> None:
    assert File("C:\\Users\\me\\game\\main.ts").filesystem.name == "local"


# --------------------------------------------------------- content hashing ----


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "tree"
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_text("a", encoding="utf-8")
    (root / "sub" / "b.txt").write_text("b", encoding="utf-8")
    return root


def content_hash(path: Path) -> str:
    # A new object each time: redun caches the hash on the instance
    return ContentDir(str(path)).hash


def dir_hash(path: Path) -> str:
    return Dir(str(path)).hash


def touch_all(root: Path, mtime: float) -> None:
    for p in root.rglob("*"):
        os.utime(p, (mtime, mtime))


@pytest.mark.parametrize("hash_fn", [content_hash, dir_hash])
def test_hash_ignores_mtime(tree: Path, hash_fn: Callable[[Path], str]) -> None:
    touch_all(tree, 1_000_000_000)
    before = hash_fn(tree)
    touch_all(tree, 2_000_000_000)
    assert hash_fn(tree) == before


def test_hash_is_stable(tree: Path) -> None:
    assert content_hash(tree) == content_hash(tree)


def test_dir_hash_matches_content_dir(tree: Path) -> None:
    assert dir_hash(tree) == content_hash(tree)


def test_hash_changes_with_content(tree: Path) -> None:
    before = content_hash(tree)
    (tree / "sub" / "b.txt").write_text("B", encoding="utf-8")
    assert content_hash(tree) != before


def test_hash_changes_with_new_file(tree: Path) -> None:
    before = content_hash(tree)
    (tree / "c.txt").write_text("c", encoding="utf-8")
    assert content_hash(tree) != before


def test_hash_changes_with_removed_file(tree: Path) -> None:
    before = content_hash(tree)
    (tree / "a.txt").unlink()
    assert content_hash(tree) != before


def test_hash_changes_with_rename(tree: Path) -> None:
    before = content_hash(tree)
    (tree / "a.txt").rename(tree / "sub" / "a.txt")
    assert content_hash(tree) != before


def test_hash_includes_path(tree: Path, tmp_path: Path) -> None:
    # Same contents somewhere else is a different output dir, so a different value
    copy = tmp_path / "copy"
    (copy / "sub").mkdir(parents=True)
    (copy / "a.txt").write_text("a", encoding="utf-8")
    (copy / "sub" / "b.txt").write_text("b", encoding="utf-8")
    assert content_hash(copy) != content_hash(tree)
