import logging

from redun import task

from mkcd2app.utils.filesystem import rmtree_robust
from mkcd2app.utils.logger import create_logger
from mkcd2app.utils.paths import get_toolchain_dir

logger = create_logger(name=__name__, level=logging.INFO)


@task(namespace="mkcd2app")
def uninstall_toolchain() -> None:
    """
    Uninstall the toolchain for this mkcd2app version by removing the toolchain
    directory and its redun cache DB.
    """
    logger.info("Uninstalling toolchain")

    toolchain_path = get_toolchain_dir()
    logger.debug(f"Removing toolchain directory {toolchain_path}")
    rmtree_robust(toolchain_path)
