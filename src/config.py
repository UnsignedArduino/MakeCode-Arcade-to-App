import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import yaml

from utils.logger import create_logger

logger = create_logger(name=__name__, level=logging.DEBUG)


class SourceType(Enum):
    GITHUB = "github"
    SHARE_LINK = "share_link"
    PATH = "path"


@dataclass
class Config:
    """
    Configuration class.
    """
    name: str
    description: str
    author: str
    version: str

    source: str
    source_type: SourceType
    source_checkout: Optional[str] = None  # For complex GitHub sources


def determine_source_type(source: str | dict) -> SourceType:
    """
    Determines the source type based on the provided source string.

    :param source: The source string or dictionary.
    :return: The SourceType enum value.
    """
    # We could do more checks for validity / strictness here
    if type(source) is not str:
        # Should have url and checkout
        return SourceType.GITHUB
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
    src_checkout = None
    if type(src) is not str:
        src_checkout = src.get("checkout")
        src = src.get("url")
        logger.debug(f"Complex GitHub source detected - will checkout {src_checkout} "
                     f"for url {src}")

    config = Config(
        name=result.get("name"),
        description=result.get("description"),
        author=result.get("author"),
        version=result.get("version"),
        source=src,
        source_type=src_type,
        source_checkout=src_checkout
    )
    logger.debug(f"Parsed configuration: {config}")
    return config
