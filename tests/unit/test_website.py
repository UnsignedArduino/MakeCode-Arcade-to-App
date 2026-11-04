import base64
import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest
from helpers import CmdCall, FakeRunCmd, make_config_yaml, tree_digest
from redun import Task
from redun.file import ContentDir, ContentFile

from mkcd2app.build_project import website
from mkcd2app.build_project.website import (
    INDEX_HTML_FAVICON_MARKER,
    INDEX_HTML_TITLE_MARKER,
    build_website,
    build_website_singlefile,
    copy_website_template,
    fill_index_html,
    fill_website_template,
    install_website_deps,
    render_title,
)
from mkcd2app.config import load_config_from_yaml
from mkcd2app.models.config import Project
from mkcd2app.utils.paths import get_templates_npm_cache_dir
from mkcd2app.utils.resources import get_resource_template_path

FAVICON_LINK = '<link rel="icon" href="./favicon.ico" type="image/x-icon" />'
BINARY_JS = "// fake binary.js\n"
SIM_HTML = "<html>fake simulator</html>\n"


@pytest.fixture
def template_dir(tmp_path: Path) -> Path:
    """A copy of the real bundled Vite template, so template drift gets caught."""
    dst = tmp_path / "template"
    with get_resource_template_path("vite-project") as src:
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("node_modules", "dist"))
    return dst


@pytest.fixture
def website_dir(tmp_path: Path, template_dir: Path) -> Path:
    """The template as copy_website_template leaves it in the build dir."""
    dst = tmp_path / "build" / "test-website"
    shutil.copytree(template_dir, dst)
    return dst


def make_support_dir(tmp_path: Path, favicon: bytes | None = None) -> Path:
    support = tmp_path / "build" / "test-binary-js-support"
    support.mkdir(parents=True)
    (support / "---simulator.html").write_text(SIM_HTML, encoding="utf-8")
    if favicon is not None:
        (support / "favicon.ico").write_bytes(favicon)
    return support


def fill(
    tmp_path: Path,
    website_dir: Path,
    favicon: bytes | None = None,
    project: dict[str, Any] | None = None,
) -> Path:
    bin_js = tmp_path / "build" / "test-binary-js-build" / "built" / "binary.js"
    bin_js.parent.mkdir(parents=True)
    bin_js.write_text(BINARY_JS, encoding="utf-8")
    config = load_config_from_yaml(
        make_config_yaml(tmp_path / "build", project=project)
    )
    result: ContentDir = fill_website_template.func(
        config.project.model_dump_json(),
        ContentDir(str(website_dir)),
        ContentFile(str(bin_js)),
        ContentDir(str(make_support_dir(tmp_path, favicon))),
    )
    return Path(result.path)


# ------------------------------------------------- copy_website_template ------


def test_copy_template_to_build_dir(tmp_path: Path, template_dir: Path) -> None:
    dst = tmp_path / "build" / "test-website"
    result: ContentDir = copy_website_template.func(
        str(dst), ContentDir(str(template_dir))
    )
    assert Path(result.path) == dst
    assert tree_digest(dst) == tree_digest(template_dir)


def test_copy_template_replaces_previous_copy(
    tmp_path: Path, template_dir: Path
) -> None:
    stale = tmp_path / "build" / "test-website" / "stale.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("old", encoding="utf-8")
    copy_website_template.func(str(stale.parent), ContentDir(str(template_dir)))
    assert not stale.exists()


# ------------------------------------------------- fill_website_template ------


def test_fill_writes_to_sibling_dir(tmp_path: Path, website_dir: Path) -> None:
    assert fill(tmp_path, website_dir) == tmp_path / "build" / "test-website-filled"


def test_fill_copies_binary_and_simulator(tmp_path: Path, website_dir: Path) -> None:
    assets = fill(tmp_path, website_dir) / "src" / "assets"
    assert (assets / "binary.js").read_text(encoding="utf-8") == BINARY_JS
    assert (assets / "---simulator.html").read_text(encoding="utf-8") == SIM_HTML


