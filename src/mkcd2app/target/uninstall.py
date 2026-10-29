import logging

from redun import task

from mkcd2app.utils.filesystem import rmtree_robust
from mkcd2app.utils.logger import create_logger
from mkcd2app.utils.paths import get_target_version_dir

logger = create_logger(name=__name__, level=logging.INFO)


@task(namespace="mkcd2app")
def uninstall_target(version: str) -> None:
    """
    Uninstall a MakeCode Arcade target version for this mkcd2app version.

    :param version: The MakeCode Arcade version to target. E.g., "4.0.14". Must be
     explicit 3 num sem ver, not just like "4.0" or "4", and do not include a "v".
    """
    logger.info(f"Uninstall MakeCode Arcade target version {version}")

    target_path = get_target_version_dir(version)
    logger.debug(f"Removing target directory {target_path}")
    rmtree_robust(target_path)
