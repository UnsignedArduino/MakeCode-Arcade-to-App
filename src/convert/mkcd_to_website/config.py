import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import yaml

from utils.logger import create_logger

logger = create_logger(name=__name__, level=logging.INFO)


class SourceType(Enum):
    GITHUB = "github"
    SHARE_LINK = "share_link"
    PATH = "path"


class IconSourceType(Enum):
    PATH = "path"
    URL = "url"


class OutputType(Enum):
    STATIC = "static"
    ELECTRON = "electron"
    TAURI = "tauri"


@dataclass
class Config:
    """
    Configuration class.
    """
    name: str
    description: str
    author: str
    version: str
    title: str

    source: str
    source_type: SourceType
    source_checkout: Optional[str] = None  # For GitHub sources

    icon: Optional[Path | str] = None
    icon_source_type: Optional[IconSourceType] = None

    output: OutputType = OutputType.STATIC


# https://stackoverflow.com/a/36283503/10291933
def is_valid_url(url, qualifying=('scheme', 'netloc')):
    tokens = urlparse(url)
    return all(getattr(tokens, qualifying_attr)
               for qualifying_attr in qualifying)


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
    elif is_valid_url(source):
        return SourceType.SHARE_LINK
    else:
        return SourceType.PATH


def determine_icon_source_type(icon: str) -> IconSourceType:
    """
    Determines the icon source type based on the provided icon string.

    :param icon: The icon string.
    :return: The IconSourceType enum value.
    """
    # We could do more checks for validity / strictness here
    if is_valid_url(icon):
        return IconSourceType.URL
    else:
        return IconSourceType.PATH


def parse_config(yaml_text: str, cwd: Path) -> Config:
    """
    Parses the YAML configuration file and returns a Config object.

    :param yaml_text: The YAML configuration text.
    :param cwd: The current working directory to resolve relative paths.
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

    icon = result.get("icon")
    icon_source_type = None if icon is None else determine_icon_source_type(icon)
    if icon_source_type == IconSourceType.PATH:
        icon = Path(icon)
        if not icon.is_absolute():
            icon = cwd / icon
    logger.debug(f"Determined icon source type for {icon} is {icon_source_type}")

    config = Config(
        name=result.get("name"),
        description=result.get("description"),
        author=result.get("author"),
        version=result.get("version"),
        title=result.get("title"),
        source=src,
        source_type=src_type,
        source_checkout=src_checkout,
        icon=icon,
        icon_source_type=icon_source_type,
        output=OutputType(result.get("output", "static").lower())
    )
    config.title = config.title.format(NAME=config.name, VERSION=config.version, AUTHOR=config.author)
    logger.debug(f"Parsed configuration: {config}")
    return config
