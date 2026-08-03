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


# Toolchain stuff


def get_toolchain_dir() -> Path:
    return get_user_data_dir() / "toolchain"


def get_redun_db_for_toolchain_path() -> Path:
    return get_user_state_dir() / "redun_db_for_toolchain.sqlite3"


def get_js_tools_dir() -> Path:
    return get_toolchain_dir() / "js_tools"


def get_js_tools_bin_dir() -> Path:
    return get_js_tools_dir() / "node_modules" / ".bin"


def get_templates_npm_cache_dir() -> Path:
    return get_toolchain_dir() / "templates_npm_cache"


# Target stuff


def get_target_dir() -> Path:
    return get_user_data_dir() / "target"


def get_redun_db_for_target_path() -> Path:
    return get_user_state_dir() / "redun_db_for_target.sqlite3"


def get_sim_html_path(v: str) -> Path:
    return get_target_dir() / v / "---simulator.html"
