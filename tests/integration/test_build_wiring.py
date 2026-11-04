"""The real task graph through the real scheduler, with only `mkc` and `npm` faked."""

import sys
from pathlib import Path

import pytest
import requests
from helpers import (
    FakeResponse,
    FakeToolchain,
    GameProject,
    TaskSpy,
    current_contents,
)
from PIL import Image

from mkcd2app.build_project import BuildProjectResult, build_project
from mkcd2app.config import load_config_from_yaml, resolve_config_paths
from mkcd2app.utils.paths import get_redun_db_for_build_path
from mkcd2app.utils.run import BuildError
from mkcd2app.utils.run_redun_task import run_redun_task

ALL_TASKS = {
    "build_project",
    "fetch_code",
    "build_binary_js",
    "copy_support_files",
    "copy_website_template",
    "fill_website_template",
    "install_website_deps",
    "build_website",
    "build_website_singlefile",
}
ALL_COMMANDS = ["mkc build", "npm ci", "npm run build", "npm run build:singlefile"]


def build_for_result(project: GameProject) -> BuildProjectResult:
    """Build like main() does, but keep the result, which main() only logs."""
    config = resolve_config_paths(
        load_config_from_yaml(project.config_path.read_text("utf-8")), project.root
    )
    result: BuildProjectResult = run_redun_task(
        build_project(config.model_dump_json()),
        get_redun_db_for_build_path(project.build_dir),
    )
    return result


# ----------------------------------------------------------------- wiring -----


def test_full_build_runs_every_task_once(
    project: GameProject, task_spy: TaskSpy
) -> None:
    ran = project.build()
    assert sorted(task_spy.ran) == sorted(ALL_TASKS)
    assert ran.commands == ALL_COMMANDS  # includes one `npm ci`, shared by both
    assert project.website.is_file()
    assert project.singlefile.is_file()


def test_result_fields_point_at_the_outputs(project: GameProject) -> None:
    result = build_for_result(project)
    assert result.static is not None and result.static_singlefile is not None
    assert Path(result.static.path) == project.website.parent
    assert Path(result.static_singlefile.path) == project.singlefile
    assert result.electron is None and result.tauri is None


def test_only_static_requested(
    project: GameProject, fake_toolchain: FakeToolchain
) -> None:
    project.config["outputs"] = [{"type": "static"}]
    project.write_config()
    result = build_for_result(project)
    assert result.static is not None and result.static_singlefile is None
    assert sorted(fake_toolchain.commands) == ["mkc build", "npm ci", "npm run build"]
    assert not project.singlefile.exists()


def test_only_singlefile_requested(
    project: GameProject, fake_toolchain: FakeToolchain
) -> None:
    project.config["outputs"] = [{"type": "static-singlefile"}]
    project.write_config()
    result = build_for_result(project)
    assert result.static is None and result.static_singlefile is not None
    assert sorted(fake_toolchain.commands) == [
        "mkc build",
        "npm ci",
        "npm run build:singlefile",
    ]
    assert not project.website.exists()


def test_game_project_details_reach_the_website(project: GameProject) -> None:
    project.config["project"]["title"] = "My Game"
    project.write_config()
    project.build()
    for output in (project.website, project.singlefile):
        text = output.read_text("utf-8")
        assert "<title>My Game</title>" in text
        assert "// built from" in text  # binary.js
        assert "<html>simulator 4.0.14</html>" in text


def test_path_icon_relative_to_the_config_reaches_the_website(
    project: GameProject,
) -> None:
    Image.new("RGBA", (16, 16), (255, 0, 0, 255)).save(project.root / "icon.png")
    project.config["inputs"]["assets"]["icon"] = {"type": "path", "value": "icon.png"}
    project.write_config()
    project.build()
    assert "data:image/x-icon;base64," in project.website.read_text("utf-8")


def test_url_icon_reaches_the_website(
    project: GameProject, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    png = tmp_path / "served.png"
    Image.new("RGBA", (16, 16), (0, 255, 0, 255)).save(png)
    monkeypatch.setattr(requests, "get", lambda url: FakeResponse(png.read_bytes()))
    project.config["inputs"]["assets"]["icon"] = {
        "type": "url",
        "value": "https://example.com/icon.png",
    }
    project.write_config()
    project.build()
    assert "data:image/x-icon;base64," in project.website.read_text("utf-8")


def test_share_link_source(project: GameProject) -> None:
    url = "https://arcade.makecode.com/S12345-67890-12345-67890"
    project.config["inputs"]["code"] = {"type": "share_link", "value": url}
    project.write_config()
    ran = project.build()
    assert ran.commands == sorted([*ALL_COMMANDS, "mkc download"])
    source = project.build_dir / "test-source" / "main.ts"
    assert url in source.read_text("utf-8")


def test_outputs_built_from_a_file_source(project: GameProject) -> None:
    fixtures = Path(__file__).parent.parent / "fixtures" / "embedded"
    project.config["inputs"]["code"] = {
        "type": "file",
        "value": str(fixtures / "empty-game.png"),
    }
    project.write_config()
    project.build()
    assert (project.build_dir / "test-source" / "pxt.json").is_file()
    assert project.website.is_file()


@pytest.mark.skipif(sys.platform == "win32", reason="the fake npm makes no symlinks")
def test_node_modules_symlinks_stay_symlinks(project: GameProject) -> None:
    # Regression: copying their targets breaks the scripts' relative imports
    project.build()
    tool = project.website.parent.parent / "node_modules" / ".bin" / "tool"
    assert tool.is_symlink()
    assert tool.resolve().is_file()


# ----------------------------------------------------------- copy-on-write -----


def test_no_task_changes_what_another_task_returned(
    project: GameProject, task_spy: TaskSpy
) -> None:
    project.build()
    assert len(task_spy.returned) == len(ALL_TASKS) - 1  # all but build_project
    for path, contents in task_spy.returned.items():
        assert current_contents(path) == contents, f"{path} changed after it returned"


def test_mkc_builds_outside_the_fetched_source(project: GameProject) -> None:
    project.build()
    assert not (project.build_dir / "test-source" / "built").exists()
    assert (
        project.build_dir / "test-binary-js-build" / "built" / "binary.js"
    ).is_file()


# ------------------------------------------------------- failure and retry -----


@pytest.mark.parametrize(
    ("command", "task"),
    [
        ("mkc build", "build_binary_js"),
        ("npm ci", "install_website_deps"),
        ("npm run build", "build_website"),
        ("npm run build:singlefile", "build_website_singlefile"),
    ],
)
def test_failed_command_raises_and_the_next_build_retries_it(
    project: GameProject, fake_toolchain: FakeToolchain, command: str, task: str
) -> None:
    fake_toolchain.failing.add(command)
    with pytest.raises(BuildError) as exc:
        project.build()
    assert exc.value.output == f"fake {command} output"

    fake_toolchain.failing.clear()
    assert task in project.build().tasks  # the failure wasn't cached
    assert project.website.is_file() and project.singlefile.is_file()
    assert project.build().tasks == set()


def test_finished_tasks_stay_cached_after_a_failure(
    project: GameProject, fake_toolchain: FakeToolchain
) -> None:
    # fetch_code has to finish before `mkc build` can run
    fake_toolchain.failing.add("mkc build")
    with pytest.raises(BuildError):
        project.build()

    fake_toolchain.failing.clear()
    ran = project.build()
    assert "fetch_code" not in ran.tasks
    assert "build_binary_js" in ran.tasks