def test_fill_sets_default_title(tmp_path: Path, website_dir: Path) -> None:
    index_html = (fill(tmp_path, website_dir) / "index.html").read_text("utf-8")
    assert "<title>Test Game v1.2.3</title>" in index_html
    assert "vite-project" not in index_html


def test_fill_inlines_favicon(tmp_path: Path, website_dir: Path) -> None:
    icon = b"\x00\x00\x01\x00fake icon bytes"
    index_html = (fill(tmp_path, website_dir, icon) / "index.html").read_text("utf-8")
    data_uri = "data:image/x-icon;base64," + base64.b64encode(icon).decode("ascii")
    assert f'<link rel="icon" href="{data_uri}" type="image/x-icon" />' in index_html
    assert "./favicon.ico" not in index_html


def test_fill_without_favicon_keeps_link(tmp_path: Path, website_dir: Path) -> None:
    index_html = (fill(tmp_path, website_dir) / "index.html").read_text("utf-8")
    assert FAVICON_LINK in index_html


def test_fill_updates_package_json(tmp_path: Path, website_dir: Path) -> None:
    original = json.loads((website_dir / "package.json").read_text(encoding="utf-8"))
    filled_path = fill(tmp_path, website_dir) / "package.json"
    filled = json.loads(filled_path.read_text(encoding="utf-8"))
    assert filled["name"] == "test"
    assert filled["version"] == "1.2.3"
    assert filled["description"] == "A test game"
    assert filled["authors"] == {"name": "Tester"}
    # Everything that npm needs to install and build is untouched
    for key in ("scripts", "dependencies", "devDependencies"):
        assert filled.get(key) == original.get(key)


def test_fill_does_not_modify_input(tmp_path: Path, website_dir: Path) -> None:
    before = tree_digest(website_dir)
    fill(tmp_path, website_dir, b"icon")
    assert tree_digest(website_dir) == before


def test_fill_replaces_previous_output(tmp_path: Path, website_dir: Path) -> None:
    stale = tmp_path / "build" / "test-website-filled" / "stale.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("old", encoding="utf-8")
    fill(tmp_path, website_dir)
    assert not stale.exists()


def test_fill_escapes_title(tmp_path: Path, website_dir: Path) -> None:
    filled = fill(tmp_path, website_dir, project={"name": "Tom & Jerry <3"})
    index_html = (filled / "index.html").read_text("utf-8")
    assert "<title>Tom &amp; Jerry &lt;3 v1.2.3</title>" in index_html


def test_fill_title_with_braces_does_not_crash(
    tmp_path: Path, website_dir: Path
) -> None:
    filled = fill(tmp_path, website_dir, project={"title": "My {Game} {NAME}"})
    index_html = (filled / "index.html").read_text("utf-8")
    assert "<title>My {Game} Test Game</title>" in index_html


def test_fill_raises_on_template_without_title(
    tmp_path: Path, website_dir: Path
) -> None:
    index_html = website_dir / "index.html"
    text = index_html.read_text("utf-8")
    assert INDEX_HTML_TITLE_MARKER in text
    index_html.write_text(text.replace(INDEX_HTML_TITLE_MARKER, ""), "utf-8")
    with pytest.raises(RuntimeError, match="vite-project"):
        fill(tmp_path, website_dir)


def test_fill_raises_on_template_without_favicon_link(
    tmp_path: Path, website_dir: Path
) -> None:
    index_html = website_dir / "index.html"
    text = index_html.read_text("utf-8")
    index_html.write_text(text.replace(INDEX_HTML_FAVICON_MARKER, ""), "utf-8")
    with pytest.raises(RuntimeError, match="favicon"):
        fill(tmp_path, website_dir, b"icon")


# ----------------------------------------------------------- render_title -----


