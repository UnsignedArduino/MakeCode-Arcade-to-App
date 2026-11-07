import logging

from redun import task
from redun.task import CacheScope

from mkcd2app.utils.filesystem import rmtree_robust
from mkcd2app.utils.logger import create_logger
from mkcd2app.utils.paths import get_toolchain_dir

logger = create_logger(name=__name__, level=logging.INFO)


# Never cached: it returns None, so a cached result can't tell that the directory
#  was reinstalled since, and a second uninstall would silently do nothing
@task(namespace="mkcd2app", cache_scope=CacheScope.NONE)
def uninstall_toolchain() -> None:
    """
    Uninstall the toolchain for this mkcd2app version by removing the toolchain
    directory. The toolchain redun DB lives in the state dir and is left in place.
    """
    logger.info("Uninstalling toolchain")

    toolchain_path = get_toolchain_dir()
    if not toolchain_path.exists():
        logger.warning("Toolchain is not installed, nothing to uninstall")
        return
    logger.debug(f"Removing toolchain directory {toolchain_path}")
    rmtree_robust(toolchain_path)
