import json
import logging
import shutil
from pathlib import Path
from typing import Callable

import requests
from bs4 import BeautifulSoup

from mkcd_to_app.config import Config, SourceType
from utils.cmd import run_shell_command
from utils.logger import create_logger

logger = create_logger(name=__name__, level=logging.INFO)


def generate_website(config: Config, prj_name: str, cwd: Path, bin_js_path: Path):
    """
    Generate the website by initializing a React TS Vite project, copying the necessary
    files, and substituting the correct values in.

    :param config: The configuration object containing the project information.
    :param prj_name: The name of the project.
    :param cwd: The current working directory where the project will be created.
    :param bin_js_path: The path to the binary.js file.
    """
    logger.debug(f"Creating React TS Vite project for {prj_name}")
    # Initialize a React TS Vite project
    if (cwd / prj_name).exists():
        logger.debug(f"Project {prj_name} already exists, continuing...")
    else:
        run_shell_command(f"yarn create vite {prj_name} -t react-ts", cwd=cwd)
    # Start copying files
    old_dir = Path.cwd() / "website_files"
    new_dir = cwd / prj_name

    def copy_template(file_name: str, callback: Callable[[str], str] = lambda x: x):
        (new_dir / file_name).write_text(callback((old_dir / file_name).read_text()))

    logger.debug(f"Copying website files from {old_dir} to {new_dir}")
    # Copy index.html and substituting the correct values
    copy_template("index.html",
                  lambda x: x.format(NAME=config.name, VERSION=config.version,
                                     AUTHOR=config.author))
    # Copy eslint.config.js
    copy_template("eslint.config.js")
    # Modify package.json
    package_json = json.loads((old_dir / "package.json").read_text())
    package_json["name"] = prj_name
    package_json["version"] = config.version
    package_json["description"] = config.description
    package_json["author"] = config.author
    package_json["scripts"] = {
        "dev": "vite",
        "lint": "eslint .",
        "writeLint": "eslint --fix .",
        "format": "prettier --check .",
        "writeFormat": "prettier --write .",
        "build": "tsc -b && vite build",
        "preview": "vite preview"
    }
    (new_dir / "package.json").write_text(json.dumps(package_json, indent=2))
    # Queue dependencies to add (these will be "yarn add"ed)
    dependencies = ["react-toastify"]
    dev_dependencies = ["eslint-plugin-react-dom", "eslint-plugin-react-x", "prettier"]
    # Copy README.md
    copy_template("README.md",
                  lambda x: x.format(WEBSITE_NAME=prj_name,
                                     SOURCE=f"{config.source} @ {config.source_checkout}" if config.source_type == SourceType.GITHUB else config.source))
    # Copy .prettierignore
    copy_template(".prettierignore")
    # yarn
    run_shell_command("yarn", cwd=new_dir)
    # yarn add stuff
    run_shell_command(f"yarn add {" ".join(dependencies)}", cwd=new_dir)
    run_shell_command(f"yarn add {" ".join(dev_dependencies)} --dev", cwd=new_dir)
    # Clear public directory
    if (new_dir / "public").exists():
        shutil.rmtree(new_dir / "public")
    (new_dir / "public").mkdir(parents=True, exist_ok=True)
    # Clear src/assets directory
    if (new_dir / "src" / "assets").exists():
        shutil.rmtree(new_dir / "src" / "assets")
    # Copy src directory
    shutil.copytree(old_dir / "src", new_dir / "src", dirs_exist_ok=True)
    game_config_ts_path = new_dir / "src" / "gameConfiguration.ts"
    logger.debug(f"gameConfiguration.ts at {game_config_ts_path}")
    # Copy binary.js
    logger.debug(f"Copying binary.js from {bin_js_path}")
    shutil.copy(bin_js_path, new_dir / "public" / "binary.js")
    # Download https://trg-arcade.userpxt.io/---simulator
    logger.debug("Downloading simulator files")
    res = requests.get("https://trg-arcade.userpxt.io/---simulator")
    if res.ok:
        sim_html = res.text
    else:
        logger.error(f"Failed to download simulator: {res.status_code} {res.reason}")
        raise Exception(f"Failed to download simulator: {res.status_code} {res.reason}")
    # Analyze simulator HTML for required CSS and JS files
    logger.debug("Analyzing simulator HTML for required CSS and JS files")
    soup = BeautifulSoup(sim_html)
    css_links = soup.find_all("link", rel="stylesheet")
    js_scripts = soup.find_all("script")
    logger.debug(f"Found {len(css_links)} CSS links and {len(js_scripts)} JS scripts")
    for css in css_links:
        if css.get("href"):
            css_url = css.get("href")
            logger.debug(f"Downloading CSS file: {css_url}")
            res = requests.get(css_url)
            if res.ok:
                # Download CSS file
                (new_dir / "public" / css_url.split("/")[-1]).write_text(res.text)
                # Rewrite CSS file to use relative paths
                css["href"] = css_url.split("/")[-1]
            else:
                logger.error(
                    f"Failed to download CSS file: {res.status_code} {res.reason}")
                raise Exception(
                    f"Failed to download CSS file: {res.status_code} {res.reason}")
    for js in js_scripts:
        if js.get("src"):
            js_url = js.get("src")
            logger.debug(f"Downloading JS file: {js_url}")
            res = requests.get(js_url)
            if res.ok:
                # Download JS file
                (new_dir / "public" / js_url.split("/")[-1]).write_text(res.text)
                # Rewrite JS file to use relative paths
                js["src"] = js_url.split("/")[-1]
            else:
                logger.error(
                    f"Failed to download JS file: {res.status_code} {res.reason}")
                raise Exception(
                    f"Failed to download JS file: {res.status_code} {res.reason}")
    sim_html = soup.prettify(formatter="html5")
    (new_dir / "public" / "---simulator.html").write_text(sim_html)
