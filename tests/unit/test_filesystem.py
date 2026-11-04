import os
import stat
import sys
from pathlib import Path

from mkcd2app.utils.filesystem import _remove_readonly, rmtree_robust


def make_readonly_tree(root: Path) -> Path:
    (root / "objects" / "ab").mkdir(parents=True)
    readonly = root / "objects" / "ab" / "cdef"
    readonly.write_bytes(b"git object")
    os.chmod(readonly, stat.S_IREAD)
    return readonly


def test_removes_tree_with_readonly_files(tmp_path: Path) -> None:
    root = tmp_path / ".git"
    make_readonly_tree(root)
    rmtree_robust(root)
    assert not root.exists()


def test_remove_readonly_handler_clears_bit_and_retries(tmp_path: Path) -> None:
    # Called directly, since only Windows refuses to unlink read-only files
    readonly = make_readonly_tree(tmp_path)
    _remove_readonly(os.unlink, str(readonly), sys.exc_info())  # type: ignore[arg-type]
    assert not readonly.exists()
