import logging
from argparse import ArgumentParser
from pathlib import Path

from config import parse_config
from source import download_source
from src.utils.cmd import run_shell_command
from utils.logger import create_logger

logger = create_logger(name=__name__, level=logging.DEBUG)

parser = ArgumentParser(description="Convert your MakeCode Arcade games into a "
                                    "standalone offline executable!")
parser.add_argument("config_path", type=Path,
                    help="Path to the YAML configuration file.")
parser.add_argument("--no-cache", action="store_true",
                    help="Do not use cached files. This will delete and download all "
                         "necessary files")
parser.add_argument("--skip-env-prep", action="store_true",
                    help="Skip environment preparation. This is useful for debugging. ")
parser.add_argument("--skip-source-download", action="store_true",
                    help="Skip source code download. This is useful for debugging. ")
args = parser.parse_args()
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
        stuff_to_check = ["node_modules", "package.json", "package-lock.json"]
        for item in stuff_to_check:
            item_path = cwd / item
            if item_path.exists():
                logger.debug(f"Removing {item_path}")
                if item_path.is_dir():
                    import shutil

                    shutil.rmtree(item_path)
                else:
                    item_path.unlink()
    run_shell_command("pxt target arcade", cwd=cwd)

if skip_source_download:
    logger.debug("Skipping source code download")
    source_code_path = cwd / f"{config.name} source"
else:
    logger.debug("Downloading source code")
    source_code_path = download_source(config, cwd, no_cache)
