import logging
from argparse import ArgumentParser, Namespace

from mkcd2app.utils.logger import create_logger

logger = create_logger(name=__name__, level=logging.INFO)


def generate_and_parse_args() -> Namespace:
    """
    Parse this CLI tool's arguments.

    :return: A `Namespace` object with parsed CLI arguments.
    """
    parser = ArgumentParser(description="Convert your MakeCode Arcade games into a "
                                        "standalone offline executable!")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug logging. This must go first before the sub "
                             "command.")
    subparsers = parser.add_subparsers(required=True, dest="command")
    # build subcommand
    parser_build = subparsers.add_parser("build",
                                         help="Build your MakeCode Arcade game.")
    parser_build.add_argument("config", type=str, help="Path to the YAML config file.")
    parser_build.add_argument("--clear-cache", action="store_true",
                              help="Delete the entire build directory before building.")

    args = parser.parse_args()
    logger.debug(f"Received arguments: {args}")
    return args
