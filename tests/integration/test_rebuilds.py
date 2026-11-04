"""
What a change reruns. Each test builds, makes one change, builds again, and checks
exactly which tasks and commands ran the second time.
"""

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from helpers import GameProject, install_fake_target
from PIL import Image

SITE_TASKS = {"fill_website_template", "build_website", "build_website_singlefile"}
SITE_COMMANDS = ["npm run build", "npm run build:singlefile"]
ALL_TASKS = SITE_TASKS | {
    "build_project",
    "fetch_code",
    "build_binary_js",
    "copy_support_files",
    "copy_website_template",
    "install_website_deps",
}


@dataclass(frozen=True)
class Change:
    id: str
    apply: Callable[[GameProject, Path], None]
    tasks: set[str]
    commands: list[str]


def set_project_field(field: str, value: str) -> Callable[[GameProject, Path], None]:
    def apply(project: GameProject, template: Path) -> None:
        project.config["project"][field] = value
        project.write_config()

    return apply


def add_comment(project: GameProject, template: Path) -> None:
    project.write_config(prefix="# A new comment\n\n")


def add_icon(project: GameProject, template: Path) -> None:
    Image.new("RGBA", (16, 16), (255, 0, 0, 255)).save(project.root / "icon.png")
    project.config["inputs"]["assets"]["icon"] = {"type": "path", "value": "icon.png"}
    project.write_config()


def change_target(project: GameProject, template: Path) -> None:
    install_fake_target("4.1.27")
    project.config["target"] = "4.1.27"
    project.write_config()


def rename_project(project: GameProject, template: Path) -> None:
    project.config["project"]["path_friendly_name"] = "renamed"
    project.write_config()


def change_build_dir(project: GameProject, template: Path) -> None:
    project.config["build_dir"] = "other-build"
    project.write_config()


def remove_singlefile_output(project: GameProject, template: Path) -> None:
    project.config["outputs"] = [{"type": "static"}]
    project.write_config()


def change_template_source(project: GameProject, template: Path) -> None:
    with (template / "src" / "App.tsx").open("a", encoding="utf-8") as f:
        f.write("// edited\n")


def change_template_lockfile(project: GameProject, template: Path) -> None:
    with (template / "package-lock.json").open("a", encoding="utf-8") as f:
        f.write("\n")


def touch_everything(project: GameProject, template: Path) -> None:
    for root in (template, project.root):
        for path in root.rglob("*"):
            if path.is_file() and not path.is_symlink():
                os.utime(path, (1_000_000, 1_000_000))


def edit_path_source(project: GameProject, template: Path) -> None:
    with (project.game / "main.ts").open("a", encoding="utf-8") as f:
        f.write("// edited\n")


CHANGES = [
    Change("comment", add_comment, set(), []),
    Change(
        "title",
        set_project_field("title", "New Title"),
        {"build_project"} | SITE_TASKS,
        SITE_COMMANDS,
    ),
    Change(
        "author",
        set_project_field("author", "Someone Else"),
        {"build_project"} | SITE_TASKS,
        SITE_COMMANDS,
    ),
    Change(
        "project-version",
        set_project_field("version", "9.9.9"),
        {"build_project"} | SITE_TASKS,
        SITE_COMMANDS,
    ),
    Change(
        "description",
        set_project_field("description", "New description"),
        {"build_project"} | SITE_TASKS,
        SITE_COMMANDS,
    ),
    Change(
        "icon",
        add_icon,
        {"build_project", "copy_support_files"} | SITE_TASKS,
        SITE_COMMANDS,
    ),
    Change(
        "target",
        change_target,
        {
            "build_project",
            "fetch_code",
            "build_binary_js",
            "copy_support_files",
        }
        | SITE_TASKS,
        ["mkc build", *SITE_COMMANDS],
    ),
    Change(
        "path-friendly-name",
        rename_project,
        ALL_TASKS,
        ["mkc build", "npm ci", *SITE_COMMANDS],
    ),
    Change(
        "build-dir",
        change_build_dir,
        ALL_TASKS,
        ["mkc build", "npm ci", *SITE_COMMANDS],
    ),
    Change("output-removed", remove_singlefile_output, {"build_project"}, []),
    # build_project reruns too, as the template in its cached result has changed
    Change(
        "template-source",
        change_template_source,
        {"build_project", "copy_website_template"} | SITE_TASKS,
        SITE_COMMANDS,
    ),
    Change(
        "template-lockfile",
        change_template_lockfile,
        {"build_project", "copy_website_template", "install_website_deps"} | SITE_TASKS,
        ["npm ci", *SITE_COMMANDS],
    ),
    Change("mtimes-only", touch_everything, set(), []),
    # By design: only the config is tracked, so this needs --full-rebuild
    Change("path-source-edit", edit_path_source, set(), []),
]


