from pathlib import Path
from typing import Any

import pytest
import yaml
from helpers import make_config_yaml
from pydantic import ValidationError

from mkcd2app.config import load_config_from_yaml, resolve_config_paths
from mkcd2app.models.config import (
    AssetSource,
    BuildConfig,
    CodeSource,
    ElectronOutput,
    FileCodeSource,
    PathAssetSource,
    PathCodeSource,
    Project,
    TauriOutput,
    UrlAssetSource,
    WindowConfig,
)


def base_config() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(make_config_yaml(Path("build")))
    return data


def load(data: object) -> BuildConfig:
    return load_config_from_yaml(yaml.safe_dump(data))


def load_outputs(*outputs: dict[str, Any]) -> list[Any]:
    data = base_config()
    data["outputs"] = list(outputs)
    return [output.root for output in load(data).outputs]


# --------------------------------------------------------- config version -----


@pytest.mark.parametrize("version", [0, 2, "1", None])
def test_unknown_version(version: object) -> None:
    data = base_config()
    data["version"] = version
    with pytest.raises(NotImplementedError, match="Unknown config version"):
        load(data)


def test_missing_version() -> None:
    data = base_config()
    del data["version"]
    with pytest.raises(NotImplementedError, match="Unknown config version None"):
        load(data)


@pytest.mark.parametrize("text", ["", "# only a comment\n", "- a\n- b\n", "just text"])
def test_empty_or_non_mapping_yaml(text: str) -> None:
    with pytest.raises(NotImplementedError, match="Unknown config version None"):
        load_config_from_yaml(text)


# ------------------------------------------------------------ valid config -----


def test_valid_config() -> None:
    config = load(base_config())
    assert config.version == 1
    assert config.project.name == "Test Game"
    assert config.build_dir == "build"
    assert config.target == "4.0.14"


def test_project_title_has_default() -> None:
    assert load(base_config()).project.title == "{NAME} v{VERSION}"


@pytest.mark.parametrize("key", ["description", "title"])
def test_optional_project_fields(key: str) -> None:
    data = base_config()
    data["project"].pop(key, None)
    load(data)


def test_icon_is_optional() -> None:
    assert load(base_config()).inputs.assets.icon is None


# ---------------------------------------------------------- required fields -----


@pytest.mark.parametrize("key", ["project", "inputs", "build_dir", "target", "outputs"])
def test_missing_top_level_field(key: str) -> None:
    data = base_config()
    del data[key]
    with pytest.raises(ValidationError, match=key):
        load(data)


@pytest.mark.parametrize("key", ["name", "path_friendly_name", "author", "version"])
def test_missing_project_field(key: str) -> None:
    data = base_config()
    del data["project"][key]
    with pytest.raises(ValidationError, match=key):
        load(data)


@pytest.mark.parametrize("key", ["code", "assets"])
def test_missing_inputs_field(key: str) -> None:
    data = base_config()
    del data["inputs"][key]
    with pytest.raises(ValidationError, match=key):
        load(data)


# ------------------------------------------------------- path_friendly_name -----


@pytest.mark.parametrize(
    "name", ["racers", "empty-game", "game_2", "v1.2", "9lives", "a" * 64]
)
def test_valid_path_friendly_name(name: str) -> None:
    data = base_config()
    data["project"]["path_friendly_name"] = name
    assert load(data).project.path_friendly_name == name


@pytest.mark.parametrize(
    "name",
    [
        # Would escape build_dir
        "../victim",
        "..",
        ".",
        "a/b",
        "a\\b",
        "/abs",
        "C:evil",
        "C:\\evil",
        # Not allowed in an npm package name
        "",
        "Racers",
        "my game",
        ".hidden",
        "_private",
        "-flag",
        "@scope/pkg",
        "racers\n",
        "a" * 65,
        # Reserved on Windows, whichever OS the config is loaded on
        "con",
        "nul",
        "com1",
        "con.txt",
        "trailing.",
    ],
)
def test_invalid_path_friendly_name(name: str) -> None:
    data = base_config()
    data["project"]["path_friendly_name"] = name
    with pytest.raises(ValidationError, match="path_friendly_name"):
        load(data)


# -------------------------------------------------------------- unknown keys -----


