import io
import logging
import sys
from pathlib import Path

from mkcd2app.build_project import BuildProjectResult, build_project
from mkcd2app.cli import generate_and_parse_args
from mkcd2app.config import load_config_from_yaml, resolve_config_paths
from mkcd2app.target.install import install_target
from mkcd2app.target.uninstall import uninstall_target
from mkcd2app.toolchain.install import install_toolchain
from mkcd2app.toolchain.uninstall import uninstall_toolchain
from mkcd2app.utils.filesystem import rmtree_robust
from mkcd2app.utils.logger import create_logger, set_all_stdout_logger_levels
from mkcd2app.utils.paths import (
    get_redun_db_for_build_path,
    get_redun_db_for_target_path,
    get_redun_db_for_toolchain_path,
)
from mkcd2app.utils.run_redun_task import run_redun_task
from mkcd2app.utils.text import raise_for_invalid_strict_semver

logger = create_logger(name=__name__, level=logging.INFO)


def _clear_build_dir(build_dir: Path) -> None:
    """
    Delete the build directory for a full rebuild.

    Only a directory with our cache DB is deleted, since `build_dir` comes from the
    config and a mistake there could otherwise delete an unrelated directory.

    :param build_dir: The build directory.
    :raises RuntimeError: If the directory has other files but no cache DB.
    """
    if not build_dir.exists() or not any(build_dir.iterdir()):
        logger.debug("Build directory is missing or empty; nothing to clear")
        return
    redun_db_path = get_redun_db_for_build_path(build_dir)
    if not redun_db_path.exists():
        raise RuntimeError(
            f"Refusing to clear {build_dir}: it isn't empty and has no "
            f"{redun_db_path.name}, so it may not be a build directory"
        )
    logger.warning(f"Clearing build directory {build_dir}")
    rmtree_robust(build_dir)


def main() -> None:
    # Logged command output can have characters that a redirected stdout's encoding
    #  can't represent (like cp1252 on Windows), which would lose the whole log record.
    #  This is what Python already does for stderr.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="backslashreplace")

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
            # noinspection none-function-assignment
            run_redun_task(
                expr=uninstall_toolchain(),
                redun_db_path=get_redun_db_for_toolchain_path(),
            )
            logger.debug("Toolchain uninstalled")
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
            # noinspection none-function-assignment
            run_redun_task(
                expr=uninstall_target(uninstall_version),
                redun_db_path=get_redun_db_for_target_path(),
            )
            logger.debug(f"Target {uninstall_version} uninstalled")

    elif args.command == "build":
        config_path = Path(args.config)
        logger.debug(f"Building project with config {config_path}")

        config_text = config_path.read_text(encoding="utf-8")

        config = resolve_config_paths(
            load_config_from_yaml(config_text), config_path.resolve().parent
        )
        build_dir = Path(config.build_dir)

        if args.full_rebuild:
            _clear_build_dir(build_dir)

        # The config is passed to redun tasks as JSON so that argument hashing is
        # deterministic (string) rather than pickle-based (which is non-deterministic
        # due to pydantic's set fields), and so that YAML comments and formatting
        # aren't part of the hash.
        results: BuildProjectResult = run_redun_task(
            build_project(config.model_dump_json()),
            get_redun_db_for_build_path(build_dir),
        )

        if results.static:
            logger.info(f"Static website directory is at {results.static.path}")
        if results.static_singlefile:
            logger.info(
                f"Static single-file HTML is at {results.static_singlefile.path}"
            )


if __name__ == "__main__":
    main()
