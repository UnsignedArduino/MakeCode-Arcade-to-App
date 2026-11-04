from pathlib import Path

import pytest
from helpers import CmdCall, FakeRunCmd
from redun.file import ContentDir

from mkcd2app.toolchain import install
from mkcd2app.toolchain.install import install_js_tools, warm_npm_cache_for_templates
from mkcd2app.utils.paths import get_js_tools_dir, get_templates_npm_cache_dir
from mkcd2app.utils.resources import (
    get_resource_js_tools_path,
    get_resource_template_path,
)
from mkcd2app.utils.run import BuildError


def failing_npm(call: CmdCall) -> None:
    raise BuildError(call.command, call.cwd, 1, "npm error")


# ------------------------------------------------------- install_js_tools -----


@pytest.fixture
def js_tools_source(tmp_path: Path) -> Path:
    source = tmp_path / "js_tools"
    source.mkdir()
    (source / "package.json").write_text("package", encoding="utf-8")
    (source / "package-lock.json").write_text("lockfile", encoding="utf-8")
    (source / "other.txt").write_text("not needed", encoding="utf-8")
    return source


def test_install_js_tools_runs_npm_ci_in_tools_dir(
    mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch, js_tools_source: Path
) -> None:
    def check_package_files(call: CmdCall) -> None:
        # Only what npm needs is copied, before npm runs
        assert sorted(p.name for p in call.cwd.iterdir()) == [
            "package-lock.json",
            "package.json",
        ]
        assert (call.cwd / "package-lock.json").read_text("utf-8") == "lockfile"

    fake = FakeRunCmd(check_package_files)
    monkeypatch.setattr(install, "run_cmd", fake)

    result = install_js_tools.func(ContentDir(str(js_tools_source)))

    dest = get_js_tools_dir()
    assert [(c.command, c.cwd) for c in fake.calls] == [(["npm", "ci"], dest)]
    assert Path(result.path) == dest / "node_modules"


def test_install_js_tools_replaces_package_files(
    mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch, js_tools_source: Path
) -> None:
    dest = get_js_tools_dir()
    dest.mkdir(parents=True)
    (dest / "package.json").write_text("old", encoding="utf-8")
    monkeypatch.setattr(install, "run_cmd", FakeRunCmd())
    install_js_tools.func(ContentDir(str(js_tools_source)))
    assert (dest / "package.json").read_text("utf-8") == "package"


def test_install_js_tools_raises_when_npm_fails(
    mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch, js_tools_source: Path
) -> None:
    monkeypatch.setattr(install, "run_cmd", FakeRunCmd(failing_npm))
    with pytest.raises(BuildError):
        install_js_tools.func(ContentDir(str(js_tools_source)))


def test_install_js_tools_with_bundled_tools(
    mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The real package files, so a bundled js_tools without a lockfile gets caught
    monkeypatch.setattr(install, "run_cmd", FakeRunCmd())
    with get_resource_js_tools_path() as js_tools:
        install_js_tools.func(ContentDir(str(js_tools)))
    assert (get_js_tools_dir() / "package-lock.json").is_file()


# ------------------------------------------- warm_npm_cache_for_templates -----


@pytest.fixture
def templates_source(tmp_path: Path) -> Path:
    templates = tmp_path / "templates"
    for name in ("a", "b"):
        (templates / name).mkdir(parents=True)
        (templates / name / "package.json").write_text(name, encoding="utf-8")
    return templates


def test_warm_npm_cache_runs_once_per_template(
    mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch, templates_source: Path
) -> None:
    seen: list[str] = []
    fake = FakeRunCmd(
        lambda call: seen.append((call.cwd / "package.json").read_text("utf-8"))
    )
    monkeypatch.setattr(install, "run_cmd", fake)

    result = warm_npm_cache_for_templates.func(ContentDir(str(templates_source)))

    cache = get_templates_npm_cache_dir()
    assert Path(result.path) == cache
    assert cache.is_dir()
    assert sorted(seen) == ["a", "b"]
    assert [c.command for c in fake.calls] == [
        ["npm", "ci", "--cache", str(cache), "--prefer-online"]
    ] * 2
    assert not any(c.cwd.exists() for c in fake.calls)  # temp dirs are cleaned up


def test_warm_npm_cache_does_not_modify_templates(
    mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch, templates_source: Path
) -> None:
    def write_node_modules(call: CmdCall) -> None:
        (call.cwd / "node_modules").mkdir()

    monkeypatch.setattr(install, "run_cmd", FakeRunCmd(write_node_modules))
    warm_npm_cache_for_templates.func(ContentDir(str(templates_source)))
    assert not list(templates_source.rglob("node_modules"))


def test_warm_npm_cache_raises_and_cleans_up_when_npm_fails(
    mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch, templates_source: Path
) -> None:
    fake = FakeRunCmd(failing_npm)
    monkeypatch.setattr(install, "run_cmd", fake)
    with pytest.raises(BuildError):
        warm_npm_cache_for_templates.func(ContentDir(str(templates_source)))
    assert len(fake.calls) == 1  # stops at the first failure
    assert not fake.calls[0].cwd.exists()


def test_warm_npm_cache_with_bundled_templates(
    mkcd2app_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `npm ci` fails without a lockfile, so a bundled template without one gets caught
    def check_lockfile(call: CmdCall) -> None:
        assert (call.cwd / "package-lock.json").is_file()

    fake = FakeRunCmd(check_lockfile)
    monkeypatch.setattr(install, "run_cmd", fake)
    with get_resource_template_path() as templates:
        warm_npm_cache_for_templates.func(ContentDir(str(templates)))
        assert len(fake.calls) == len(list(templates.iterdir()))
    assert fake.calls