def add_key(data: dict[str, Any], *path: str | int) -> None:
    section: Any = data
    for key in path:
        section = section[key]
    section["typo"] = "oops"


@pytest.mark.parametrize(
    "path",
    [
        (),
        ("project",),
        ("inputs",),
        ("inputs", "code"),
        ("inputs", "assets"),
        ("outputs", 0),
    ],
    ids=str,
)
def test_unknown_key_is_rejected(path: tuple[str | int, ...]) -> None:
    data = base_config()
    add_key(data, *path)
    with pytest.raises(ValidationError, match="typo"):
        load(data)


def test_misspelled_key_is_rejected_instead_of_using_the_default() -> None:
    data = base_config()
    data["project"]["titel"] = "My Game"
    with pytest.raises(ValidationError, match="titel"):
        load(data)


def test_unknown_key_in_icon_is_rejected() -> None:
    data = base_config()
    data["inputs"]["assets"]["icon"] = {"type": "path", "value": "i.png", "typo": 1}
    with pytest.raises(ValidationError, match="typo"):
        load(data)


def test_unknown_key_in_window_is_rejected() -> None:
    with pytest.raises(ValidationError, match="depth"):
        load_outputs({"type": "electron", "window": {"depth": 32}})


# ------------------------------------------------------------------ outputs -----


def test_empty_outputs_are_rejected() -> None:
    with pytest.raises(ValidationError, match="outputs"):
        load_outputs()


def test_unknown_output_type_is_rejected() -> None:
    with pytest.raises(ValidationError, match="nonsense"):
        load_outputs({"type": "nonsense"})


def test_tauri_requires_identifier() -> None:
    with pytest.raises(ValidationError, match="identifier"):
        load_outputs({"type": "tauri"})


def test_tauri_with_identifier() -> None:
    [output] = load_outputs({"type": "tauri", "identifier": "com.example.game"})
    assert isinstance(output, TauriOutput)
    assert output.identifier == "com.example.game"
    assert output.window is None


def test_electron_window_is_optional() -> None:
    [output] = load_outputs({"type": "electron"})
    assert isinstance(output, ElectronOutput)
    assert output.window is None


def test_window_config_defaults() -> None:
    assert WindowConfig() == WindowConfig(width=640, height=480)


def test_window_config_fills_in_missing_side() -> None:
    [output] = load_outputs({"type": "electron", "window": {"width": 800}})
    assert output.window == WindowConfig(width=800, height=480)


# ------------------------------------------------------------- code sources -----


def test_unknown_code_source_type_is_rejected() -> None:
    data = base_config()
    data["inputs"]["code"] = {"type": "ftp", "value": "ftp://example.com"}
    with pytest.raises(ValidationError, match="ftp"):
        load(data)


def test_unknown_icon_source_type_is_rejected() -> None:
    data = base_config()
    data["inputs"]["assets"]["icon"] = {"type": "ftp", "value": "ftp://example.com"}
    with pytest.raises(ValidationError, match="ftp"):
        load(data)


# ---------------------------------------------------- resolve_config_paths -----


def load_with_paths(
    code: dict[str, Any], icon: dict[str, Any] | None = None, build_dir: str = "build"
) -> BuildConfig:
    data = base_config()
    data["inputs"]["code"] = code
    if icon:
        data["inputs"]["assets"]["icon"] = icon
    data["build_dir"] = build_dir
    return load(data)


@pytest.mark.parametrize(
    "code_type",
    [("path", PathCodeSource), ("file", FileCodeSource)],
    ids=lambda t: t[0],
)
def test_resolve_makes_relative_paths_absolute(
    tmp_path: Path, code_type: tuple[str, type[PathCodeSource | FileCodeSource]]
) -> None:
    name, source_type = code_type
    config = load_with_paths(
        {"type": name, "value": "./game"},
        {"type": "path", "value": "assets/icon.png"},
        "./out/build",
    )

    resolved = resolve_config_paths(config, tmp_path)

    base = tmp_path.resolve()
    assert resolved.build_dir == str(base / "out" / "build")
    assert resolved.inputs.code.root == source_type(
        type=name,  # type: ignore[arg-type]
        value=str(base / "game"),
    )
    assert resolved.inputs.assets.icon is not None
    assert resolved.inputs.assets.icon.root == PathAssetSource(
        type="path", value=str(base / "assets" / "icon.png")
    )


