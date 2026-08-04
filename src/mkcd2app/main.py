import logging
import shutil
from pathlib import Path

from mkcd2app.build_project import BuildProjectResult, build_project
from mkcd2app.cli import generate_and_parse_args
from mkcd2app.config import load_config_from_yaml
from mkcd2app.target.install import install_target
from mkcd2app.toolchains.install import install_toolchain
from mkcd2app.utils.logger import create_logger, set_all_stdout_logger_levels
from mkcd2app.utils.paths import (
    get_redun_db_for_target_path,
    get_redun_db_for_toolchain_path,
)
from mkcd2app.utils.run_redun_task import run_redun_task
from mkcd2app.utils.text import raise_for_invalid_strict_semver

logger = create_logger(name=__name__, level=logging.INFO)


def main() -> None:
    args = generate_and_parse_args()
    debug = bool(args.debug)
    if debug:
        set_all_stdout_logger_levels(logging.DEBUG)
    logger.debug(f"Received arguments: {args}")

    if args.command == "toolchain":
        if args.toolchain_command == "install":
            logger.debug("Installing MakeCode CLI toolchain")
            run_redun_task(
                expr=install_toolchain(),
                redun_db_path=get_redun_db_for_toolchain_path(),
            )
            logger.debug("Toolchain installed")
        elif args.toolchain_command == "status":
            logger.debug("Checking MakeCode CLI toolchain status")

        elif args.toolchain_command == "uninstall":
            logger.debug("Uninstalling MakeCode CLI toolchain")
    elif args.command == "target":
        if args.target_command == "install":
            install_version: str = args.version
            raise_for_invalid_strict_semver(install_version)
            logger.debug(f"Installing MakeCode CLI target version {install_version}")
            run_redun_task(
                expr=install_target(install_version),
                redun_db_path=get_redun_db_for_target_path(),
            )
            logger.debug(f"Target {install_version} installed")
        elif args.target_command == "list":
            logger.debug("Listing MakeCode CLI target")

        elif args.target_command == "uninstall":
            uninstall_version: str = args.version
            raise_for_invalid_strict_semver(uninstall_version)
            logger.debug(
                f"Uninstalling MakeCode CLI target version {uninstall_version}"
            )

    elif args.command == "build":
        config_path = Path(args.config)
        logger.debug(f"Building project with config {config_path}")

        config_text = config_path.read_text()

        # Parse once only to extract build_dir for the redun DB path.
        # The raw YAML text is passed to redun tasks so that argument
        # hashing is deterministic (string) rather than pickle-based
        # (which is non-deterministic due to pydantic's set fields).
        config = load_config_from_yaml(config_text)
        build_dir = Path(config.build_dir)

        if args.clear_cache:
            if build_dir.exists():
                logger.warning(f"Clearing build directory {build_dir}")
                shutil.rmtree(build_dir)
            else:
                logger.debug("Build directory does not exist; nothing to clear")

        results: BuildProjectResult = run_redun_task(
            build_project(config_text), build_dir.resolve() / ".redun-cache.db"
        )

        if results.static:
            logger.info(f"Static website directory is at {results.static.path}")
        if results.static_singlefile:
            logger.info(
                f"Static single-file HTML is at {results.static_singlefile.path}"
            )


if __name__ == "__main__":
    main()
