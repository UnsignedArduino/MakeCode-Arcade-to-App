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


def resolve_config_paths(config: BuildConfig, base_dir: Path) -> BuildConfig:
    """
    Make the paths in a config absolute, so it means the same thing wherever it's run
    from. Done before the config reaches a task, so that the location of a relative
    path is part of what redun hashes.

    :param config: The config. It isn't modified.
    :param base_dir: The directory relative paths are relative to, which is the config
     file's directory. Absolute paths and URLs are left as they are.
    :return: A copy of the config with absolute paths.
    """

    def resolve(path: str) -> str:
        return str((base_dir / path).resolve())

    resolved = config.model_copy(deep=True)
    resolved.build_dir = resolve(resolved.build_dir)
    code = resolved.inputs.code.root
    if isinstance(code, PathCodeSource | FileCodeSource):
        code.value = resolve(code.value)
    icon = resolved.inputs.assets.icon
    if icon is not None and isinstance(icon.root, PathAssetSource):
        icon.root.value = resolve(icon.root.value)
    return resolved