def make_project(**overrides: str) -> Project:
    fields = {
        "name": "Racers",
        "path_friendly_name": "racers",
        "author": "me",
        "version": "1.0.0",
        **overrides,
    }
    return Project.model_validate(fields)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("{NAME} v{VERSION}", "Racers v1.0.0"),
        ("{NAME} by {AUTHOR}", "Racers by me"),
        ("{NAME}{NAME}", "RacersRacers"),
        ("Plain title", "Plain title"),
        # Anything that isn't one of the three placeholders is kept literally
        ("My {Game}", "My {Game}"),
        ("Score: {}", "Score: {}"),
        ("{{NAME}}", "{Racers}"),
        ("{NAME:>10}", "{NAME:>10}"),
        ("{NAME.__class__}", "{NAME.__class__}"),
        ("{name}", "{name}"),
        ("{NAME", "{NAME"),
    ],
)
def test_render_title(title: str, expected: str) -> None:
    assert render_title(make_project(title=title)) == expected


def test_render_title_default() -> None:
    assert render_title(make_project()) == "Racers v1.0.0"


def test_render_title_does_not_expand_substituted_values() -> None:
    project = make_project(name="{VERSION}", author="{NAME}")
    assert render_title(project.model_copy(update={"title": "{NAME} {AUTHOR}"})) == (
        "{VERSION} {NAME}"
    )


def test_render_title_does_not_escape_html() -> None:
    # Escaping is fill_index_html's job, after substitution
    assert render_title(make_project(name="A & B")) == "A & B v1.0.0"


# -------------------------------------------------------- fill_index_html -----

MINIMAL_INDEX_HTML = (
    f"<head>{INDEX_HTML_FAVICON_MARKER}{INDEX_HTML_TITLE_MARKER}</head>"
)


def test_fill_index_html_escapes_title() -> None:
    out = fill_index_html(MINIMAL_INDEX_HTML, "</title><script>x</script>")
    assert "<title>&lt;/title&gt;&lt;script&gt;x&lt;/script&gt;</title>" in out


def test_fill_index_html_keeps_quotes_in_title() -> None:
    out = fill_index_html(MINIMAL_INDEX_HTML, 'Say "hi"')
    assert '<title>Say "hi"</title>' in out


def test_fill_index_html_without_favicon_needs_no_link() -> None:
    out = fill_index_html(INDEX_HTML_TITLE_MARKER, "T")
    assert out == "<title>T</title>"


@pytest.mark.parametrize(
    "text",
    ["", INDEX_HTML_TITLE_MARKER * 2, "<title>Something else</title>"],
    ids=["missing", "twice", "renamed"],
)
def test_fill_index_html_requires_title_marker_once(text: str) -> None:
    with pytest.raises(RuntimeError, match="exactly once"):
        fill_index_html(text, "T")


@pytest.mark.parametrize(
    "text",
    [
        INDEX_HTML_TITLE_MARKER,
        INDEX_HTML_TITLE_MARKER + INDEX_HTML_FAVICON_MARKER * 2,
        INDEX_HTML_TITLE_MARKER + '<link rel="icon" href="./favicon.ico">',
    ],
    ids=["missing", "twice", "reformatted"],
)
def test_fill_index_html_requires_favicon_marker_once(text: str) -> None:
    with pytest.raises(RuntimeError, match="exactly once"):
        fill_index_html(text, "T", b"icon")


# -------------------------------------------------- install_website_deps ------


