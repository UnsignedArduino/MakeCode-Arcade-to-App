import logging
import shutil
from argparse import ArgumentParser
from pathlib import Path

import redun
import redun.file
from redun import Scheduler

# Monkey-patch redun.file.get_proto so Windows absolute paths like "E:\..."
# aren't parsed as having scheme "e" by urllib.parse.urlparse.
_orig_get_proto = redun.file.get_proto


def _patched_get_proto(url: str | None = None) -> str:
    if url and len(url) >= 3 and url[1] == ":" and url[0].isalpha() and url[2] in ("\\",
                                                                                   "/"):
        return "local"
    return _orig_get_proto(url)


redun.file.get_proto = _patched_get_proto


# Monkey patch ContentDir to use content-based hashing instead of mtime-based hashing.
# This addresses the issue where cache busts even on identical runs.
# Note: ContentDir.__iter__() already yields ContentFile objects (via
# ContentFileClasses), so f.hash is content-based — no need to create redundant
# ContentFile instances.
def _content_dir_calc_hash(self, files=None):
    if files is None:
        files = list(self)
    from redun.hashing import hash_struct
    return hash_struct([self.type_basename, self.path] + sorted(f.hash for f in files))


redun.file.ContentDir._calc_hash = _content_dir_calc_hash


# Also patch Dir._calc_hash to prevent mtime-based hashing leak through any
# code path that uses Dir directly (e.g. FileSystem.iter_file_hashes).
# Note: we intentionally drop the `files` param because Dir.update_hash()
# passes File objects (mtime-based), not ContentFile objects. Re-iterating
# via ContentDir gives properly content-based hashing.
def _dir_calc_hash(self, files=None):
    from redun.file import ContentDir
    return ContentDir(self.path)._calc_hash()


redun.file.Dir._calc_hash = _dir_calc_hash

from mkcd2app.build_project import build_project
from mkcd2app.config import load_config_from_yaml
from mkcd2app.utils.logger import create_logger, set_all_stdout_logger_levels

logger = create_logger(name=__name__, level=logging.INFO)


def main():
    parser = ArgumentParser(description="Convert your MakeCode Arcade games into a "
                                        "standalone offline executable!")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug logging. This must go first before the sub "
                             "command.")
    subparsers = parser.add_subparsers(required=True, dest="command")
    # build subcommand
    parser_build = subparsers.add_parser("build",
                                         help="Build your MakeCode Arcade game.")
    parser_build.add_argument("config", type=str, help="Path to the YAML config file.")
    parser_build.add_argument("--clear-cache", action="store_true",
                              help="Delete the entire build directory before building.")

    args = parser.parse_args()
    debug = bool(args.debug)
    if debug:
        set_all_stdout_logger_levels(logging.DEBUG)
    logger.debug(f"Received arguments: {args}")

    if args.command == "build":
        logger.debug("Building project")

        config_path = Path(args.config)
        logger.debug(f"Loading config from {config_path}")
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

        build_dir.mkdir(parents=True, exist_ok=True)
        db_uri = f"sqlite:///{build_dir.resolve() / '.redun-cache.db'}"
        logger.debug(f"redun cache DB: {db_uri}")
        # noinspection PyUnresolvedReferences
        redun_config = redun.config.Config({
            "scheduler": {"log_level": "DEBUG"},
            "backend": {"db_uri": db_uri},
        })
        scheduler = Scheduler(config=redun_config)
        # Load/migrate the backend so the persistent DB is properly set up.
        # Without this, providing a custom db_uri skips the automatic
        # engine creation and migration that the in-memory default does.
        scheduler.load()
        result = scheduler.run(
            build_project(config_text),
        )

        logger.debug(f"Build finished, result is at {result}")


if __name__ == "__main__":
    main()
