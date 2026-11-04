import json
import logging
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import requests
from helpers import (
    TARGET_VERSION,
    CmdCall,
    FakeResponse,
    FakeRunCmd,
    capture_logger,
    tree_digest,
)
from PIL import Image
from redun.file import ContentDir, ContentFile

from mkcd2app.build_project.inputs import code
from mkcd2app.build_project.inputs.code import (
    _warn_on_target_mismatch,
    build_binary_js,
    copy_support_files,
    fetch_code,
)
from mkcd2app.utils.paths import get_js_tools_bin_dir

FIXTURES = Path(__file__).parent.parent / "fixtures"
EMPTY_GAME_DIR = FIXTURES / "empty_game"
EMPTY_PNG = FIXTURES / "embedded" / "empty-game.png"  # saved with 4.0.14
DUCK_PNG = FIXTURES / "embedded" / "falling-duck.png"  # saved with 4.1.27
MKC_JSON = {"targetWebsite": f"https://arcade.makecode.com/v{TARGET_VERSION}"}


def read_mkc_json(code_path: Path) -> Any:
    return json.loads((code_path / "mkc.json").read_text(encoding="utf-8"))


def run_fetch_code(
    build_dir: Path, source: dict[str, Any], target: str = TARGET_VERSION
) -> Path:
    result: ContentDir = fetch_code.func(
        json.dumps(source), target, str(build_dir / "test-source")
    )
    return Path(result.path)


# ------------------------------------------------------------ fetch_code ------


def test_path_source_copies_project(tmp_path: Path) -> None:
    code_path = run_fetch_code(
        tmp_path / "build", {"type": "path", "value": str(EMPTY_GAME_DIR)}
    )
    assert code_path == tmp_path / "build" / "test-source"
    copied = tree_digest(code_path)
    assert copied.pop("mkc.json")
    assert copied == tree_digest(EMPTY_GAME_DIR)
    assert read_mkc_json(code_path) == MKC_JSON


def test_fetch_code_replaces_previous_source(tmp_path: Path) -> None:
    stale = tmp_path / "build" / "test-source" / "stale.ts"
    stale.parent.mkdir(parents=True)
    stale.write_text("old", encoding="utf-8")
    run_fetch_code(tmp_path / "build", {"type": "path", "value": str(EMPTY_GAME_DIR)})
    assert not stale.exists()


def test_mkc_json_uses_target(tmp_path: Path) -> None:
    code_path = run_fetch_code(
        tmp_path / "build",
        {"type": "path", "value": str(EMPTY_GAME_DIR)},
        target="4.1.27",
    )
    assert read_mkc_json(code_path) == {
        "targetWebsite": "https://arcade.makecode.com/v4.1.27"
    }


def test_share_link_source_runs_mkc_download(
    tmp_path: Path, mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeRunCmd()
    monkeypatch.setattr(code, "run_cmd", fake)
    url = "https://arcade.makecode.com/S12345-67890-12345-67890"

    code_path = run_fetch_code(tmp_path / "build", {"type": "share_link", "value": url})

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call.command == ["mkc", "download", url]
    assert call.cwd == code_path
    assert call.which_path == get_js_tools_bin_dir()
    assert read_mkc_json(code_path) == MKC_JSON


@pytest.mark.parametrize(
    ("source", "expected_ref"),
    [
        ({"type": "git", "url": "https://example.com/a/b.git", "ref": "v1"}, "v1"),
        ({"type": "git", "url": "https://example.com/a/b.git"}, None),
        ({"type": "github", "value": "https://github.com/a/b", "checkout": "dev"}, "dev"),
        ({"type": "github", "value": "https://github.com/a/b"}, "master"),
    ],
)  # fmt: skip
def test_git_sources_clone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: dict[str, str],
    expected_ref: str | None,
) -> None:
    # Cloning itself is covered by test_git.py; this checks fetch_code's dispatch
    calls: list[tuple[str, Path, str | None]] = []

    def fake_clone(url: str, path: Path, ref: str | None = None) -> None:
        # The parent must exist, and the clone target must not
        assert path.parent.is_dir()
        assert not path.exists()
        calls.append((url, path, ref))
        path.mkdir()

    monkeypatch.setattr(code, "clone_and_checkout", fake_clone)
    code_path = run_fetch_code(tmp_path / "build", source)

    url = source.get("url") or source["value"]
    assert calls == [(url, code_path, expected_ref)]
    assert read_mkc_json(code_path) == MKC_JSON


