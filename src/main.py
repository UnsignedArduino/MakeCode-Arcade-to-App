import logging
from argparse import ArgumentParser
from pathlib import Path
import re
import subprocess

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
parser.add_argument("--skip-ext-install", action="store_true",
                    help="Skip extension installation. This is useful for debugging.")
parser.add_argument("--skip-build", action="store_true",
                    help="Skip building the project. This is useful for debugging.")
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
skip_ext_install = bool(args.skip_ext_install)

cwd = config_path.parent / config.name
logger.debug(f"Current working directory: {cwd} (source code directory will be "
             f"downloaded here)")
cwd.mkdir(parents=True, exist_ok=True)

# pxt target arcade
if skip_env_prep:
    logger.info("Skipping environment preparation")
else:
    logger.info(f"Setting up environment")
    if no_cache:
        logger.debug("Checking for existing environment to remove")
        delete_these(["node_modules", "package.json", "package-lock.json"], cwd)
    run_shell_command("pxt target arcade", cwd=cwd)

# Download source code
if skip_source_download:
    logger.info("Skipping source code download")
    source_code_path = cwd / f"{config.name} source"
else:
    logger.info("Downloading source code")
    source_code_path = download_source(config, cwd, no_cache)

# pxt install
if skip_ext_install:
    logger.info("Skipping extension installation")
else:
    logger.info("Installing extensions")
    if no_cache:
        logger.debug("Cleaning")
        run_shell_command("pxt clean", cwd=source_code_path)
    run_shell_command("pxt install", cwd=source_code_path)

# pxt build
binary_js_path = source_code_path / "built" / "debug" / "binary.js"
if args.skip_build:
    logger.info("Skipping build")
else:
    logger.info("Building project")
    if no_cache:
        logger.debug("Checking for binary to remove")
        if binary_js_path.exists():
            logger.debug(f"Deleting {binary_js_path}")
            binary_js_path.unlink()
    run_shell_command("pxt build", cwd=source_code_path)

logger.debug(f"Binary JS path: {binary_js_path}")
