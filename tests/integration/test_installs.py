"""Toolchain and target installs through the real scheduler and ``main()``."""

from html import unescape

import pytest
import requests
from helpers import FAKE_SIM_URL, Cli, FakeResponse, GameProject, install_fake_target

from mkcd2app.utils.paths import (
    get_js_tools_dir,
    get_sim_html_path,
    get_target_version_dir,
    get_templates_npm_cache_dir,
    get_toolchain_dir,
)
from mkcd2app.utils.resources import get_resource_template_path

VERSION = "4.0.14"
SIM_PAGES = {
    FAKE_SIM_URL: b'<html><head><link rel="stylesheet" href="/sim.css"></head>'
    + "<body><p>héllo ✓</p><script src='https://cdn.example.com/sim.js'></script>"
    "</body></html>".encode(),
    "https://sim.example.com/sim.css": "p::after { content: 'é' }".encode(),
    "https://cdn.example.com/sim.js": "run('✓', 1 < 2)".encode(),
}


@pytest.fixture
def sim_requests(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Serve the simulator from fake URLs; return the list of requested URLs."""
    requested: list[str] = []

    def fake_get(url: str) -> FakeResponse:
        requested.append(url)
        return FakeResponse(SIM_PAGES[url])

    monkeypatch.setattr(requests, "get", fake_get)
    return requested


# -------------------------------------------------------------- toolchain -----


def install_commands() -> list[str]:
    """The commands a toolchain install runs: one `npm ci` per template, and the tools."""
    with get_resource_template_path() as templates:
        return ["npm ci"] * (len(list(templates.iterdir())) + 1)


def test_toolchain_install(cli: Cli) -> None:
    ran = cli.run("toolchain", "install")
    assert ran.tasks == {
        "install_toolchain",
        "install_js_tools",
        "warm_npm_cache_for_templates",
    }
    assert ran.commands == install_commands()
    assert (get_js_tools_dir() / "node_modules").is_dir()
    assert list(get_templates_npm_cache_dir().iterdir())


def test_second_toolchain_install_is_cached(cli: Cli) -> None:
    cli.run("toolchain", "install")
    ran = cli.run("toolchain", "install")
    assert ran.tasks == set()
    assert ran.commands == []


def test_toolchain_uninstall_then_install(cli: Cli) -> None:
    cli.run("toolchain", "install")
    cli.run("toolchain", "uninstall")
    assert not get_toolchain_dir().exists()

    ran = cli.run("toolchain", "install")

    assert ran.commands == install_commands()
    assert (get_js_tools_dir() / "node_modules").is_dir()


def test_toolchain_uninstall_when_not_installed_is_fine(cli: Cli) -> None:
    # Regression: this crashed with a FileNotFoundError
    cli.run("toolchain", "uninstall")
    assert not get_toolchain_dir().exists()


def test_toolchain_uninstall_twice_is_fine(cli: Cli) -> None:
    cli.run("toolchain", "install")
    cli.run("toolchain", "uninstall")
    cli.run("toolchain", "uninstall")
    assert not get_toolchain_dir().exists()


# ----------------------------------------------------------------- target -----


def test_target_install_writes_a_self_contained_simulator(
    cli: Cli, sim_requests: list[str]
) -> None:
    ran = cli.run("target", "install", VERSION)

    assert ran.commands == ["mkc build"]
    assert ran.tasks == {
        "install_target",
        "warm_mkc_cache_for_version_and_get_binary_js_metadata",
        "download_sim",
    }
    assert sim_requests == list(SIM_PAGES)
    text = get_sim_html_path(VERSION).read_text(encoding="utf-8")
    assert "src=" not in text and "<link" not in text
    assert "run('✓', 1 < 2)" in text
    assert "p::after { content: 'é' }" in text
    assert "<p>" in text and "héllo ✓" in unescape(text)


def test_second_target_install_is_cached(cli: Cli, sim_requests: list[str]) -> None:
    cli.run("target", "install", VERSION)
    sim_requests.clear()
    ran = cli.run("target", "install", VERSION)
    assert ran.tasks == set()
    assert ran.commands == []
    assert sim_requests == []


def test_target_uninstall_then_install(cli: Cli, sim_requests: list[str]) -> None:
    # Regression: the simulator is a ContentFile, and a deleted one crashed the next run
    cli.run("target", "install", VERSION)
    cli.run("target", "uninstall", VERSION)
    assert not get_target_version_dir(VERSION).exists()
    sim_requests.clear()

    ran = cli.run("target", "install", VERSION)

    assert "download_sim" in ran.tasks
    assert sim_requests == list(SIM_PAGES)
    assert get_sim_html_path(VERSION).is_file()


def test_each_target_version_installs_separately(
    cli: Cli, sim_requests: list[str]
) -> None:
    cli.run("target", "install", VERSION)
    ran = cli.run("target", "install", "4.1.27")
    assert "download_sim" in ran.tasks
    assert get_sim_html_path(VERSION).is_file()
    assert get_sim_html_path("4.1.27").is_file()


def test_target_uninstall_when_not_installed_is_fine(cli: Cli) -> None:
    # Regression: this crashed with a FileNotFoundError
    cli.run("target", "uninstall", VERSION)
    assert not get_target_version_dir(VERSION).exists()


def test_target_uninstall_only_affects_that_version(cli: Cli) -> None:
    install_fake_target(VERSION)
    install_fake_target("4.1.27")
    cli.run("target", "uninstall", VERSION)
    assert not get_sim_html_path(VERSION).exists()
    assert get_sim_html_path("4.1.27").exists()


# ------------------------------------------------------------ all together -----


def test_install_then_build(
    project: GameProject, cli: Cli, sim_requests: list[str]
) -> None:
    # The project fixture installs a fake target, so start from nothing
    get_sim_html_path(VERSION).unlink()
    with pytest.raises(FileNotFoundError, match="target install"):
        project.build()

    cli.run("toolchain", "install")
    cli.run("target", "install", VERSION)
    project.build()

    # The simulator that `target install` made is what ends up in the website
    assert "run('✓', 1 < 2)" in project.website.read_text(encoding="utf-8")
