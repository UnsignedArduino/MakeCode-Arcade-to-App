import logging
from argparse import ArgumentParser
from pathlib import Path

from convert.mkcd_to_website.config import OutputType, parse_config
from convert.mkcd_to_website.source import download_source
from convert.mkcd_to_website.website import generate_website
from convert.website_to_electron.electron import generate_electron
from convert.website_to_tauri.tauri import generate_tauri
from utils.cmd import run_shell_command
from utils.filesystem import delete_these
from utils.logger import create_logger, set_all_stdout_logger_levels

logger = create_logger(name=__name__, level=logging.INFO)

parser = ArgumentParser(description="Convert your MakeCode Arcade games into a "
                                    "standalone offline executable!")
parser.add_argument("config_path", type=Path,
                    help="Path to the YAML configuration file.")
parser.add_argument("--no-cache", action="store_true",
                    help="Do not use cached files. This will delete and download all "
                         "necessary files.")
parser.add_argument("--skip-env-prep", action="store_true",
                    help="Skip environment preparation. This is useful for debugging.")
parser.add_argument("--skip-source-download", action="store_true",
                    help="Skip source code download. This is useful for debugging.")
parser.add_argument("--skip-ext-install", action="store_true",
                    help="Skip extension installation. This is useful for debugging.")
parser.add_argument("--skip-bin-build", action="store_true",
                    help="Skip building the game binary. This is useful for debugging.")
parser.add_argument("--skip-website-gen", action="store_true",
                    help="Skip website generation. This is useful for debugging.")
parser.add_argument("--skip-website-build", action="store_true",
                    help="Skip building the website. This is useful for debugging.")
parser.add_argument("--skip-electron-gen", action="store_true",
                    help="Skip Electron app generation. This is useful for debugging.")
parser.add_argument("--skip-electron-build", action="store_true",
                    help="Skip building the Electron app. This is useful for debugging.")
parser.add_argument("--skip-tauri-gen", action="store_true",
                    help="Skip Tauri app generation. This is useful for debugging.")
parser.add_argument("--skip-tauri-build", action="store_true",
                    help="Skip building the Tauri app. This is useful for debugging.")
parser.add_argument("--debug", action="store_true",
                    help="Enable debug logging.")
args = parser.parse_args()
debug = bool(args.debug)
if debug:
    set_all_stdout_logger_levels(logging.DEBUG)
logger.debug(f"Received arguments: {args}")

config_path = Path(args.config_path)
logger.info(f"Loading configuration from {config_path}")
config = parse_config(config_path.read_text(), config_path.parent)

output_format = config.output
logger.debug(f"Building to {output_format.value}")

no_cache = bool(args.no_cache)
if no_cache:
    logger.info("No cache option selected. Ignoring cached files.")
skip_env_prep = bool(args.skip_env_prep)
skip_source_download = bool(args.skip_source_download)
skip_ext_install = bool(args.skip_ext_install)
skip_bin_build = bool(args.skip_bin_build)
skip_website_gen = bool(args.skip_website_gen)
skip_website_build = bool(args.skip_website_build)
skip_electron_gen = bool(args.skip_electron_gen)
skip_electron_build = bool(args.skip_electron_build)
skip_tauri_gen = bool(args.skip_tauri_gen)
skip_tauri_build = bool(args.skip_tauri_build)

cwd = config_path.parent / config.name
src_dir = Path(__file__).parent
logger.debug(f"Current working directory: {cwd} (source code directory will be "
             f"downloaded here)")
logger.debug(f"Source code directory: {src_dir}")
cwd.mkdir(parents=True, exist_ok=True)
# npx pxt target arcade
if skip_env_prep:
    logger.info("Skipping environment preparation")
else:
    logger.info(f"Setting up environment")
    if no_cache:
        logger.debug("Checking for existing environment to remove")
        delete_these(["node_modules", "package.json", "package-lock.json"], cwd)
    run_shell_command("npx pxt target arcade", cwd=cwd)

# Download source code
if skip_source_download:
    logger.info("Skipping source code download")
    source_code_path = cwd / f"{config.name} source"
