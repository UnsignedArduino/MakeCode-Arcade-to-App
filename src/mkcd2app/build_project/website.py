import base64
import json
import logging
import shutil
from pathlib import Path

from redun import task
from redun.file import ContentDir, ContentFile

from mkcd2app.config import load_config_from_yaml
from mkcd2app.utils.logger import create_logger
from mkcd2app.utils.paths import get_templates_npm_cache_dir
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
def fill_website_template(
    config_yaml: str,
    website_path: ContentDir,
    bin_js_path: ContentFile,
    support_path: ContentDir,
) -> ContentDir:
    """
    "Fill" the website template

    Example intput: racers-website
    Example output: racers-website-filled

    :param config_yaml: The raw YAML text of the config file.
    :param website_path: redun.ContentDir pointing to the copied website template.
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

    title = config.project.title.format(
        NAME=config.project.name,
        VERSION=config.project.version,
        AUTHOR=config.project.author,
    )
    logger.debug(f'Using title "{title}" in index.html')
    index_html_path = dst / "index.html"
    index_html_text = index_html_path.read_text(encoding="utf-8")
    index_html_text = index_html_text.replace(
        "<title>vite-project</title>", f"<title>{title}</title>"
    )

    favicon_path = Path(support_path.path) / "favicon.ico"
    if favicon_path.exists():
        favicon_b64 = base64.b64encode(favicon_path.read_bytes()).decode("ascii")
        favicon_data_uri = f"data:image/x-icon;base64,{favicon_b64}"
        index_html_text = index_html_text.replace(
            '<link rel="icon" href="./favicon.ico" type="image/x-icon" />',
            f'<link rel="icon" href="{favicon_data_uri}" type="image/x-icon" />',
        )
        logger.debug("Inlined favicon.ico into index.html")

    index_html_path.write_text(index_html_text, encoding="utf-8")

    logger.debug("Updating package.json")
    package_json_path = dst / "package.json"
    package_json = json.loads(package_json_path.read_text(encoding="utf-8"))
    package_json["name"] = config.project.path_friendly_name
    package_json["version"] = config.project.version
    package_json["description"] = config.project.description
    package_json["authors"] = {"name": config.project.author}
    package_json_path.write_text(json.dumps(package_json, indent=2), encoding="utf-8")

    logger.debug("Website template filled")
    return ContentDir(str(dst))


@task(namespace="mkcd2app")
def install_website_deps(
    deps_dir: str, package_json: ContentFile, package_lock: ContentFile
) -> ContentDir:
    """
    ``npm ci`` the template's dependencies in their own directory.

    Only package.json and package-lock.json are inputs, so changing the game or its
    assets doesn't bust the cached install. The template's unfilled package.json is
    used because filling only changes metadata that ``npm ci`` ignores.

    Example input: racers-website-deps, package.json, package-lock.json
    Example output: racers-website-deps/node_modules

    :param deps_dir: The directory to install into.
    :param package_json: A redun.ContentFile pointing to the template's package.json.
    :param package_lock: A redun.ContentFile pointing to the template's lockfile.
    :return: A redun.ContentDir pointing to the installed node_modules.
    """
    dst = Path(deps_dir)
    logger.info("Installing website dependencies")

    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    shutil.copy(package_json.path, dst / "package.json")
    shutil.copy(package_lock.path, dst / "package-lock.json")

    cache_path = get_templates_npm_cache_dir()
    logger.debug(f"Using template npm cache at {cache_path} to install")

    run_cmd(["npm", "ci", "--cache", str(cache_path), "--offline"], cwd=dst)
    logger.debug("Website dependencies installed")

    return ContentDir(str(dst / "node_modules"))


def _copy_site_with_deps(src: Path, dst: Path, node_modules: ContentDir) -> None:
    """Copy the filled site to ``dst`` and put a copy of ``node_modules`` in it."""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    # Keep symlinks as symlinks: on POSIX node_modules/.bin entries are relative
    #  symlinks, and copying their targets breaks the scripts' relative imports
    shutil.copytree(node_modules.path, dst / "node_modules", symlinks=True)


@task(namespace="mkcd2app")
def build_website(
    website_filled_path: ContentDir, node_modules: ContentDir
) -> ContentDir:
    """
    Make a copy of the filled website with node_modules, then `npm run build` in it.

    We copy so that we never mutate a ContentDir that another task owns,
    keeping ContentDir hashes stable for caching.

    Example input: racers-website-filled, racers-website-deps/node_modules
    Example output: racers-website-filled-built/dist

    :param website_filled_path: A redun.ContentDir pointing to the filled website.
    :param node_modules: A redun.ContentDir pointing to the installed dependencies.
    :return: A redun.ContentDir pointing to the directory of static HTML/CSS/JS files
     ready to serve.
    """
    src = Path(website_filled_path.path)
    dst = src.parent / f"{src.name}-built"
    logger.info("Building website to static HTML/CSS/JS")

    _copy_site_with_deps(src, dst, node_modules)

    run_cmd(["npm", "run", "build"], cwd=dst)
    logger.debug("Website built successfully")

    actual_dist = dst / "dist"

    logger.debug(f"Static HTML/CSS/JS files at {actual_dist}")

    return ContentDir(str(actual_dist))


@task(namespace="mkcd2app")
def build_website_singlefile(
    website_filled_path: ContentDir, node_modules: ContentDir
) -> ContentFile:
    """
    Make a copy of the filled website with node_modules, then
    `npm run build:singlefile` in it.

    We copy so that we never mutate a ContentDir that another task owns,
    keeping ContentDir hashes stable for caching.

    Example input: racers-website-filled, racers-website-deps/node_modules
    Example output: index.html

    :param website_filled_path: A redun.ContentDir pointing to the filled website.
    :param node_modules: A redun.ContentDir pointing to the installed dependencies.
    :return: A redun.ContentFile pointing to the single-file HTML.
    """
    src = Path(website_filled_path.path)
    dst = src.parent / f"{src.name}-singlefile-built"
    logger.info("Building website to static HTML file")

    _copy_site_with_deps(src, dst, node_modules)

    run_cmd(["npm", "run", "build:singlefile"], cwd=dst)
    logger.debug("Website built successfully")

    actual_dist = dst / "dist" / "index.html"

    logger.debug(f"Static HTML file at {actual_dist}")

    return ContentFile(str(actual_dist))
