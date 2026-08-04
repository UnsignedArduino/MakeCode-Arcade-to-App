import logging
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

from redun import task
from redun.file import ContentDir, ContentFile

from mkcd2app.build_project.inputs.code import (
    build_binary_js,
    copy_support_files,
    fetch_code,
)
from mkcd2app.build_project.website import (
    copy_website_template,
    fill_website_template,
    install_deps_and_build_website,
    install_deps_and_build_website_singlefile,
)
from mkcd2app.config import load_config_from_yaml
from mkcd2app.models.config import StaticOutput, StaticSinglefileOutput
from mkcd2app.utils.logger import create_logger
from mkcd2app.utils.resources import get_resource_template_path

logger = create_logger(name=__name__, level=logging.INFO)


@dataclass
class BuildProjectResult:
    static: ContentDir | None = None
    static_singlefile: ContentFile | None = None
    electron: ContentDir | None = None
    tauri: ContentDir | None = None


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
        template_path = stack.enter_context(get_resource_template_path("vite-project"))
        template_content = ContentDir(str(template_path / "vite-project"))

        # Fetch game source code with `mkc`, `git`, or copy from disk
        code_path = fetch_code(config_yaml)
        # Build binary.js with `mkc`
        bin_js_path = build_binary_js(config_yaml, code_path)
        # Copy ---simulator.html from target dir and get favicon.ico if present
        support_path = copy_support_files(config_yaml)
        # Copy website template (clean copy with template files only)
        website_path = copy_website_template(config_yaml, template_content)
        # Copy + fill (separate dir so stages don't mutate each other's
        #  ContentDir/ContentPath
        website_filled_path = fill_website_template(
            config_yaml, website_path, bin_js_path, support_path
        )

        results = BuildProjectResult()
        # Build the website outputs
        # Electron and Tauri outputs depend on static_singlefile so redun figures it out
        logger.debug(f"{config.outputs=}")
        for output in config.outputs:
            match output.root:
                case StaticOutput():
                    # Copy + `npm ci` + `npm run build` (separate dir for same reason)
                    results.static = install_deps_and_build_website(website_filled_path)
                    logger.debug("Will build to static website")
                case StaticSinglefileOutput():
                    results.static_singlefile = (
                        install_deps_and_build_website_singlefile(website_filled_path)
                    )
                    logger.debug("Will build to static single-file website")

        return results
