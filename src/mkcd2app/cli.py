import logging
from argparse import ArgumentParser, Namespace

from mkcd2app.utils.logger import create_logger

logger = create_logger(name=__name__, level=logging.INFO)


def generate_and_parse_args() -> Namespace:
    """
    Parse this CLI tool's arguments.

    :return: A `Namespace` object with parsed CLI arguments.
    """
    parser = ArgumentParser(
        prog="mkcd2app",
        description="Convert your MakeCode Arcade games into a "
        "standalone offline executable!",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging. This must go first before any sub commands.",
    )
    subparsers = parser.add_subparsers(required=True, dest="command")

    parser_build = subparsers.add_parser(
        "build", help="Build your MakeCode Arcade game."
    )
    parser_build.add_argument("config", type=str, help="Path to the YAML config file.")
    parser_build.add_argument(
        "--clear-cache",
        action="store_true",
        help="Delete the entire build directory before building.",
    )

    parser_toolchain = subparsers.add_parser(
        "toolchain", help="Manage the MakeCode CLI toolchain."
    )
    toolchain_subparsers = parser_toolchain.add_subparsers(
        required=True, dest="toolchain_command"
    )
    toolchain_subparsers.add_parser(
        "install",
        help="Install the MakeCode CLI toolchain for this specific mkcd2app version.",
    )
    toolchain_subparsers.add_parser(
        "status", help="Show the installed MakeCode CLI toolchain."
    )
    toolchain_subparsers.add_parser(
        "uninstall",
        help="Uninstall the MakeCode CLI toolchain for this specific mkcd2app version.",
    )

    parser_target = subparsers.add_parser(
        "target", help="Manage MakeCode Arcade target versions."
    )
    target_subparsers = parser_target.add_subparsers(
        required=True, dest="target_command"
    )
    parser_target_install = target_subparsers.add_parser(
        "install", help="Install a MakeCode Arcade target version."
    )
    parser_target_install.add_argument(
        "version", type=str, help="Target version to install."
    )
    target_subparsers.add_parser(
        "list", help="List installed MakeCode Arcade target versions."
    )
    parser_target_uninstall = target_subparsers.add_parser(
        "uninstall", help="Uninstall a MakeCode Arcade target version."
    )
    parser_target_uninstall.add_argument(
        "version", type=str, help="Target version to uninstall."
    )

    args = parser.parse_args()
    logger.debug(f"Received arguments: {args}")
    return args
