import logging
import shutil
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from redun import task
from redun.file import ContentDir, ContentFile

from mkcd2app.build_project.inputs.code import build_binary_js, \
    download_and_mod_supporting_files, fetch_code
from mkcd2app.build_project.website import copy_website_template, \
    fill_website_template, install_deps_and_build_website, \
    install_deps_and_build_website_singlefile
from mkcd2app.config import load_config_from_yaml
from mkcd2app.config.model import StaticOutput, StaticSinglefileOutput
from mkcd2app.utils.logger import create_logger
from mkcd2app.utils.resources import get_js_tools_path, get_template_path
from mkcd2app.utils.run import run_cmd

logger = create_logger(name=__name__, level=logging.INFO)


@task(namespace="mkcd2app")
def install_mkcd_build_tools(config_yaml: str,
                             js_tools_src: ContentDir) -> ContentDir:
    """
    Installs the MakeCode Arcade build tools.

    :param config_yaml: The raw YAML text of the config file.
    :param js_tools_src: A redun.ContentDir pointing to the js_tools directory,
                         so that redun tracks changes to package.json etc.
    :return: A redun.ContentDir that points to node_modules, this is only used so that
     redun will see that some tasks depend on `mkc` being installed.
    """
    logger.info("Installing MakeCode Arcade build tools")

    config = load_config_from_yaml(config_yaml)
    build_path = Path(config.build_dir)
    logger.debug(f"Tools will be installed in {build_path}")

    js_tools_path = Path(js_tools_src.path)
    shutil.copy(js_tools_path / "package.json", build_path / "package.json")
    shutil.copy(js_tools_path / "package-lock.json",
                build_path / "package-lock.json")

    run_cmd(["npm", "ci"], cwd=build_path)

    logger.debug("All MakeCode Arcade build tools installed")

    return ContentDir(str(build_path / "node_modules"))


@dataclass
class BuildProjectResult:
    static: Optional[ContentDir] = None
    static_singlefile: Optional[ContentFile] = None
    electron: Optional[ContentDir] = None
    tauri: Optional[ContentDir] = None


@task(namespace="mkcd2app")
def build_project(config_yaml: str) -> BuildProjectResult:
    """
    Build the project.

    :param config_yaml: The raw YAML text of the config file.
    :return BuildProjectResult: A BuildProjectResult object containing paths.
    """
    logger.info("Building project")

    config = load_config_from_yaml(config_yaml)
    build_dir = Path(config.build_dir)
    logger.debug(f"Project build directory is at {build_dir}")
    build_dir.mkdir(parents=True, exist_ok=True)

    with ExitStack() as stack:
        js_tools_path = stack.enter_context(get_js_tools_path())
        js_tools_content = ContentDir(str(js_tools_path))

        template_path = stack.enter_context(get_template_path("vite-project"))
        template_content = ContentDir(str(template_path))

        # Install `mkc` with `npm ci` in build dir
        node_modules_for_mkc = install_mkcd_build_tools(config_yaml, js_tools_content)
        # Fetch game source code with `mkc`, `git`, or copy from disk
        code_path = fetch_code(config_yaml, node_modules_for_mkc)
        # Build binary.js with `mkc`
        bin_js_path = build_binary_js(config_yaml, code_path)
        # Download supporting files to run binary.js, including ---simulator.html and all
        # it's references, and get favicon.ico if present
        support_path = download_and_mod_supporting_files(config_yaml)

        # Copy website template (clean copy with template files only)
        website_path = copy_website_template(config_yaml, template_content)
        # Copy + fill (separate dir so stages don't mutate each other's
        #  ContentDir/ContentPath
        website_filled_path = fill_website_template(config_yaml, website_path,
                                                    bin_js_path,
                                                    support_path)

        results = BuildProjectResult()

        logger.debug(f"{config.outputs=}")
        for output in config.outputs:
            match output.root:
                case StaticOutput():
                    # Copy + `npm ci` + `npm run build` (separate dir for same reason)
                    results.static = install_deps_and_build_website(website_filled_path)
                    logger.debug("Will build to static website")
                case StaticSinglefileOutput():
                    results.static_singlefile = install_deps_and_build_website_singlefile(
                        website_filled_path)
                    logger.debug("Will build to static single-file website")

        return results
