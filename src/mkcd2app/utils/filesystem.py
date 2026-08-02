import os
import shutil
import stat
from pathlib import Path
from types import TracebackType
from typing import Any


def _remove_readonly(
    func: Any,
    path: str,
    exc_info: tuple[type[BaseException], BaseException, TracebackType],
) -> None:
    """shutil.rmtree error handler: clear read-only bit and retry.

    Needed on Windows because git marks files under .git/objects (and
    sometimes .git itself) read-only, which makes os.unlink/os.rmdir
    raise PermissionError (WinError 5) even though we own the files.
    """
    os.chmod(path, stat.S_IWRITE)
    func(path)


def rmtree_robust(path: Path) -> None:
    if not path.exists():
        return
    shutil.rmtree(path, onerror=_remove_readonly)
