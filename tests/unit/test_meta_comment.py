import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from mkcd2app.utils.text import extract_meta_comment

# Copied from a real `mkc build -j` of the empty game on 4.0.14
META: dict[str, Any] = {
    "simUrl": "https://trg-arcade.userpxt.io/---simulator",
    "cdnUrl": "https://cdn.makecode.com",
    "version": "v0.0.0",
    "target": "arcade",
    "targetVersion": "4.0.14",
}


def write_binary_js(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "binary.js"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_extracts_metadata(tmp_path: Path) -> None:
    path = write_binary_js(
        tmp_path, "// start", f"// meta={json.dumps(META)}", "var x = 1;"
    )
    metadata = extract_meta_comment(path)
    assert str(metadata.simUrl) == META["simUrl"]
    assert metadata.target == "arcade"
    assert metadata.targetVersion == "4.0.14"


def test_indented_comment(tmp_path: Path) -> None:
    path = write_binary_js(tmp_path, f"    // meta={json.dumps(META)}   ")
    assert extract_meta_comment(path).targetVersion == "4.0.14"


def test_first_meta_comment_wins(tmp_path: Path) -> None:
    other = {**META, "targetVersion": "9.9.9"}
    path = write_binary_js(
        tmp_path, f"// meta={json.dumps(META)}", f"// meta={json.dumps(other)}"
    )
    assert extract_meta_comment(path).targetVersion == "4.0.14"


def test_missing_comment(tmp_path: Path) -> None:
    path = write_binary_js(tmp_path, "// no metadata here", "var meta = {};")
    with pytest.raises(ValueError, match="Meta comment not found"):
        extract_meta_comment(path)


@pytest.mark.parametrize(
    "meta",
    [
        {**META, "unexpected": 1},  # extra="forbid"
        {k: v for k, v in META.items() if k != "simUrl"},
        {**META, "cdnUrl": "not a url"},
    ],
)
def test_invalid_metadata(tmp_path: Path, meta: dict[str, Any]) -> None:
    path = write_binary_js(tmp_path, f"// meta={json.dumps(meta)}")
    with pytest.raises(ValidationError):
        extract_meta_comment(path)


def test_invalid_json(tmp_path: Path) -> None:
    path = write_binary_js(tmp_path, "// meta={not json")
    with pytest.raises(ValidationError):
        extract_meta_comment(path)
