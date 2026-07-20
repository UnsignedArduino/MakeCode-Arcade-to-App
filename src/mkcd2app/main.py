import logging
from argparse import ArgumentParser
from pathlib import Path

import redun
from redun import Scheduler

from mkcd2app.build_project import build_project
from mkcd2app.config import load_config_from_yaml
from mkcd2app.utils.logger import create_logger, set_all_stdout_logger_levels

logger = create_logger(name=__name__, level=logging.INFO)


def main():
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

    args = parser.parse_args()
    debug = bool(args.debug)
    if debug:
        set_all_stdout_logger_levels(logging.DEBUG)
    logger.debug(f"Received arguments: {args}")

    if args.command == "build":
        logger.debug("Building project")

        config_path = Path(args.config)
        logger.debug(f"Loading config from {config_path}")
        config_text = config_path.read_text()
        config = load_config_from_yaml(config_text)

        # noinspection PyUnresolvedReferences
        redun_config = redun.config.Config({"scheduler": {"log_level": "DEBUG"}})
        scheduler = Scheduler(config=redun_config)
        result = scheduler.run(
            build_project(config),
        )

        logger.debug(f"Build finished, result is at {result}")


if __name__ == "__main__":
    main()
