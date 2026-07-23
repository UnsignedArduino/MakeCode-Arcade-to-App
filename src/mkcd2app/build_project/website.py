import base64
import json
import logging
import shutil
from pathlib import Path

from redun import task
from redun.file import ContentDir, ContentFile

from mkcd2app.config import load_config_from_yaml
from mkcd2app.utils.logger import create_logger
from mkcd2app.utils.run import run_cmd

logger = create_logger(name=__name__, level=logging.INFO)


def _website_dir(build_dir: Path, name: str, suffix: str) -> Path:
    """Return a directory path like ``build_dir/{name}-website{suffix}``."""
    return build_dir / f"{name}-website{suffix}"


@task(namespace="mkcd2app")
def copy_website_template(config_yaml: str, template_src: ContentDir) -> ContentDir:
    """
    Copy the template to the build directory.

    Example input: config_yaml, template_src
    Example output: racers-website

    :param config_yaml: The raw YAML text of the config file.
    :param template_src: A redun.ContentDir pointing to the template source,
                         so that redun tracks changes to template files.
    :return: A redun.ContentDir that points to the Vite website template directory.
    """
    config = load_config_from_yaml(config_yaml)
    dst = _website_dir(Path(config.build_dir), config.project.path_friendly_name, "")
    logger.info(f"Website will be copied to {dst}")
    if dst.exists():
        shutil.rmtree(dst)
    logger.debug(f"Copying template from {template_src.path}")
    shutil.copytree(template_src.path, dst)
    logger.debug("Website template copied")
    return ContentDir(str(dst))


@task(namespace="mkcd2app")
def fill_website_template(config_yaml: str,
                          website_path: ContentDir,
                          bin_js_path: ContentFile,
                          support_path: ContentDir) -> ContentDir:
    """
    "Fill" the website template

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
    asset_path = dst / "src" / "assets"
    logger.debug(f"public directory is at {public_path}")
    logger.debug(f"asset directory is at {asset_path}")

    logger.debug(f"Copying binary.js from {bin_js_path.path}")
    shutil.copy(bin_js_path.path, asset_path)

    simulator_html_path = Path(support_path.path) / "---simulator.html"
    logger.debug(f"Copying ---simulator.html from {simulator_html_path}")
    shutil.copy(simulator_html_path, asset_path)

    title = config.project.title.format(NAME=config.project.name,
                                        VERSION=config.project.version,
                                        AUTHOR=config.project.author)
    logger.debug(f"Using title \"{title}\" in index.html")
    index_html_path = dst / "index.html"
    index_html_text = index_html_path.read_text()
    index_html_text = index_html_text.replace("<title>vite-project</title>",
                                              f"<title>{title}</title>")

    favicon_path = Path(support_path.path) / "favicon.ico"
    if favicon_path.exists():
        favicon_b64 = base64.b64encode(favicon_path.read_bytes()).decode("ascii")
        favicon_data_uri = f"data:image/x-icon;base64,{favicon_b64}"
        index_html_text = index_html_text.replace(
            '<link rel="icon" href="./favicon.ico" type="image/x-icon" />',
            f'<link rel="icon" href="{favicon_data_uri}" type="image/x-icon" />'
        )
        favicon_path.unlink()
        logger.debug("Inlined favicon.ico into index.html and removed from public/")

    index_html_path.write_text(index_html_text)

    logger.debug("Updating package.json")
    package_json_path = dst / "package.json"
    package_json = json.loads(package_json_path.read_text())
    package_json["name"] = config.project.path_friendly_name
    package_json["version"] = config.project.version
    package_json["description"] = config.project.description
    package_json["authors"] = {
        "name": config.project.author
    }
    package_json_path.write_text(json.dumps(package_json, indent=2))

    logger.debug("Website template filled")
    return ContentDir(str(dst))


@task(namespace="mkcd2app")
def install_deps_and_build_website(website_filled_path: ContentDir) -> ContentDir:
    """
    Make a copy of the template website, then ``npm ci`` and `npm run build` in it.

    We copy so that we never mutate a ContentDir that another task owns,
    keeping ContentDir hashes stable for caching.

    Example input: racers-website-filled
    Example output: racers-website-filled-built

    :param website_filled_path: A redun.ContentDir pointing to the template website.
    :return: A redun.ContentDir pointing to the directory of static HTML/CSS/JS files
     ready to serve. 
    """
    src = Path(website_filled_path.path)
    dst = src.parent / f"{src.name}-built"
    logger.info(f"Installing website dependencies and building to static HTML/CSS/JS")

    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

    run_cmd(["npm", "ci"], cwd=dst)
    logger.debug("Website dependencies installed")

    run_cmd(["npm", "run", "build"], cwd=dst)
    logger.debug("Website built successfully")

    actual_dist = dst / "dist"

    logger.debug(f"Static HTML/CSS/JS files at {actual_dist}")

    return ContentDir(str(actual_dist))
