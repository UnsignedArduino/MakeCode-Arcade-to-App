import logging
from dataclasses import dataclass
from enum import Enum

import yaml

from utils.logger import create_logger

logger = create_logger(name=__name__, level=logging.DEBUG)


class SourceType(Enum):
    GITHUB = "github"
    SHARE_LINK = "share_link"
    PATH = "path"


@dataclass
class Config:
    source: str
    source_type: SourceType


def determine_source_type(source: str) -> SourceType:
    """
    Determines the source type based on the provided source string.

    :param source: The source string.
    :return: The SourceType enum value.
    """
    # We could do more checks for validity
    if "github.com" in source:
        return SourceType.GITHUB
    elif "makecode.com" in source:
        return SourceType.SHARE_LINK
    else:
        return SourceType.PATH


def parse_config(yaml_text: str) -> Config:
    """
    Parses the YAML configuration file and returns a Config object.

    :param yaml_text: The YAML configuration text.
    :return: A Config object.
    """
    logger.debug(f"Parsing YAML configuration")
    result = yaml.safe_load(yaml_text)

    src = result.get("source")
    src_type = determine_source_type(src)
    logger.debug(f"Determined source type for {src} is {src_type}")
    config = Config(
        source=src,
        source_type=src_type
    )
    logger.debug(f"Parsed configuration: {config}")
    return config
