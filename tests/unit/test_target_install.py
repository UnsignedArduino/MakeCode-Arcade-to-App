import json
from html import unescape
from pathlib import Path
from typing import Any

import pytest
import requests
from helpers import (
    TARGET_VERSION,
    CmdCall,
    FakeResponse,
    FakeRunCmd,
    tree_digest,
)
from redun.file import ContentDir

from mkcd2app.target import install
from mkcd2app.target.install import (
    _download_text,
    download_sim,
    warm_mkc_cache_for_version_and_get_binary_js_metadata,
)
from mkcd2app.utils.paths import get_js_tools_bin_dir, get_sim_html_path
from mkcd2app.utils.resources import get_resource_empty_project_path
from mkcd2app.utils.run import BuildError

SIM_URL = "https://sim.example.com/---simulator"
METADATA = {
    "simUrl": SIM_URL,
    "cdnUrl": "https://cdn.example.com/",
    "version": "v0.0.0",
    "target": "arcade",
    "targetVersion": TARGET_VERSION,
}
METADATA_JSON = json.dumps(METADATA)


def serve(monkeypatch: pytest.MonkeyPatch, pages: dict[str, bytes]) -> list[str]:
    """Fake ``requests.get`` with these pages; return the list of requested URLs."""
    requested: list[str] = []

    def fake_get(url: str) -> FakeResponse:
        requested.append(url)
        return FakeResponse(pages[url])

    monkeypatch.setattr(requests, "get", fake_get)
    return requested


def run_download_sim(monkeypatch: pytest.MonkeyPatch, sim_html: str) -> str:
    """Run download_sim on this simulator page, and return the HTML it wrote."""
    serve(monkeypatch, {SIM_URL: sim_html.encode()})
    return Path(download_sim.func(METADATA_JSON, TARGET_VERSION).path).read_text(
        encoding="utf-8"
    )


# --------------------------------------------------------- _download_text -----


def test_download_text_decodes_utf8_without_charset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression: res.text decodes as ISO-8859-1 when the server sends no charset
    text = "héllo ✓ 😀"
    serve(monkeypatch, {"https://example.com/x": text.encode()})
    assert _download_text("https://example.com/x") == text


def test_download_text_raises_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(requests, "get", lambda url: FakeResponse(b"", 404))
    with pytest.raises(requests.HTTPError):
        _download_text("https://example.com/x")


# ----------------------------------------------------------- download_sim -----


