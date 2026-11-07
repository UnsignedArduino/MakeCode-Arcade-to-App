from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from mkcd2app.config import load_config_from_yaml
from mkcd2app.models.config import GitCodeSource, GitHubCodeSource


def config_yaml_with_code(code: dict[str, Any]) -> str:
    return yaml.safe_dump(
        {
            "version": 1,
            "project": {
                "name": "Test",
                "path_friendly_name": "test",
                "author": "Test",
                "version": "1.0.0",
            },
            "inputs": {"code": code, "assets": {}},
            "build_dir": "build",
            "target": "4.0.14",
            "outputs": [{"type": "static"}],
        }
    )


def test_git_source_with_ref() -> None:
    config = load_config_from_yaml(
        config_yaml_with_code(
            {"type": "git", "url": "https://gitlab.com/a/b.git", "ref": "v1.0.0"}
        )
    )
    source = config.inputs.code.root
    assert isinstance(source, GitCodeSource)
    assert str(source.url) == "https://gitlab.com/a/b.git"
    assert source.ref == "v1.0.0"


def test_git_source_ref_defaults_to_default_branch() -> None:
    config = load_config_from_yaml(
        config_yaml_with_code({"type": "git", "url": "https://codeberg.org/a/b"})
    )
    source = config.inputs.code.root
    assert isinstance(source, GitCodeSource)
    assert source.ref is None


@pytest.mark.parametrize(
    "url", ["ssh://git@example.com/a/b.git", "git://example.com/a/b", "file:///a/b"]
)
def test_git_source_accepts_non_http_urls(url: str) -> None:
    config = load_config_from_yaml(config_yaml_with_code({"type": "git", "url": url}))
    assert isinstance(config.inputs.code.root, GitCodeSource)


def test_git_source_requires_url() -> None:
    with pytest.raises(ValidationError):
        load_config_from_yaml(
            config_yaml_with_code({"type": "git", "value": "https://github.com/a/b"})
        )


def test_github_alias_still_parses() -> None:
    config = load_config_from_yaml(
        config_yaml_with_code(
            {"type": "github", "value": "https://github.com/a/b", "checkout": "dev"}
        )
    )
    source = config.inputs.code.root
    assert isinstance(source, GitHubCodeSource)
    assert str(source.value) == "https://github.com/a/b"
    assert source.checkout == "dev"


def test_github_alias_checkout_defaults_to_master() -> None:
    config = load_config_from_yaml(
        config_yaml_with_code({"type": "github", "value": "https://github.com/a/b"})
    )
    source = config.inputs.code.root
    assert isinstance(source, GitHubCodeSource)
    assert source.checkout == "master"