def test_file_source_extracts_project(tmp_path: Path) -> None:
    code_path = run_fetch_code(
        tmp_path / "build", {"type": "file", "value": str(EMPTY_PNG)}
    )
    assert (code_path / "pxt.json").is_file()
    assert (code_path / "main.ts").is_file()
    assert read_mkc_json(code_path) == MKC_JSON


def test_file_source_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="nope.png"):
        run_fetch_code(
            tmp_path / "build", {"type": "file", "value": str(tmp_path / "nope.png")}
        )


@pytest.mark.parametrize(("png", "warns"), [(EMPTY_PNG, False), (DUCK_PNG, True)])
def test_file_source_warns_on_target_mismatch(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, png: Path, warns: bool
) -> None:
    with capture_logger(caplog, code.logger):
        run_fetch_code(tmp_path / "build", {"type": "file", "value": str(png)})
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    if warns:
        assert [r.getMessage() for r in warnings] == [
            f"Project was saved with Arcade 4.1.27, building against {TARGET_VERSION}"
        ]
    else:
        assert warnings == []


# ---------------------------------------------- _warn_on_target_mismatch ------


@pytest.mark.parametrize(
    "pxt_json",
    [
        None,  # file missing
        "not json",
        "[]",
        "{}",
        '{"targetVersions": []}',
        '{"targetVersions": {"targetId": "arcade"}}',
        f'{{"targetVersions": {{"target": "{TARGET_VERSION}"}}}}',
    ],
)
def test_target_mismatch_no_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, pxt_json: str | None
) -> None:
    path = tmp_path / "pxt.json"
    if pxt_json is not None:
        path.write_text(pxt_json, encoding="utf-8")
    with capture_logger(caplog, code.logger):
        _warn_on_target_mismatch(path, TARGET_VERSION)
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_target_mismatch_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "pxt.json"
    path.write_text(json.dumps({"targetVersions": {"target": "2.0.48"}}), "utf-8")
    with capture_logger(caplog, code.logger):
        _warn_on_target_mismatch(path, TARGET_VERSION)
    assert [(r.levelno, r.getMessage()) for r in caplog.records] == [
        (
            logging.WARNING,
            f"Project was saved with Arcade 2.0.48, building against {TARGET_VERSION}",
        )
    ]


# ------------------------------------------------------- build_binary_js ------