def test_download_sim_inlines_css_and_js(
    mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requested = serve(
        monkeypatch,
        {
            SIM_URL: b'<html><head><link rel="stylesheet" '
            b'href="https://cdn.example.com/a.css"></head><body>'
            b'<script src="https://cdn.example.com/b.js"></script></body></html>',
            "https://cdn.example.com/a.css": b"body { color: red }",
            "https://cdn.example.com/b.js": b"run()",
        },
    )

    result = download_sim.func(METADATA_JSON, TARGET_VERSION)

    assert Path(result.path) == get_sim_html_path(TARGET_VERSION)
    assert requested == [
        SIM_URL,
        "https://cdn.example.com/a.css",
        "https://cdn.example.com/b.js",
    ]
    html = Path(result.path).read_text(encoding="utf-8")
    assert "<style>" in html and "body { color: red }" in html
    assert "run()" in html
    assert "src=" not in html and "<link" not in html


@pytest.mark.parametrize(
    ("href", "expected"),
    [
        ("/a.css", "https://sim.example.com/a.css"),
        ("a.css", "https://sim.example.com/a.css"),
        ("//cdn.example.com/a.css", "https://cdn.example.com/a.css"),
        ("https://cdn.example.com/a.css", "https://cdn.example.com/a.css"),
    ],
)
def test_download_sim_resolves_urls_against_sim_url(
    mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch, href: str, expected: str
) -> None:
    sim = f'<link rel="stylesheet" href="{href}"><script src="{href}"></script>'
    requested = serve(monkeypatch, {SIM_URL: sim.encode(), expected: b"x"})
    download_sim.func(METADATA_JSON, TARGET_VERSION)
    assert requested == [SIM_URL, expected, expected]


def test_download_sim_leaves_tags_without_urls_alone(
    mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    html = run_download_sim(
        monkeypatch, '<link rel="stylesheet"><script>inline()</script>'
    )
    assert "<link" in html and "<style>" not in html
    assert "inline()" in html


def test_download_sim_leaves_other_links_alone(
    mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Only stylesheets get inlined, so a favicon link isn't downloaded
    html = run_download_sim(monkeypatch, '<link rel="icon" href="/favicon.ico">')
    assert 'href="/favicon.ico"' in html


def test_download_sim_does_not_escape_inlined_js(
    mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Escaping these would silently break the simulator
    js = "if (a < b && c > d) run('é')"
    serve(
        monkeypatch,
        {
            SIM_URL: b'<script src="https://cdn.example.com/b.js"></script>',
            "https://cdn.example.com/b.js": js.encode(),
        },
    )
    result = download_sim.func(METADATA_JSON, TARGET_VERSION)
    assert js in Path(result.path).read_text(encoding="utf-8")


def test_download_sim_keeps_non_ascii_text(
    mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # prettify writes these as HTML entities, which browsers decode back
    written = run_download_sim(monkeypatch, "<p>héllo ✓</p>")
    assert "héllo ✓" in unescape(written)


@pytest.mark.parametrize(
    "failing_url",
    [SIM_URL, "https://cdn.example.com/a.css", "https://cdn.example.com/b.js"],
)
def test_download_sim_raises_on_http_error(
    mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch, failing_url: str
) -> None:
    def fake_get(url: str) -> FakeResponse:
        if url == failing_url:
            return FakeResponse(b"", 404)
        if url == SIM_URL:
            return FakeResponse(
                b'<link rel="stylesheet" href="https://cdn.example.com/a.css">'
                b'<script src="https://cdn.example.com/b.js"></script>'
            )
        return FakeResponse(b"x")

    monkeypatch.setattr(requests, "get", fake_get)
    with pytest.raises(requests.HTTPError):
        download_sim.func(METADATA_JSON, TARGET_VERSION)
    assert not get_sim_html_path(TARGET_VERSION).exists()


# ------------------------------------------------------ warm_mkc_cache_... -----


def run_warm_cache(version: str = TARGET_VERSION) -> str:
    with get_resource_empty_project_path() as empty_project:
        metadata: str = warm_mkc_cache_for_version_and_get_binary_js_metadata.func(
            ContentDir(str(empty_project)), version
        )
    return metadata


def write_binary_js(cwd: Path, text: str) -> None:
    (cwd / "built").mkdir()
    (cwd / "built" / "binary.js").write_text(text, encoding="utf-8")


def test_warm_cache_builds_empty_project_for_version(
    mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}

    def fake_mkc_build(call: CmdCall) -> None:
        # The folder is temporary, so check it while the command is running
        seen["files"] = tree_digest(call.cwd)
        seen["mkc_json"] = json.loads((call.cwd / "mkc.json").read_text("utf-8"))
        write_binary_js(call.cwd, f"// meta={METADATA_JSON}\nrun()\n")

    fake = FakeRunCmd(fake_mkc_build)
    monkeypatch.setattr(install, "run_cmd", fake)

    metadata = run_warm_cache("4.1.27")

    assert [(c.command, c.which_path) for c in fake.calls] == [
        (["mkc", "build", "-j"], get_js_tools_bin_dir())
    ]
    assert seen["mkc_json"] == {"targetWebsite": "https://arcade.makecode.com/v4.1.27"}
    seen["files"].pop("mkc.json")
    with get_resource_empty_project_path() as empty_project:
        assert seen["files"] == tree_digest(empty_project)
    assert json.loads(metadata) == METADATA


def test_warm_cache_cleans_up_temp_dir(
    mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeRunCmd(
        lambda call: write_binary_js(call.cwd, f"// meta={METADATA_JSON}\n")
    )
    monkeypatch.setattr(install, "run_cmd", fake)
    run_warm_cache()
    assert not fake.calls[0].cwd.exists()


def test_warm_cache_raises_and_cleans_up_when_mkc_fails(
    mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_mkc_build(call: CmdCall) -> None:
        raise BuildError(call.command, call.cwd, 1, "compile error")

    fake = FakeRunCmd(failing_mkc_build)
    monkeypatch.setattr(install, "run_cmd", fake)
    with pytest.raises(BuildError):
        run_warm_cache()
    assert not fake.calls[0].cwd.exists()


def test_warm_cache_raises_without_binary_js(
    mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(install, "run_cmd", FakeRunCmd())
    with pytest.raises(FileNotFoundError):
        run_warm_cache()


def test_warm_cache_raises_without_meta_comment(
    mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeRunCmd(lambda call: write_binary_js(call.cwd, "run()\n"))
    monkeypatch.setattr(install, "run_cmd", fake)
    with pytest.raises(ValueError, match="Meta comment not found"):
        run_warm_cache()
