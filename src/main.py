import logging
from argparse import ArgumentParser

from utils.logger import create_logger

logger = create_logger(name=__name__, level=logging.DEBUG)

parser = ArgumentParser(description="Convert your MakeCode Arcade games into a "
                                    "standalone offline executable!")
args = parser.parse_args()
logger.debug(f"Received arguments: {args}")
