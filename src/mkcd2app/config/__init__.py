import logging

import yaml

from mkcd2app.config.model import BuildConfig
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

    if data["version"] == 1:  # only one config version so far
        config = BuildConfig(**data)
    else:
        raise NotImplementedError(f"Unknown config version {data.version}")
    logger.debug(f"Loaded config version {config.version}")

    return config
