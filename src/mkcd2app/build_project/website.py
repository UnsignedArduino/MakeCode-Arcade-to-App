import logging
import shutil
from pathlib import Path

from redun import task
from redun.file import ContentDir, ContentFile

from mkcd2app.config import load_config_from_yaml
from mkcd2app.utils.logger import create_logger
from mkcd2app.utils.resources import get_template_path
from mkcd2app.utils.run import run_cmd

logger = create_logger(name=__name__, level=logging.INFO)


def _website_dir(build_dir: Path, name: str, suffix: str) -> Path:
    """Return a directory path like ``build_dir/{name}-website{suffix}``."""
    return build_dir / f"{name}-website{suffix}"


@task(namespace="mkcd2app")
def copy_website_template(config_yaml: str) -> ContentDir:
    """
    Copy the template to the build directory.

    Example input: config_yaml
    Example output: racers-website

    :param config_yaml: The raw YAML text of the config file.
    :return: A redun.ContentDir that points to the Vite website template directory.
    """
    config = load_config_from_yaml(config_yaml)
    dst = _website_dir(Path(config.build_dir), config.project.path_friendly_name, "")
    logger.info(f"Website will be copied to {dst}")
    if dst.exists():
        shutil.rmtree(dst)
    with get_template_path("vite-project") as src:
        logger.debug(f"Copying template from {src}")
        shutil.copytree(src, dst)
    logger.debug("Website template copied")
    return ContentDir(str(dst))


@task(namespace="mkcd2app")
def fill_website_template(config_yaml: str,
                          website_path: ContentDir,
                          bin_js_path: ContentFile,
                          support_path: ContentDir) -> ContentDir:
    """
    "Fill" the website template — copy binary.js and support files into ``public/``
    and update the ``<title>``.

    We copy the deps-installed website first so we never mutate a ContentDir
    that another task owns.

    Example intput: racers-website
    Example output: racers-website-filled

    :param config_yaml: The raw YAML text of the config file.
    :param website_path: redun.ContentDir pointing to the deps-installed website.
    :param bin_js_path: redun.ContentFile pointing to the binary JS file.
    :param support_path: redun.ContentDir pointing to the support file directory.
    :return: A redun.ContentDir pointing to the filled website directory.
    """
    logger.info("Filling website template")

    config = load_config_from_yaml(config_yaml)
    src = Path(website_path.path)
    dst = src.parent / f"{src.name}-filled"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

    public_path = dst / "public"
    logger.debug(f"public directory is at {public_path}")

    logger.debug(f"Copying binary.js from {bin_js_path.path}")
    shutil.copy(bin_js_path.path, public_path)

    logger.debug(f"Copying support files from {support_path.path}")
    shutil.copytree(support_path.path, public_path, dirs_exist_ok=True)

    title = config.project.title.format(NAME=config.project.name,
                                        VERSION=config.project.version,
                                        AUTHOR=config.project.author)
    logger.debug(f"Using title \"{title}\" in index.html")
    index_html_path = dst / "index.html"
    index_html_text = index_html_path.read_text()
    index_html_text = index_html_text.replace("<title>vite-project</title>",
                                              f"<title>{title}</title>")
    index_html_path.write_text(index_html_text)

    logger.debug("Website template filled")
    return ContentDir(str(dst))


@task(namespace="mkcd2app")
def install_website_dependencies(website_filled_path: ContentDir) -> ContentDir:
    """
    Make a copy of the template website, then ``npm ci`` in it.

    We copy so that we never mutate a ContentDir that another task owns,
    keeping ContentDir hashes stable for caching.

    Example input: racers-website-filled
    Example output: racers-website-filled-deps

    :param website_filled_path: A redun.ContentDir pointing to the template website.
    :return: A redun.ContentDir pointing to the deps-installed website copy.
    """
    src = Path(website_filled_path.path)
    dst = src.parent / f"{src.name}-deps"
    logger.info(f"Installing website dependencies — copy {src} -> {dst}")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    run_cmd("npm ci", cwd=dst)
    logger.debug("Website dependencies installed")
    return ContentDir(str(dst))
