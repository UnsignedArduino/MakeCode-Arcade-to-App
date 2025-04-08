import logging
from argparse import ArgumentParser
from pathlib import Path

from config import parse_config
from source import download_source
from utils.logger import create_logger

logger = create_logger(name=__name__, level=logging.DEBUG)

parser = ArgumentParser(description="Convert your MakeCode Arcade games into a "
                                    "standalone offline executable!")
parser.add_argument("config_path", type=Path,
                    help="Path to the YAML configuration file.")
args = parser.parse_args()
logger.debug(f"Received arguments: {args}")

config_path = Path(args.config_path)
logger.info(f"Loading configuration from {config_path}")
config = parse_config(config_path.read_text())

cwd = config_path.parent / config.name
logger.debug(f"Current working directory: {cwd} (source code directory will be "
             f"downloaded here)")
cwd.mkdir(parents=True, exist_ok=True)

logger.debug("Downloading source code")
source_code_dir = download_source(config, cwd)
