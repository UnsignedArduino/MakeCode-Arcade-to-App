from pathlib import Path

import pytest
from helpers import make_config_yaml
from pydantic import ValidationError

from mkcd2app.config import load_config_from_yaml
from mkcd2app.utils.text import is_strict_semver, raise_for_invalid_strict_semver

VALID = ["4.0.14", "0.0.0", "10.20.30"]
INVALID = [
    "v4.0.14",
    "4.0",
    "4",
    "01.0.0",
    "4.00.1",
    "4.0.14\n",  # $ in Python's re matches before a trailing newline
    " 4.0.14",
    "4.0.14 ",
    "4.0.14-beta",
    "4.0.14+build",
    "",
]


@pytest.mark.parametrize("version", VALID)
def test_is_strict_semver_accepts(version: str) -> None:
    assert is_strict_semver(version)


@pytest.mark.parametrize("version", INVALID)
def test_is_strict_semver_rejects(version: str) -> None:
    assert not is_strict_semver(version)


def test_raise_for_invalid_strict_semver_accepts_valid() -> None:
    raise_for_invalid_strict_semver("4.0.14")  # doesn't raise


@pytest.mark.parametrize("version", INVALID)
def test_raise_for_invalid_strict_semver_raises(version: str) -> None:
    with pytest.raises(ValueError, match="not a valid strict numeric semver"):
        raise_for_invalid_strict_semver(version)


def test_config_accepts_strict_semver_target(tmp_path: Path) -> None:
    config = load_config_from_yaml(make_config_yaml(tmp_path, target="4.0.14"))
    assert config.target == "4.0.14"


@pytest.mark.parametrize("target", ["4.0", "v4.0.14", "4.0.14-beta", "4.0.14\n"])
def test_config_rejects_non_semver_target(tmp_path: Path, target: str) -> None:
    with pytest.raises(ValidationError, match="target"):
        load_config_from_yaml(make_config_yaml(tmp_path, target=target))
