import logging
from pathlib import Path

import yaml

from mkcd2app.models.config import (
    BuildConfig,
    FileCodeSource,
    PathAssetSource,
    PathCodeSource,
)
from mkcd2app.utils.logger import create_logger

logger = create_logger(name=__name__, level=logging.INFO)


def load_config_from_yaml(config_text: str) -> BuildConfig:
    """
    Load a config from YAML text.

    :param config_text: The text of the config file, not the path.
    :return: A Config object.
    """
    logger.debug(f"Loading config from {len(config_text)} characters of YAML text")
    data = yaml.safe_load(config_text)

    version = data.get("version") if isinstance(data, dict) else None
    if version == 1:  # only one config version so far
        config = BuildConfig(**data)
    else:
        raise NotImplementedError(f"Unknown config version {version}")
    logger.debug(f"Loaded config version {config.version}")

    return config


def _raise_for_overlapping_source(source: Path, build_dir: Path) -> None:
    """
    Reject a `path` code source that overlaps the build directory. Copying a source
    that contains the build directory would copy the build into itself, and a source
    inside the build directory could be deleted by a build or a full rebuild.

    :param source: The absolute path of the code source.
    :param build_dir: The absolute path of the build directory.
    :raises ValueError: If either directory is inside the other, or they're the same.
    """
    if build_dir.is_relative_to(source):
        raise ValueError(
            f"build_dir {build_dir} is inside the path code source {source}, so the "
            "build would copy itself. Set build_dir to a folder outside the source."
        )
    if source.is_relative_to(build_dir):
        raise ValueError(
            f"The path code source {source} is inside build_dir {build_dir}, so a "
            "build could delete it. Set build_dir to a folder outside the source."
        )


def resolve_config_paths(config: BuildConfig, base_dir: Path) -> BuildConfig:
    """
    Make the paths in a config absolute, so it means the same thing wherever it's run
    from. Done before the config reaches a task, so that the location of a relative
    path is part of what redun hashes.

    :param config: The config. It isn't modified.
    :param base_dir: The directory relative paths are relative to, which is the config
     file's directory. Absolute paths and URLs are left as they are.
    :return: A copy of the config with absolute paths.
    :raises ValueError: If a `path` code source overlaps the build directory.
    """

    def resolve(path: str) -> str:
        return str((base_dir / path).resolve())

    resolved = config.model_copy(deep=True)
    resolved.build_dir = resolve(resolved.build_dir)
    code = resolved.inputs.code.root
    if isinstance(code, PathCodeSource | FileCodeSource):
        code.value = resolve(code.value)
    if isinstance(code, PathCodeSource):
        _raise_for_overlapping_source(Path(code.value), Path(resolved.build_dir))
    icon = resolved.inputs.assets.icon
    if icon is not None and isinstance(icon.root, PathAssetSource):
        icon.root.value = resolve(icon.root.value)
    return resolved
