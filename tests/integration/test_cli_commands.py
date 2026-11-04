"""The real ``main()``, from arguments to tasks, with only `mkc` and `npm` faked."""

import logging
from pathlib import Path

import pytest
from helpers import Cli, FakeToolchain, GameProject, TaskSpy
from pydantic import ValidationError

from mkcd2app.utils.paths import get_sim_html_path


def assert_nothing_ran(fake_toolchain: FakeToolchain, task_spy: TaskSpy) -> None:
    assert fake_toolchain.commands == []
    assert task_spy.ran == []


# --------------------------------------------------------------- arguments -----


@pytest.mark.parametrize("command", ["install", "uninstall"])
@pytest.mark.parametrize("version", ["4.0", "v4.0.14", "4.0.14-beta", "latest"])
def test_target_version_must_be_strict_semver(
    cli: Cli,
    fake_toolchain: FakeToolchain,
    task_spy: TaskSpy,
    command: str,
    version: str,
) -> None:
    with pytest.raises(ValueError, match="strict numeric semver"):
        cli.run("target", command, version)
    assert_nothing_ran(fake_toolchain, task_spy)


@pytest.mark.parametrize("argv", [("toolchain", "status"), ("target", "list")])
def test_stub_commands_run_nothing(cli: Cli, argv: tuple[str, ...]) -> None:
    ran = cli.run(*argv)
    assert ran.tasks == set()
    assert ran.commands == []


def test_debug_turns_on_debug_logging(
    project: GameProject, restore_log_levels: None
) -> None:
    logger = logging.getLogger("mkcd2app.main")
    assert logger.level == logging.INFO
    project.cli.run("--debug", "build", str(project.config_path))
    assert logger.level == logging.DEBUG


# ------------------------------------------------------------------ configs -----


def test_missing_config_file(
    cli: Cli, tmp_path: Path, fake_toolchain: FakeToolchain, task_spy: TaskSpy
) -> None:
    with pytest.raises(FileNotFoundError):
        cli.run("build", str(tmp_path / "missing.yaml"))
    assert_nothing_ran(fake_toolchain, task_spy)


def test_unknown_config_version(
    project: GameProject, fake_toolchain: FakeToolchain, task_spy: TaskSpy
) -> None:
    project.config["version"] = 2
    project.write_config()
    with pytest.raises(NotImplementedError, match="Unknown config version 2"):
        project.build()
    assert_nothing_ran(fake_toolchain, task_spy)
    assert not project.build_dir.exists()


def test_unknown_config_key(
    project: GameProject, fake_toolchain: FakeToolchain, task_spy: TaskSpy
) -> None:
    project.config["project"]["titel"] = "Typo"
    project.write_config()
    with pytest.raises(ValidationError, match="titel"):
        project.build()
    assert_nothing_ran(fake_toolchain, task_spy)


@pytest.mark.parametrize(
    "output",
    [{"type": "electron"}, {"type": "tauri", "identifier": "com.example.game"}],
    ids=["electron", "tauri"],
)
def test_unimplemented_output_builds_nothing(
    project: GameProject,
    fake_toolchain: FakeToolchain,
    task_spy: TaskSpy,
    output: dict[str, str],
) -> None:
    project.config["outputs"].append(output)
    project.write_config()
    with pytest.raises(NotImplementedError, match=output["type"]):
        project.build()
    assert fake_toolchain.commands == []
    assert not project.website.exists()


def test_target_not_installed_builds_nothing(
    project: GameProject, fake_toolchain: FakeToolchain
) -> None:
    get_sim_html_path("4.0.14").unlink()
    with pytest.raises(FileNotFoundError, match="mkcd2app target install 4.0.14"):
        project.build()
    assert fake_toolchain.commands == []


# ---------------------------------------------------------- --full-rebuild -----


def test_full_rebuild_clears_the_build_dir_and_reruns_everything(
    project: GameProject,
) -> None:
    project.build()
    stale = project.build_dir / "stale.txt"
    stale.write_text("left over", encoding="utf-8")

    ran = project.build("--full-rebuild")

    assert not stale.exists()
    assert (project.build_dir / ".redun-cache.db").is_file()
    assert "fetch_code" in ran.tasks
    assert "mkc build" in ran.commands and "npm ci" in ran.commands
    assert project.website.is_file()


def test_full_rebuild_with_no_previous_build(project: GameProject) -> None:
    assert not project.build_dir.exists()
    assert project.build("--full-rebuild").commands
    assert project.website.is_file()


def test_full_rebuild_refuses_a_folder_that_is_not_a_build_dir(
    project: GameProject, fake_toolchain: FakeToolchain, task_spy: TaskSpy
) -> None:
    # `build_dir: "."`, say: this would delete the game and the config
    project.config["build_dir"] = "."
    project.write_config()
    with pytest.raises(RuntimeError, match="Refusing to clear"):
        project.build("--full-rebuild")
    assert_nothing_ran(fake_toolchain, task_spy)
    assert project.config_path.is_file()
    assert (project.game / "main.ts").is_file()
