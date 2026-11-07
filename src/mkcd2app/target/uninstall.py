import logging

from redun import task
from redun.task import CacheScope

from mkcd2app.utils.filesystem import rmtree_robust
from mkcd2app.utils.logger import create_logger
from mkcd2app.utils.paths import get_target_version_dir

logger = create_logger(name=__name__, level=logging.INFO)


# Never cached: it returns None, so a cached result can't tell that the directory
#  was reinstalled since, and a second uninstall would silently do nothing
@task(namespace="mkcd2app", cache_scope=CacheScope.NONE)
def uninstall_target(version: str) -> None:
    """
    Uninstall a MakeCode Arcade target version for this mkcd2app version.

    :param version: The MakeCode Arcade version to target. E.g., "4.0.14". Must be
     explicit 3 num sem ver, not just like "4.0" or "4", and do not include a "v".
    """
    logger.info(f"Uninstall MakeCode Arcade target version {version}")

    target_path = get_target_version_dir(version)
    if not target_path.exists():
        logger.warning(f"Target {version} is not installed, nothing to uninstall")
        return
    logger.debug(f"Removing target directory {target_path}")
    rmtree_robust(target_path)