def test_install_deps_runs_offline_npm_ci(
    tmp_path: Path,
    template_dir: Path,
    mkcd2app_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps_dir = tmp_path / "build" / "test-website-deps"
    (deps_dir / "stale.txt").parent.mkdir(parents=True)
    (deps_dir / "stale.txt").write_text("old", encoding="utf-8")

    def fake_npm_ci(call: CmdCall) -> None:
        # The lockfile must already be in place when npm runs
        assert (call.cwd / "package.json").is_file()
        assert (call.cwd / "package-lock.json").is_file()
        (call.cwd / "node_modules").mkdir()

    fake = FakeRunCmd(fake_npm_ci)
    monkeypatch.setattr(website, "run_cmd", fake)

    result: ContentDir = install_website_deps.func(
        str(deps_dir),
        ContentFile(str(template_dir / "package.json")),
        ContentFile(str(template_dir / "package-lock.json")),
    )

    cache = get_templates_npm_cache_dir()
    assert cache.is_relative_to(mkcd2app_home)
    assert [(c.command, c.cwd) for c in fake.calls] == [
        (["npm", "ci", "--cache", str(cache), "--offline"], deps_dir)
    ]
    assert Path(result.path) == deps_dir / "node_modules"
    assert not (deps_dir / "stale.txt").exists()
    for name in ("package.json", "package-lock.json"):
        assert (deps_dir / name).read_bytes() == (template_dir / name).read_bytes()


# --------------------------------------------- build_website(_singlefile) -----


@pytest.fixture
def node_modules(tmp_path: Path) -> Path:
    """A fake node_modules with a relative .bin symlink when the OS allows it."""
    nm = tmp_path / "deps" / "node_modules"
    (nm / "vite" / "bin").mkdir(parents=True)
    (nm / "vite" / "bin" / "vite.js").write_text("// vite", encoding="utf-8")
    (nm / ".bin").mkdir()
    try:
        os.symlink(Path("..") / "vite" / "bin" / "vite.js", nm / ".bin" / "vite")
    except OSError:
        pass  # e.g. Windows without symlink privileges
    return nm


def fake_vite_build(call: CmdCall) -> None:
    # Fails like the real build would if node_modules wasn't copied in
    assert (call.cwd / "node_modules" / "vite" / "bin" / "vite.js").is_file()
    (call.cwd / "dist").mkdir()
    (call.cwd / "dist" / "index.html").write_text("<html>built</html>", "utf-8")


@pytest.mark.parametrize(
    ("task", "script", "suffix", "output"),
    [
        (build_website, "build", "-built", "dist"),
        (build_website_singlefile, "build:singlefile", "-singlefile-built", "dist/index.html"),
    ],
    ids=["static", "singlefile"],
)  # fmt: skip
def test_build_website(
    tmp_path: Path,
    website_dir: Path,
    node_modules: Path,
    monkeypatch: pytest.MonkeyPatch,
    task: Task[..., ContentDir | ContentFile],
    script: str,
    suffix: str,
    output: str,
) -> None:
    fake = FakeRunCmd(fake_vite_build)
    monkeypatch.setattr(website, "run_cmd", fake)
    before = tree_digest(website_dir)

    result: ContentDir | ContentFile = task.func(
        ContentDir(str(website_dir)), ContentDir(str(node_modules))
    )

    built = website_dir.parent / f"{website_dir.name}{suffix}"
    assert [(c.command, c.cwd) for c in fake.calls] == [(["npm", "run", script], built)]
    assert Path(result.path) == built / output
    assert tree_digest(website_dir) == before
    assert not (website_dir / "node_modules").exists()


def test_build_website_keeps_bin_symlinks(
    tmp_path: Path,
    website_dir: Path,
    node_modules: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not (node_modules / ".bin" / "vite").is_symlink():
        pytest.skip("can't create symlinks here")
    monkeypatch.setattr(website, "run_cmd", FakeRunCmd(fake_vite_build))

    build_website.func(ContentDir(str(website_dir)), ContentDir(str(node_modules)))

    link = website_dir.parent / "test-website-built" / "node_modules" / ".bin" / "vite"
    assert link.is_symlink()
    assert os.readlink(link) == str(Path("..") / "vite" / "bin" / "vite.js")


def test_build_website_replaces_previous_output(
    tmp_path: Path,
    website_dir: Path,
    node_modules: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale = website_dir.parent / "test-website-built" / "stale.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("old", encoding="utf-8")
    monkeypatch.setattr(website, "run_cmd", FakeRunCmd(fake_vite_build))

    build_website.func(ContentDir(str(website_dir)), ContentDir(str(node_modules)))

    assert not stale.exists()
