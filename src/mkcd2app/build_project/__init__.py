import logging
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import assert_never

from redun import task
from redun.file import ContentDir, ContentFile

from mkcd2app.build_project.inputs.code import (
    build_binary_js,
    copy_support_files,
    fetch_code,
)
from mkcd2app.build_project.website import (
    _website_dir,
    build_website,
    build_website_singlefile,
    copy_website_template,
    fill_website_template,
    install_website_deps,
)
from mkcd2app.models.config import (
    BuildConfig,
    ElectronOutput,
    StaticOutput,
    StaticSinglefileOutput,
    TauriOutput,
)
from mkcd2app.utils.logger import create_logger
from mkcd2app.utils.paths import get_sim_html_path
from mkcd2app.utils.resources import get_resource_template_path

logger = create_logger(name=__name__, level=logging.INFO)


@dataclass
class BuildProjectResult:
    static: ContentDir | None = None
    static_singlefile: ContentFile | None = None
    electron: ContentDir | None = None
    tauri: ContentDir | None = None


@task(namespace="mkcd2app")
def build_project(config_json: str) -> BuildProjectResult:
    """
    Build the project.

    Each subtask gets only the parts of the config it uses, as strings, so editing
    one part of the config only reruns the tasks that depend on it.

    :param config_json: The BuildConfig, with absolute paths (see
     `resolve_config_paths`), dumped to a JSON string.
    :return BuildProjectResult: A BuildProjectResult object containing paths.
    """
    logger.info("Building project")

    config = BuildConfig.model_validate_json(config_json)
    build_dir = Path(config.build_dir)
    name = config.project.path_friendly_name
    logger.debug(f"Project build directory is at {build_dir}")
    build_dir.mkdir(parents=True, exist_ok=True)

    if not get_sim_html_path(config.target).is_file():
        raise FileNotFoundError(
            f"MakeCode Arcade target {config.target} is not installed, install it "
            f"with `mkcd2app target install {config.target}`"
        )

    icon = config.inputs.assets.icon

    with ExitStack() as stack:
        template_path = stack.enter_context(get_resource_template_path("vite-project"))
        template_content = ContentDir(str(template_path))

        # Fetch game source code with `mkc`, dulwich (git), or copy from disk
        code_path = fetch_code(
            config.inputs.code.model_dump_json(),
            config.target,
            str(build_dir / f"{name}-source"),
        )
        # Copy the source code + build binary.js with `mkc`
        bin_js_path = build_binary_js(
            code_path, str(build_dir / f"{name}-binary-js-build")
        )
        # Copy ---simulator.html from target dir and get favicon.ico if present
        support_path = copy_support_files(
            config.target,
            icon.model_dump_json() if icon else None,
            str(build_dir / f"{name}-binary-js-support"),
        )
        # Copy website template (clean copy with template files only)
        website_path = copy_website_template(
            str(_website_dir(build_dir, name, "")), template_content
        )
        # Copy + fill (separate dir so stages don't mutate each other's
        #  ContentDir/ContentPath
        website_filled_path = fill_website_template(
            config.project.model_dump_json(), website_path, bin_js_path, support_path
        )
        # `npm ci` from only package.json + lockfile, so game/asset changes don't
        #  bust it; shared by every website output
        node_modules = install_website_deps(
            str(_website_dir(build_dir, name, "-deps")),
            ContentFile(str(template_path / "package.json")),
            ContentFile(str(template_path / "package-lock.json")),
        )

        results = BuildProjectResult()
        # Build the website outputs
        # Electron and Tauri outputs depend on static_singlefile so redun figures it out
        logger.debug(f"{config.outputs=}")
        for output in config.outputs:
            match output.root:
                case StaticOutput():
                    # Copy + node_modules + `npm run build` (separate dir for same
                    #  reason)
                    results.static = build_website(website_filled_path, node_modules)
                    logger.debug("Will build to static website")
                case StaticSinglefileOutput():
                    results.static_singlefile = build_website_singlefile(
                        website_filled_path, node_modules
                    )
                    logger.debug("Will build to static single-file website")
                case ElectronOutput() | TauriOutput():
                    # Tasks are lazy, so nothing has run yet
                    raise NotImplementedError(
                        f"The {output.root.type} output is not implemented yet"
                    )
                case _:
                    assert_never(output.root)

        return results
