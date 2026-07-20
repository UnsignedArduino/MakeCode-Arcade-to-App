import logging
import shutil
from pathlib import Path

from redun import task
from redun.file import ContentDir, ContentFile

from mkcd2app.config import BuildConfig
from mkcd2app.utils.logger import create_logger
from mkcd2app.utils.resources import get_template_path
from mkcd2app.utils.run import run_cmd

logger = create_logger(name=__name__, level=logging.INFO)


@task(namespace="mkcd2app")
def copy_website_template(config: BuildConfig) -> ContentDir:
    """
    Copy the template to the build directory.

    :param config: App build configuration
    :return: A redun.ContentDir that points to the Vite website directory.
    """
    website_path = Path(
        config.build_dir) / f"{config.project.path_friendly_name}-website"
    logger.info(f"Website will be copied to {website_path}")

    with get_template_path("vite-project") as website_template_path:
        logger.debug(f"Copying template from {website_template_path}")
        shutil.copytree(website_template_path, website_path, dirs_exist_ok=True)

    logger.debug("Website template copied")
    return ContentDir(str(website_path))


@task(namespace="mkcd2app")
def install_website_dependencies(website_path: ContentDir) -> ContentDir:
    """
    `npm ci` in the website.

    :param website_path: A redun.ContentDir that points to the Vite website directory.
    :return: A redun.ContentDir that points to the node_modules directory for the
     website, this is only used so that redun will see some tasks depend on the website
     dependencies being installed.
    """
    website_path = Path(website_path.path)
    logger.info(f"Installing website dependencies for {website_path}")

    run_cmd("npm ci", cwd=website_path)

    logger.debug("Website dependencies installed")
    return ContentDir(str(website_path / "node_modules"))


@task(namespace="mkcd2app")
def fill_website_template(config: BuildConfig,
                          website_path: ContentDir,
                          bin_js_path: ContentFile,
                          support_path: ContentDir) -> ContentDir:
    """
    "Fill" the website template. (Currently just need to copy files to public directory)

    :param config: App build configuration
    :param website_path: redun.ContentDir that points to the Vite website directory.
    :param bin_js_path: redun.ContentFile that points to the binary JS file.
    :param support_path: redun.ContentDir that points to the support file directory.
    :return: A redun.ContentDir that points to the Vite website directory (same as 
     website_path but with different hash now)
    """
    logger.info("Filling website template")

    website_path = Path(website_path.path)
    public_path = website_path / "public"
    logger.debug(f"public directory is at {public_path}")

    logger.debug(f"Copying binary.js from {bin_js_path.path}")
    shutil.copy(bin_js_path.path, public_path)

    logger.debug(f"Copying support files from {support_path.path}")
    shutil.copytree(support_path.path, public_path, dirs_exist_ok=True)

    title = config.project.title.format(NAME=config.project.name,
                                        VERSION=config.project.version,
                                        AUTHOR=config.project.author)
    logger.debug(f"Using title \"{title}\"")
    index_html_path = website_path / "index.html"
    index_html_text = index_html_path.read_text()
    index_html_text = index_html_text.replace("<title>vite-project</title>",
                                              f"<title>{title}</title>")
    index_html_path.write_text(index_html_text)

    logger.debug("Website template filled")
    return ContentDir(str(website_path))
