from dataclasses import dataclass
from pathlib import Path

import pytest
from dulwich import porcelain
from dulwich.repo import Repo

from mkcd2app.utils.git import clone_and_checkout

IDENTITY = b"Test <test@example.com>"


@dataclass
class SourceRepo:
    path: Path
    first_sha: str  # tagged v1, content "1"
    second_sha: str  # tip of the "feature" branch, content "2"
    head_sha: str  # tip of the default branch, content "3"


def commit_file(repo_path: Path, content: str) -> str:
    (repo_path / "file.txt").write_text(content, encoding="utf-8")
    porcelain.add(str(repo_path), [str(repo_path / "file.txt")])
    # sign=False so a commit.gpgsign in the user's git config doesn't apply
    sha = porcelain.commit(
        str(repo_path),
        message=f"Write {content}".encode(),
        author=IDENTITY,
        committer=IDENTITY,
        sign=False,
    )
    return sha.decode()


@pytest.fixture(scope="module")
def source_repo(tmp_path_factory: pytest.TempPathFactory) -> SourceRepo:
    path = tmp_path_factory.mktemp("source")
    porcelain.init(str(path))
    first = commit_file(path, "1")
    porcelain.tag_create(str(path), b"v1", sign=False)
    second = commit_file(path, "2")
    porcelain.branch_create(str(path), b"feature")
    head = commit_file(path, "3")
    return SourceRepo(path, first, second, head)


def read_clone(path: Path) -> tuple[str, str]:
    """Return the checked-out file content and the commit HEAD points at."""
    with Repo(str(path)) as repo:
        head = repo.head().decode()
    return (path / "file.txt").read_text(encoding="utf-8"), head


def test_default_branch(source_repo: SourceRepo, tmp_path: Path) -> None:
    clone_and_checkout(str(source_repo.path), tmp_path / "clone")
    assert read_clone(tmp_path / "clone") == ("3", source_repo.head_sha)


def test_branch(source_repo: SourceRepo, tmp_path: Path) -> None:
    clone_and_checkout(str(source_repo.path), tmp_path / "clone", "feature")
    assert read_clone(tmp_path / "clone") == ("2", source_repo.second_sha)


def test_tag(source_repo: SourceRepo, tmp_path: Path) -> None:
    clone_and_checkout(str(source_repo.path), tmp_path / "clone", "v1")
    assert read_clone(tmp_path / "clone") == ("1", source_repo.first_sha)


@pytest.mark.parametrize("length", [7, 40])
def test_commit_sha(source_repo: SourceRepo, tmp_path: Path, length: int) -> None:
    sha = source_repo.second_sha[:length]
    clone_and_checkout(str(source_repo.path), tmp_path / "clone", sha)
    assert read_clone(tmp_path / "clone") == ("2", source_repo.second_sha)


def test_commit_sha_matching_default_branch(
    source_repo: SourceRepo, tmp_path: Path
) -> None:
    # Regression: dulwich only writes files that differ from the current HEAD tree,
    # so this used to leave an empty worktree after a no-checkout clone
    clone_and_checkout(
        str(source_repo.path), tmp_path / "clone", source_repo.head_sha[:7]
    )
    assert read_clone(tmp_path / "clone") == ("3", source_repo.head_sha)


def test_unknown_ref(source_repo: SourceRepo, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Could not find"):
        clone_and_checkout(str(source_repo.path), tmp_path / "clone", "nope")


def test_value_error_without_ref_is_not_retried_as_a_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Only a ref can be mistaken for a commit SHA, so anything else must surface
    calls: list[str] = []

    def fake_clone(url: str, *args: object, **kwargs: object) -> None:
        calls.append(url)
        raise ValueError("some other problem")

    monkeypatch.setattr(porcelain, "clone", fake_clone)
    with pytest.raises(ValueError, match="some other problem"):
        clone_and_checkout("https://example.com/a/b", tmp_path / "clone")
    assert calls == ["https://example.com/a/b"]