@pytest.mark.parametrize("change", CHANGES, ids=lambda change: change.id)
def test_change_reruns_only_what_depends_on_it(
    project: GameProject, template_dir: Path, change: Change
) -> None:
    project.build()
    change.apply(project, template_dir)
    ran = project.build()
    assert ran.tasks == change.tasks
    assert ran.commands == sorted(change.commands)


# -------------------------------------------------------------- no changes -----


def test_unchanged_rebuild_runs_nothing(project: GameProject) -> None:
    project.build()
    ran = project.build()
    assert ran.tasks == set()
    assert ran.commands == []


def test_running_from_another_directory_runs_nothing(
    project: GameProject, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project.build()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert project.build().tasks == set()
    assert list(elsewhere.iterdir()) == []


def test_relative_config_argument_runs_nothing(
    project: GameProject, monkeypatch: pytest.MonkeyPatch
) -> None:
    project.build()
    monkeypatch.chdir(project.root)
    assert project.cli.run("build", project.config_path.name).tasks == set()


# ------------------------------------------------------------- the results -----


def test_adding_an_output_only_builds_that_output(project: GameProject) -> None:
    project.config["outputs"] = [{"type": "static"}]
    project.write_config()
    project.build()

    project.config["outputs"].append({"type": "static-singlefile"})
    project.write_config()
    ran = project.build()

    assert ran.tasks == {"build_project", "build_website_singlefile"}
    assert ran.commands == ["npm run build:singlefile"]
    assert project.singlefile.is_file()


def test_new_title_reaches_both_outputs(project: GameProject) -> None:
    project.build()
    set_project_field("title", "New Title")(project, Path())
    project.build()
    for output in (project.website, project.singlefile):
        assert "<title>New Title</title>" in output.read_text("utf-8")


def test_new_target_reaches_the_game_and_simulator(
    project: GameProject, template_dir: Path
) -> None:
    project.build()
    change_target(project, template_dir)
    project.build()
    text = project.website.read_text("utf-8")
    assert '"targetVersion": "4.1.27"' in text
    assert "<html>simulator 4.1.27</html>" in text


def test_build_dir_moves_with_the_config(project: GameProject) -> None:
    project.build()
    change_build_dir(project, Path())
    project.build()
    assert (project.root / "other-build" / ".redun-cache.db").is_file()


def test_path_source_edit_is_stale_until_full_rebuild(project: GameProject) -> None:
    project.build()
    before = project.website.read_text("utf-8")
    edit_path_source(project, Path())

    project.build()
    assert project.website.read_text("utf-8") == before

    ran = project.build("--full-rebuild")
    assert ran.tasks == ALL_TASKS
    assert project.website.read_text("utf-8") != before


@pytest.mark.parametrize(
    ("get_output", "delete_parent", "task", "commands"),
    [
        (lambda p: p.website, False, "build_website", ["npm run build"]),
        (lambda p: p.website, True, "build_website", ["npm run build"]),
        (
            lambda p: p.singlefile,
            False,
            "build_website_singlefile",
            ["npm run build:singlefile"],
        ),
        (
            lambda p: p.singlefile,
            True,
            "build_website_singlefile",
            ["npm run build:singlefile"],
        ),
        # Same source, so the same binary.js: nothing after it needs to rerun
        (
            lambda p: p.build_dir / "test-binary-js-build" / "built" / "binary.js",
            False,
            "build_binary_js",
            ["mkc build"],
        ),
    ],
    ids=["static", "static-folder", "singlefile", "singlefile-folder", "binary-js"],
)
def test_deleted_output_is_rebuilt(
    project: GameProject,
    get_output: Callable[[GameProject], Path],
    delete_parent: bool,
    task: str,
    commands: list[str],
) -> None:
    # Regression: a deleted ContentFile crashed the next run instead of rerunning
    project.build()
    output = get_output(project)
    if delete_parent:
        shutil.rmtree(output.parent)
    else:
        output.unlink()
    ran = project.build()
    assert task in ran.tasks
    assert ran.commands == commands
    assert output.is_file()
