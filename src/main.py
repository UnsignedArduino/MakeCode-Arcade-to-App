import logging
from argparse import ArgumentParser
from pathlib import Path

from mkcd_to_app.config import parse_config
from mkcd_to_app.source import download_source
from utils.cmd import run_shell_command
from utils.filesystem import delete_these
from utils.logger import create_logger, set_all_stdout_logger_levels

logger = create_logger(name=__name__, level=logging.INFO)

parser = ArgumentParser(description="Convert your MakeCode Arcade games into a "
                                    "standalone offline executable!")
parser.add_argument("config_path", type=Path,
                    help="Path to the YAML configuration file.")
parser.add_argument("--no-cache", action="store_true",
                    help="Do not use cached files. This will delete and download all "
                         "necessary files.")
parser.add_argument("--skip-env-prep", action="store_true",
                    help="Skip environment preparation. This is useful for debugging.")
parser.add_argument("--skip-source-download", action="store_true",
                    help="Skip source code download. This is useful for debugging.")
parser.add_argument("--debug", action="store_true",
                    help="Enable debug logging.")
args = parser.parse_args()
debug = bool(args.debug)
if debug:
    set_all_stdout_logger_levels(logging.DEBUG)
logger.debug(f"Received arguments: {args}")

config_path = Path(args.config_path)
logger.info(f"Loading configuration from {config_path}")
config = parse_config(config_path.read_text())

no_cache = bool(args.no_cache)
if no_cache:
    logger.info("No cache option selected. Ignoring cached files.")
skip_env_prep = bool(args.skip_env_prep)
skip_source_download = bool(args.skip_source_download)

cwd = config_path.parent / config.name
logger.debug(f"Current working directory: {cwd} (source code directory will be "
             f"downloaded here)")
cwd.mkdir(parents=True, exist_ok=True)

# pxt target arcade
if skip_env_prep:
    logger.debug("Skipping environment preparation")
else:
    logger.info(f"Setting up environment")
    if no_cache:
        logger.debug("Checking for existing environment to remove")
        delete_these(["node_modules", "package.json", "package-lock.json"], cwd)
    run_shell_command("pxt target arcade", cwd=cwd)

# Download source code
if skip_source_download:
    logger.debug("Skipping source code download")
    source_code_path = cwd / f"{config.name} source"
else:
    logger.debug("Downloading source code")
    source_code_path = download_source(config, cwd, no_cache)
