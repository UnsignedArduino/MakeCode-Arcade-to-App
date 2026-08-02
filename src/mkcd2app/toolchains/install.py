import logging
import shutil
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory

from redun import task
from redun.file import ContentDir

from mkcd2app.utils.logger import create_logger
from mkcd2app.utils.paths import get_js_tools_dir, get_templates_npm_cache_dir
from mkcd2app.utils.resources import get_js_tools_path, get_template_path
from mkcd2app.utils.run import run_cmd

logger = create_logger(name=__name__, level=logging.INFO)


@task(namespace="mkcd2app")
def install_js_tools(js_tools: ContentDir) -> ContentDir:
    """
    Installs necessary JS tools for mkcd2app.

    :param js_tools: The ContentDir pointing to the directory containing the
     package.json and package-lock.json, which include the tools to install.
    :return: A ContentDir pointing to node_modules, to ensure redun sees that this task
     has something that depends on its results.
    """
    logger.info("Installing JS tools")

    source_path = Path(js_tools.path)
    dest_path = get_js_tools_dir()
    dest_path.mkdir(parents=True, exist_ok=True)

    logger.debug(f"Copying package files from {source_path} to {dest_path}")
    shutil.copy(source_path / "package.json", dest_path / "package.json")
    shutil.copy(source_path / "package-lock.json", dest_path / "package-lock.json")

    logger.debug("`npm ci` to download")
    run_cmd(["npm", "ci"], cwd=dest_path)

    logger.debug("All JS tools installed")
    return ContentDir(str(dest_path / "node_modules"))


@task(namespace="mkcd2app")
def warm_npm_cache_for_templates(templates: ContentDir) -> ContentDir:
    """
    For every template in the templates directory, copy them to a temporary directory,
    run `npm ci --cache CACHE_DIR --prefer-online` where CACHE_DIR

    :param templates: The ContentDir pointing to the directory containing the templates.
    :return: A ContentDir pointing to node_modules, to ensure redun sees that this task
     has something that depends on its results.
    """
    logger.info("Warming npm cache for templates")

    source_path = Path(templates.path)
    cache_path = get_templates_npm_cache_dir()
    cache_path.mkdir(parents=True, exist_ok=True)

    logger.debug(f"Looking for templates in {source_path}")

    all_templates = list(source_path.iterdir())
    logger.debug(f"Found {len(all_templates)} templates")

    for template in all_templates:
        logger.debug(f"Caching packages for template {template.name}")
        with TemporaryDirectory() as tmp_dir:
            tmp_dir_path = Path(tmp_dir)
            logger.debug(f"Copying {template} to {tmp_dir_path}")
            shutil.copytree(template, tmp_dir_path, dirs_exist_ok=True)
            logger.debug("Caching npm packages")
            run_cmd(
                ["npm", "ci", "--cache", str(cache_path), "--prefer-online"],
                cwd=tmp_dir_path,
            )

    logger.debug(f"npm cache filled at {cache_path}")
    return ContentDir(str(cache_path))


@task(namespace="mkcd2app")
def install_toolchain() -> tuple[ContentDir, ContentDir]:
    """
    Install the toolchain for this mkcd2app version.
    """
    logger.info("Installing toolchain")

    with ExitStack() as stack:
        js_tools_path = stack.enter_context(get_js_tools_path())
        templates_path = stack.enter_context(get_template_path())

        # `npm ci` the necessary tools (`mkc` CLI itself)
        js_tools_node_modules = install_js_tools(ContentDir(str(js_tools_path)))
        # `npm ci --cache CACHE_DIR --prefer-online` for all templates
        templates_npm_cache = warm_npm_cache_for_templates(
            ContentDir(str(templates_path))
        )

        return js_tools_node_modules, templates_npm_cache