def test_resolve_follows_parent_directories(tmp_path: Path) -> None:
    config = load_with_paths({"type": "path", "value": "../game"}, None, "../../build")
    base = tmp_path / "a" / "b"
    resolved = resolve_config_paths(config, base)
    assert resolved.build_dir == str((tmp_path / "build").resolve())
    assert resolved.inputs.code.root == PathCodeSource(
        type="path", value=str((tmp_path / "a" / "game").resolve())
    )


def test_resolve_keeps_absolute_paths(tmp_path: Path) -> None:
    game = (tmp_path / "elsewhere" / "game").resolve()
    build = (tmp_path / "elsewhere" / "build").resolve()
    config = load_with_paths({"type": "path", "value": str(game)}, None, str(build))
    resolved = resolve_config_paths(config, tmp_path / "config-dir")
    assert resolved.build_dir == str(build)
    assert resolved.inputs.code.root == PathCodeSource(type="path", value=str(game))


@pytest.mark.parametrize(
    "code",
    [
        {"type": "share_link", "value": "https://arcade.makecode.com/S12345/"},
        {"type": "git", "url": "https://github.com/a/b", "ref": "main"},
        {"type": "git", "url": "file:///a/b"},
        {"type": "github", "value": "https://github.com/a/b"},
    ],
    ids=lambda code: code["type"],
)
def test_resolve_leaves_urls_alone(tmp_path: Path, code: dict[str, Any]) -> None:
    icon = {"type": "url", "value": "https://example.com/icon.png"}
    config = load_with_paths(code, icon)
    resolved = resolve_config_paths(config, tmp_path)
    assert resolved.inputs.code == config.inputs.code
    assert resolved.inputs.assets.icon is not None
    assert isinstance(resolved.inputs.assets.icon.root, UrlAssetSource)
    assert resolved.inputs.assets.icon == config.inputs.assets.icon


def test_resolve_does_not_modify_the_config(tmp_path: Path) -> None:
    config = load_with_paths(
        {"type": "path", "value": "game"}, {"type": "path", "value": "icon.png"}
    )
    before = config.model_dump_json()
    resolve_config_paths(config, tmp_path)
    assert config.model_dump_json() == before


def test_resolve_does_not_depend_on_the_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = load_with_paths({"type": "path", "value": "game"})
    results = []
    for cwd in (tmp_path / "one", tmp_path / "two"):
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        results.append(resolve_config_paths(config, tmp_path).model_dump_json())
    assert results[0] == results[1]


# ------------------------------------------------- the JSON tasks are given -----


def test_comments_and_formatting_do_not_change_the_json() -> None:
    data = base_config()
    plain = yaml.safe_dump(data)
    reformatted = "# A comment\n\n" + yaml.safe_dump(data, sort_keys=False, indent=4)
    assert plain != reformatted
    assert (
        load_config_from_yaml(plain).model_dump_json()
        == load_config_from_yaml(reformatted).model_dump_json()
    )


@pytest.mark.parametrize(
    "code",
    [
        {"type": "share_link", "value": "https://arcade.makecode.com/S12345/"},
        {"type": "git", "url": "https://github.com/a/b", "ref": "main"},
        {"type": "github", "value": "https://github.com/a/b", "checkout": "dev"},
        {"type": "path", "value": "game"},
        {"type": "file", "value": "game.png"},
    ],
    ids=lambda code: code["type"],
)
def test_config_and_its_parts_survive_json(code: dict[str, Any]) -> None:
    icon = {"type": "url", "value": "https://example.com/icon.png"}
    config = load_with_paths(code, icon)
    assert BuildConfig.model_validate_json(config.model_dump_json()) == config
    assert (
        CodeSource.model_validate_json(config.inputs.code.model_dump_json())
        == config.inputs.code
    )
    assert config.inputs.assets.icon is not None
    assert (
        AssetSource.model_validate_json(config.inputs.assets.icon.model_dump_json())
        == config.inputs.assets.icon
    )
    assert (
        Project.model_validate_json(config.project.model_dump_json()) == config.project
    )
