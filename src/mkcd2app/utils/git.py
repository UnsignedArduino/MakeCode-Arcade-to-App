import logging
import os
import sys
from pathlib import Path
from typing import BinaryIO

from dulwich import porcelain

from mkcd2app.utils.logger import create_logger

logger = create_logger(name=__name__, level=logging.INFO)


def clone_and_checkout(url: str, path: Path, ref: str | None = None) -> None:
    """
    Clone a git repository and check out a branch, tag, or commit, using dulwich
    (pure Python) so no `git` executable is needed.

    The default branch, branches, and tags get a shallow (depth 1) clone. Anything
    else is treated as a (possibly abbreviated) commit SHA, which needs a full clone
    because a shallow clone can only fetch refs the server advertises.

    :param url: The URL (or local path) of the repository to clone.
    :param path: The directory to clone into. Must not exist or be empty.
    :param ref: A branch name, tag name, or (possibly abbreviated) commit SHA. None
     checks out the remote's default branch.
    """
    # dulwich writes \r-separated progress to errstream, which floods non-TTY logs
    # (like CI), so only show it with --debug
    show_progress = logger.isEnabledFor(logging.DEBUG)
    with open(os.devnull, "wb") as devnull:
        errstream: BinaryIO = sys.stderr.buffer if show_progress else devnull
        try:
            logger.debug(f"Shallow cloning {url}@{ref or 'default branch'} to {path}")
            with porcelain.clone(
                url,
                str(path),
                depth=1,
                branch=ref,
                errstream=errstream,
            ):
                return
        except ValueError:
            # dulwich raises ValueError (and removes the directory) when ref isn't
            # a branch or tag on the remote. That can't happen with ref=None.
            if ref is None:
                raise
            logger.debug(f"{ref!r} is not a branch or tag, assuming a commit SHA")

        logger.debug(f"Cloning {url} to {path}")
        # Check out the default branch first: dulwich's checkout only writes files
        # that differ from the current HEAD tree, so after a no-checkout clone
        # (empty worktree), a target with the same tree as HEAD would write nothing.
        with porcelain.clone(url, str(path), errstream=errstream):
            pass

    logger.debug(f"Checking out {ref}")
    try:
        porcelain.checkout(str(path), ref)
    except KeyError:
        raise ValueError(
            f"Could not find branch, tag, or commit {ref!r} in {url}"
        ) from None