else:
    logger.info("Downloading source code")
    source_code_path = download_source(config, cwd, no_cache)

# npx pxt install
if skip_ext_install:
    logger.info("Skipping extension installation")
else:
    logger.info("Installing extensions")
    if no_cache:
        logger.debug("Cleaning")
        run_shell_command("npx pxt clean", cwd=source_code_path)
    run_shell_command("npx pxt install", cwd=source_code_path)

# npx pxt build
binary_js_path = source_code_path / "built" / "debug" / "binary.js"
if skip_bin_build:
    logger.info("Skipping build")
else:
    logger.info("Building project")
    if no_cache:
        logger.debug("Checking for binary to remove")
        if binary_js_path.exists():
            logger.debug(f"Deleting {binary_js_path}")
            binary_js_path.unlink()
    run_shell_command("npx pxt build", cwd=source_code_path)
logger.debug(f"Binary JS path: {binary_js_path}")

# yarn create vite, copy files, and substitute values
vite_project_name = f"{config.name.lower().replace(" ", "-")}-website"
website_path = cwd / vite_project_name
if skip_website_gen:
    logger.info("Skipping website generation")
else:
    logger.info(f"Generating TS React and Vite website")
    if no_cache:
        logger.debug("Checking for existing website to remove")
        delete_these([vite_project_name], cwd)
    logger.debug(f"Creating Vite project with name {vite_project_name}")
    generate_website(config, vite_project_name, src_dir / "templates" / "website_files",
                     cwd, binary_js_path)

# yarn run build
website_dist_path = website_path / "dist"
if skip_website_build:
    logger.info("Skipping website build")
else:
    logger.info("Building website")
    run_shell_command("yarn build", cwd=website_path)

logger.info(f"Static website files are at {website_dist_path}")
if output_format == OutputType.STATIC:
    logger.info(f"Build finished")
    exit(0)
elif output_format == OutputType.ELECTRON:
    electron_project_name = f"{config.name.lower().replace(" ", "-")}-electron"
    electron_path = cwd / electron_project_name
    if skip_electron_gen:
        logger.info("Skipping Electron app generation")
    else:
        logger.info(f"Generating Electron app")
        logger.debug(
            f"Creating Electron app in {cwd}, using {website_dist_path} for source")
        logger.debug(f"Creating Electron project with name {electron_project_name}")
        # npx create-electron-app@latest, copy files, and substitute values
        if no_cache:
            logger.debug("Checking for existing website to remove")
            delete_these([electron_project_name], cwd)
        generate_electron(config, electron_project_name,
                          src_dir / "templates" / "electron_files", website_dist_path,
                          cwd)

    # yarn run make
    electron_dist_path = electron_path / "out"
    if skip_electron_build:
        logger.info("Skipping Electron app build")
    else:
        logger.info("Building Electron app")
        run_shell_command("yarn run make", cwd=electron_path)

    logger.info(f"Electron app executables are at {electron_dist_path}")
    logger.info(f"Build finished")
    exit(0)
elif output_format == OutputType.TAURI:
    tauri_project_name = f"{config.name.lower().replace(' ', '-')}-tauri"
    tauri_path = cwd / tauri_project_name
    if skip_tauri_gen:
        logger.info("Skipping Tauri app generation")
    else:
        logger.info(f"Generating Tauri app")
        logger.debug(
            f"Creating Tauri app in {cwd}, using {website_dist_path} for source")
        logger.debug(f"Creating Tauri project with name {tauri_project_name}")
        # yarn create tauri-app
        if no_cache:
            logger.debug("Checking for existing website to remove")
            delete_these([tauri_project_name], cwd)
        generate_tauri(config, tauri_project_name,
                       src_dir / "templates" / "tauri_files", website_dist_path, cwd)

    # yarn run tauri build
    tauri_dist_path = tauri_path / "src-tauri" / "target" / "release"
    if skip_tauri_build:
        logger.info("Skipping Tauri app build")
    else:
        logger.info("Building Tauri app")
        run_shell_command("yarn run tauri build", cwd=tauri_path)

    logger.info(f"Tauri app executables are at {tauri_dist_path}")
    logger.info(f"Build finished")
    exit(0)
