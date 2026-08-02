from importlib.metadata import version
from pathlib import Path

from platformdirs import PlatformDirs


def get_mkcd2app_version() -> str:
    return version("mkcd2app")


DIRS = PlatformDirs("mkcd2app", appauthor=False)


def get_user_data_dir() -> Path:
    return Path(DIRS.user_data_dir) / get_mkcd2app_version()


def get_user_state_dir() -> Path:
    return Path(DIRS.user_state_dir) / get_mkcd2app_version()


def get_toolchain_dir() -> Path:
    return get_user_data_dir() / "toolchain"


def get_redun_db_for_toolchain_path() -> Path:
    return get_user_state_dir() / "redun_db_for_toolchain.sqlite3"


def get_js_tools_dir() -> Path:
    return get_toolchain_dir() / "js_tools"


def get_templates_npm_cache_dir() -> Path:
    return get_toolchain_dir() / "templates_npm_cache"