def test_build_binary_js(
    tmp_path: Path, mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code_path = tmp_path / "build" / "test-source"
    code_path.mkdir(parents=True)
    (code_path / "main.ts").write_text("// game", encoding="utf-8")
    before = tree_digest(code_path)

    def fake_mkc_build(call: CmdCall) -> None:
        assert (call.cwd / "main.ts").is_file()
        (call.cwd / "built").mkdir()
        (call.cwd / "built" / "binary.js").write_text("// built", encoding="utf-8")
        (call.cwd / "built" / "other.txt").write_text("x", encoding="utf-8")

    fake = FakeRunCmd(fake_mkc_build)
    monkeypatch.setattr(code, "run_cmd", fake)
    build_dir = tmp_path / "build" / "test-binary-js-build"

    result: ContentFile = build_binary_js.func(
        ContentDir(str(code_path)), str(build_dir)
    )

    assert [(c.command, c.cwd, c.which_path) for c in fake.calls] == [
        (["mkc", "build", "-j"], build_dir, get_js_tools_bin_dir())
    ]
    output = build_dir / "built" / "binary.js"
    assert Path(result.path) == output
    assert output.read_text(encoding="utf-8") == "// built"
    # Built in a copy, so fetch_code's ContentDir hash doesn't change
    assert tree_digest(code_path) == before


def test_build_binary_js_replaces_previous_build(
    tmp_path: Path, mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code_path = tmp_path / "build" / "test-source"
    code_path.mkdir(parents=True)
    build_dir = tmp_path / "build" / "test-binary-js-build"
    stale = build_dir / "built" / "binary.js"
    stale.parent.mkdir(parents=True)
    stale.write_text("old", encoding="utf-8")

    def check_no_stale_build(call: CmdCall) -> None:
        assert not stale.exists()

    monkeypatch.setattr(code, "run_cmd", FakeRunCmd(check_no_stale_build))
    build_binary_js.func(ContentDir(str(code_path)), str(build_dir))


# ---------------------------------------------------- copy_support_files ------


@pytest.fixture
def sim_html(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path]:
    path = tmp_path / "target" / TARGET_VERSION / "---simulator.html"
    path.parent.mkdir(parents=True)
    path.write_text("<html>sim</html>", encoding="utf-8")
    requested: list[str] = []

    def fake_get_sim_html_path(v: str) -> Path:
        requested.append(v)
        return path

    monkeypatch.setattr(code, "get_sim_html_path", fake_get_sim_html_path)
    yield path
    assert requested == [TARGET_VERSION]


def make_png(path: Path, size: tuple[int, int] = (32, 32)) -> Path:
    Image.new("RGBA", size, (255, 0, 0, 255)).save(path)
    return path


def run_copy_support_files(build_dir: Path, icon: dict[str, str] | None) -> Path:
    result: ContentDir = copy_support_files.func(
        TARGET_VERSION,
        json.dumps(icon) if icon else None,
        str(build_dir / "test-binary-js-support"),
    )
    return Path(result.path)


def test_support_files_without_icon(tmp_path: Path, sim_html: Path) -> None:
    support = run_copy_support_files(tmp_path / "build", None)
    assert support == tmp_path / "build" / "test-binary-js-support"
    assert sorted(p.name for p in support.iterdir()) == ["---simulator.html"]
    assert (support / "---simulator.html").read_bytes() == sim_html.read_bytes()


def test_support_files_replaces_previous_output(tmp_path: Path, sim_html: Path) -> None:
    stale = tmp_path / "build" / "test-binary-js-support" / "favicon.ico"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"old icon")
    support = run_copy_support_files(tmp_path / "build", None)
    assert not (support / "favicon.ico").exists()


def test_support_files_icon_from_path(tmp_path: Path, sim_html: Path) -> None:
    icon = make_png(tmp_path / "icon.png")
    support = run_copy_support_files(
        tmp_path / "build", {"type": "path", "value": str(icon)}
    )
    with Image.open(support / "favicon.ico") as im:
        assert im.format == "ICO"


def test_support_files_icon_from_url(
    tmp_path: Path, sim_html: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    png = make_png(tmp_path / "icon.png").read_bytes()
    urls: list[str] = []

    def fake_get(url: str) -> FakeResponse:
        urls.append(url)
        return FakeResponse(png)

    monkeypatch.setattr(requests, "get", fake_get)
    support = run_copy_support_files(
        tmp_path / "build", {"type": "url", "value": "https://example.com/icon.png"}
    )
    assert urls == ["https://example.com/icon.png"]
    with Image.open(support / "favicon.ico") as im:
        assert im.format == "ICO"


def test_support_files_icon_url_http_error(
    tmp_path: Path, sim_html: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(requests, "get", lambda url: FakeResponse(b"", 404))
    with pytest.raises(requests.HTTPError):
        run_copy_support_files(
            tmp_path / "build", {"type": "url", "value": "https://example.com/x.png"}
        )
