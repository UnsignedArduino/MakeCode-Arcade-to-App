import logging
import shutil
from pathlib import Path

from redun import task
from redun.file import ContentDir

from mkcd2app.build_project.inputs.code import build_binary_js, \
    download_supporting_files, fetch_code
from mkcd2app.build_project.website import copy_website_template, \
    fill_website_template, install_website_dependencies
from mkcd2app.config import BuildConfig
from mkcd2app.utils.logger import create_logger
from mkcd2app.utils.resources import get_js_tools_path
from mkcd2app.utils.run import run_cmd

logger = create_logger(name=__name__, level=logging.INFO)


@task(namespace="mkcd2app")
def install_mkcd_build_tools(config: BuildConfig) -> ContentDir:
    """
    Installs the MakeCode Arcade build tools.

    :param config: The parsed config file.
    :return: A redun.ContentDir that points to node_modules, this is only used so that
     redun will see that some tasks depend on `mkc` being installed.
    """
    logger.info("Installing MakeCode Arcade build tools")

    build_path = Path(config.build_dir)
    logger.debug(f"Tools will be installed in {build_path}")

    with get_js_tools_path() as js_tools_path:
        shutil.copy(js_tools_path / "package.json", build_path / "package.json")
        shutil.copy(js_tools_path / "package-lock.json",
                    build_path / "package-lock.json")

    run_cmd("npm ci", cwd=build_path)

    logger.debug("All MakeCode Arcade build tools installed")

    return ContentDir(str(build_path / "node_modules"))


@task(namespace="mkcd2app")
def build_project(config: BuildConfig):
    """
    Build the project.

    :param config: The parsed config file.
    """
    # TODO: Figure out why the cache keeps busting even on identical reruns

    logger.info("Building project")

    build_dir = Path(config.build_dir)
    logger.debug(f"Project build directory is at {build_dir}")
    build_dir.mkdir(parents=True, exist_ok=True)

    # Install `mkc` with `npm ci` in build dir
    node_modules_for_mkc = install_mkcd_build_tools(config)
    # Fetch game source code with `mkc`, `git`, or copy from disk
    code_path = fetch_code(config, node_modules_for_mkc)
    # Build binary.js with `mkc`
    bin_js_path = build_binary_js(code_path)
    # Download supporting files to run binary.js, including ---simulator.html and all
    # it's references
    support_path = download_supporting_files(config)

    # Copy website template
    website_path = copy_website_template(config)
    # `npm ci` the website
    node_modules_for_website = install_website_dependencies(website_path)
    # Fill the website template out
    website_path = fill_website_template(config, website_path, bin_js_path,
                                         support_path)

    return website_path, node_modules_for_website  # returning so redun actually runs the promises
