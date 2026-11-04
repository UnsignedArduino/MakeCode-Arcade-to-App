"""
What ``build_project`` checks before anything runs. How its tasks are wired together
needs the redun scheduler, since calling a task here only gives an unevaluated
expression.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml
from helpers import TARGET_VERSION, make_config_yaml

from mkcd2app.build_project import BuildProjectResult, build_project
from mkcd2app.config import load_config_from_yaml
from mkcd2app.utils.paths import get_sim_html_path


def config_json(build_dir: Path, *outputs: dict[str, Any]) -> str:
    data = yaml.safe_load(make_config_yaml(build_dir))
    data["outputs"] = list(outputs)
    return load_config_from_yaml(yaml.safe_dump(data)).model_dump_json()


@pytest.fixture
def installed_target(mkcd2app_home: Path) -> None:
    path = get_sim_html_path(TARGET_VERSION)
    path.parent.mkdir(parents=True)
    path.write_text("<html>sim</html>", encoding="utf-8")


@pytest.mark.parametrize(
    ("output", "name"),
    [
        ({"type": "electron"}, "electron"),
        ({"type": "tauri", "identifier": "com.example.game"}, "tauri"),
    ],
    ids=["electron", "tauri"],
)
@pytest.mark.parametrize("with_static", [False, True], ids=["alone", "with-static"])
def test_unimplemented_output_raises(
    tmp_path: Path,
    installed_target: None,
    output: dict[str, Any],
    name: str,
    with_static: bool,
) -> None:
    outputs = [{"type": "static"}, output] if with_static else [output]
    with pytest.raises(NotImplementedError, match=name):
        build_project.func(config_json(tmp_path / "build", *outputs))


@pytest.mark.parametrize(
    ("output", "field"),
    [
        ({"type": "static"}, "static"),
        ({"type": "static-singlefile"}, "static_singlefile"),
    ],
    ids=["static", "static-singlefile"],
)
def test_implemented_outputs_only_fill_their_field(
    tmp_path: Path, installed_target: None, output: dict[str, Any], field: str
) -> None:
    result: BuildProjectResult = build_project.func(
        config_json(tmp_path / "build", output)
    )
    filled = {k for k, v in vars(result).items() if v is not None}
    assert filled == {field}


def test_missing_target_names_the_install_command(
    tmp_path: Path, mkcd2app_home: Path
) -> None:
    with pytest.raises(
        FileNotFoundError, match=f"mkcd2app target install {TARGET_VERSION}"
    ):
        build_project.func(config_json(tmp_path / "build", {"type": "static"}))
