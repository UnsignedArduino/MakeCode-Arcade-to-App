import logging
from pathlib import Path

from mkcd2app.cli import generate_and_parse_args
from mkcd2app.utils.logger import create_logger, set_all_stdout_logger_levels

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

        elif args.toolchain_command == "status":
            logger.debug("Checking MakeCode CLI toolchain status")

        elif args.toolchain_command == "uninstall":
            logger.debug("Uninstalling MakeCode CLI toolchain")
    elif args.command == "target":
        if args.target_command == "install":
            installVersion: str = args.version
            logger.debug(f"Installing MakeCode CLI target version {installVersion}")

        elif args.target_command == "list":
            logger.debug("Listing MakeCode CLI target")

        elif args.target_command == "uninstall":
            uninstallVersion: str = args.version
            logger.debug(f"Uninstalling MakeCode CLI target version {uninstallVersion}")

    elif args.command == "build":
        config_path = Path(args.config)
        logger.debug(f"Building project with config {config_path}")

        # config_text = config_path.read_text()
        #
        # # Parse once only to extract build_dir for the redun DB path.
        # # The raw YAML text is passed to redun tasks so that argument
        # # hashing is deterministic (string) rather than pickle-based
        # # (which is non-deterministic due to pydantic's set fields).
        # config = load_config_from_yaml(config_text)
        # build_dir = Path(config.build_dir)
        #
        # if args.clear_cache:
        #     if build_dir.exists():
        #         logger.warning(f"Clearing build directory {build_dir}")
        #         shutil.rmtree(build_dir)
        #     else:
        #         logger.debug("Build directory does not exist; nothing to clear")
        #
        # build_dir.mkdir(parents=True, exist_ok=True)
        # db_uri = f"sqlite:///{build_dir.resolve() / '.redun-cache.db'}"
        # logger.debug(f"redun cache DB: {db_uri}")
        # # noinspection PyUnresolvedReferences
        # redun_config = redun.config.Config(
        #     {
        #         "scheduler": {"log_level": "DEBUG"},
        #         "backend": {"db_uri": db_uri},
        #     }
        # )
        # scheduler = Scheduler(config=redun_config)
        # # Load/migrate the backend so the persistent DB is properly set up.
        # # Without this, providing a custom db_uri skips the automatic
        # # engine creation and migration that the in-memory default does.
        # scheduler.load()
        # results: BuildProjectResult = scheduler.run(
        #     build_project(config_text),
        # )
        # if results.static:
        #     logger.info(f"Static website directory is at {results.static.path}")
        # if results.static_singlefile:
        #     logger.info(
        #         f"Static single-file HTML is at {results.static_singlefile.path}"
        #     )


if __name__ == "__main__":
    main()
