import os
import re
import shutil
import subprocess
import zipfile
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml
from bs4 import BeautifulSoup
from dulwich import porcelain

from mkcd2app.build_project.inputs.embedded_source import read_embedded_files
from mkcd2app.utils.paths import get_sim_html_path

TARGET_VERSION = "4.0.14"
FIXTURES = Path("tests/fixtures")
MKCD_PROJECTS = "mkcd_projects"  # Next to the configs, which use relative paths
EMPTY_GAME_DIR = FIXTURES / MKCD_PROJECTS / "empty_game"
STATICS_CONFIG = "empty_game_path_build_statics.yaml"
FILE_SOURCE_CONFIG = "empty_game_file_source_build_statics.yaml"
RACERS_SHARE_LINK = "https://arcade.makecode.com/84426-33815-03715-00484"
EMPTY_GAME_TITLE = "<title>Empty Game v0.0.1</title>"
FAVICON = 'href="data:image/x-icon;base64,'
# From binary.js and the simulator, as a build can only have these if it has those
BINARY_JS_MARKER = f'"targetVersion":"{TARGET_VERSION}"'
SIMULATOR_MARKER = "initCurrentRuntime"


def run_mkcd2app(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["mkcd2app", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        env=env,
        check=False,  # pytest.fail below, as CalledProcessError hides the output
    )
    if result.returncode != 0:
        pytest.fail(
            f"`mkcd2app {' '.join(args)}` failed with exit code {result.returncode}\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
    return result


def parse_job_status(redun_output: str) -> dict[str, dict[str, int]]:
    """
    Parse the last job status table redun logs after a run, as {task or "ALL": {column:
    count}}.

    This relies on redun's log format, which is stable because redun is pinned.
    Example::

        [redun] | TASK                PENDING RUNNING  FAILED  CACHED    DONE   TOTAL
        [redun] |
        [redun] | ALL                       0       0       0       7       0       7
        [redun] | mkcd2app.fetch_code       0       0       0       1       0       1
    """
    lines = redun_output.splitlines()
    headers = [i for i, line in enumerate(lines) if "| TASK " in line]
    assert headers, f"no redun job status table in output:\n{redun_output}"
    columns = lines[headers[-1]].split("| TASK", 1)[1].split()
    status: dict[str, dict[str, int]] = {}
    for line in lines[headers[-1] + 1 :]:
        row = re.search(r"\| (\S+)((?:\s+\d+)+)\s*$", line)
        if row:
            counts = map(int, row[2].split())
            status[row[1]] = dict(zip(columns, counts, strict=True))
    assert "ALL" in status, f"no ALL row in job status table:\n{redun_output}"
    return status


def tasks_that_ran(redun_output: str) -> set[str]:
    return {
        task.removeprefix("mkcd2app.")
        for task, counts in parse_job_status(redun_output).items()
        if task != "ALL" and counts["DONE"]
    }


@pytest.fixture(scope="session", autouse=True)
def installed_toolchain_and_target(pytestconfig: pytest.Config) -> Generator[None]:
    # Install into a dir under .pytest_cache instead of the real user dirs; it
    # persists between sessions so reruns hit the install's redun cache
    home = pytestconfig.cache.mkdir("mkcd2app-home")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MKCD2APP_HOME", str(home))
        run_mkcd2app("toolchain", "install")
        run_mkcd2app("target", "install", TARGET_VERSION)
        yield


@dataclass
class Build:
    config: Path

    @property
    def dir(self) -> Path:
        return self.config.parent / "build"

    @property
    def source(self) -> Path:
        return self.dir / "empty-game-source"

    @property
    def static(self) -> Path:
        return self.dir / "empty-game-website-filled-built" / "dist"

    @property
    def singlefile(self) -> Path:
        return self.dir / "empty-game-website-filled-singlefile-built" / "dist"


def make_project(root: Path) -> Build:
    """Copy the empty game and its config to a folder, as the config's paths are relative."""
    shutil.copytree(EMPTY_GAME_DIR, root / MKCD_PROJECTS / "empty_game")
    return Build(Path(shutil.copy(FIXTURES / STATICS_CONFIG, root)))


def read_config(build: Build) -> dict[str, Any]:
    config: dict[str, Any] = yaml.safe_load(build.config.read_text(encoding="utf-8"))
    return config


def write_config(build: Build, config: dict[str, Any]) -> None:
    build.config.write_text(yaml.safe_dump(config), encoding="utf-8")


def assert_is_a_static_website(dist: Path) -> None:
    assert (dist / "index.html").is_file(), "expected index.html present"
    assert list((dist / "assets").glob("*.js")), "expected js files"


# ---------------------------------------------------------- the shared build -----


@pytest.fixture(scope="module")
def empty_game_build_to_statics(tmp_path_factory: pytest.TempPathFactory) -> Build:
    build = make_project(tmp_path_factory.mktemp("statics"))
    shutil.copy(Path("examples") / "Racers icon.png", build.config.parent / "icon.png")
    config = read_config(build)
    config["inputs"]["assets"] = {"icon": {"type": "path", "value": "icon.png"}}
    write_config(build, config)
    run_mkcd2app("build", str(build.config))
    return build


def test_empty_game_build_to_statics_static(empty_game_build_to_statics: Build) -> None:
    static_dist = empty_game_build_to_statics.static

    # check for index.html and assets dir
    assert (static_dist / "index.html").is_file(), "expected index.html file present"
    assert (static_dist / "assets").is_dir(), "expected assets directory present"
    # ensure nonzero amount of css and js files
    css_files = list((static_dist / "assets").glob("*.css"))
    js_files = list((static_dist / "assets").glob("*.js"))
    assert css_files, "expected css files present"
    assert js_files, "expected js files present"
    # Relative asset paths, so the site also works from a subfolder like /<repo>/
    index = (static_dist / "index.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(index, features="html.parser")
    tags = soup.select("script[src], link[rel=stylesheet], link[rel=modulepreload]")
    urls = [str(tag.get("src") or tag.get("href")) for tag in tags]
    assert urls and all(
        url.startswith("./") and (static_dist / url).is_file() for url in urls
    ), f"expected relative asset paths to files in the output, got {urls}"


def test_static_output_has_the_game_and_simulator(
    empty_game_build_to_statics: Build,
) -> None:
    assets = empty_game_build_to_statics.static / "assets"
    # vite.config.ts splits these into their own chunks
    [binary_js] = assets.glob("binary-*.js")
    [simulator] = assets.glob("simulator-*.js")
    assert BINARY_JS_MARKER in binary_js.read_text(encoding="utf-8")
    assert SIMULATOR_MARKER in simulator.read_text(encoding="utf-8")


def test_empty_game_build_to_statics_static_singlefile(
    empty_game_build_to_statics: Build,
) -> None:
    static_singlefile_dist = empty_game_build_to_statics.singlefile

    # ensure no other files or directories are present in the dist
    items = list(static_singlefile_dist.iterdir())
    assert len(items) == 1, (
        f"expected only index.html in {static_singlefile_dist}, found: {[p.name for p in items]}"
    )
    only = items[0]
    assert only.is_file(), "expected only index.html present"
    assert only.name == "index.html", "expected only index.html present"


def test_singlefile_output_has_the_game_and_simulator_inside_it(
    empty_game_build_to_statics: Build,
) -> None:
    text = (empty_game_build_to_statics.singlefile / "index.html").read_text("utf-8")
    assert BINARY_JS_MARKER in text
    assert SIMULATOR_MARKER in text
    soup = BeautifulSoup(text, features="html.parser")
    assert soup.find_all("script", src=True) == []
    assert soup.find_all("link", rel="stylesheet") == []


@pytest.mark.parametrize(
    "get_dist",
    [lambda build: build.static, lambda build: build.singlefile],
    ids=["static", "singlefile"],
)
def test_title_and_icon_reach_the_built_page(
    empty_game_build_to_statics: Build, get_dist: Any
) -> None:
    text = (get_dist(empty_game_build_to_statics) / "index.html").read_text("utf-8")
    assert EMPTY_GAME_TITLE in text
    assert FAVICON in text


@pytest.mark.parametrize(
    "get_page",
    [
        lambda build: build.static / "index.html",
        lambda build: build.singlefile / "index.html",
        lambda build: get_sim_html_path(TARGET_VERSION),
    ],
    ids=["static", "singlefile", "installed-simulator"],
)
def test_nothing_loads_scripts_or_styles_from_the_internet(
    empty_game_build_to_statics: Build, get_page: Any
) -> None:
    # The offline promise
    text = get_page(empty_game_build_to_statics).read_text(encoding="utf-8")
    soup = BeautifulSoup(text, features="html.parser")
    urls = [str(tag["src"]) for tag in soup.find_all("script", src=True)]
    urls += [str(tag.get("href")) for tag in soup.find_all("link", rel="stylesheet")]
    external = [url for url in urls if re.match(r"(https?:)?//", url)]
    assert external == []


def test_empty_game_build_to_statics_second_build_caches(
    empty_game_build_to_statics: Build,
) -> None:
    # Nothing changed, so every job should be served from redun's cache
    result = run_mkcd2app("build", str(empty_game_build_to_statics.config))
    totals = parse_job_status(result.stderr)["ALL"]

    assert totals["TOTAL"] > 0, f"expected redun to schedule jobs, got {totals}"
    assert totals["DONE"] == 0 and totals["CACHED"] == totals["TOTAL"], (
        f"expected every job on the second build to hit the cache, got {totals}"
    )


# ------------------------------------------------------------- code sources -----


def test_empty_game_file_source_build_to_static(tmp_path: Path) -> None:
    # Same empty game, but exported as a PNG from the 4.0.14 editor (`file` source)
    (tmp_path / MKCD_PROJECTS).mkdir()
    png = FIXTURES / MKCD_PROJECTS / "empty-game.png"
    shutil.copy(png, tmp_path / MKCD_PROJECTS)
    build = Build(Path(shutil.copy(FIXTURES / FILE_SOURCE_CONFIG, tmp_path)))

    result = run_mkcd2app("build", str(build.config))

    # Extraction keeps the embedded bytes exactly, so compare against the PNG's
    # own contents; the checked-in fixture may have CRLF from git on Windows
    embedded = read_embedded_files(png)
    assert (build.source / "main.ts").read_bytes() == embedded["main.ts"].encode()
    expected = EMPTY_GAME_DIR / "main.ts"
    assert (build.source / "main.ts").read_text(encoding="utf-8") == expected.read_text(
        encoding="utf-8"
    )
    assert (build.source / "mkc.json").is_file(), "expected mkc.json written"
    # The PNG was saved with the same Arcade version as `target`
    output = result.stdout + result.stderr
    assert "Project was saved with Arcade" not in output

    assert_is_a_static_website(build.static)


def test_empty_game_zip_file_source_build_to_static(tmp_path: Path) -> None:
    # Zip the checked-in empty game the way GitHub's "Download ZIP" lays it out (one
    # <repo>-<branch>/ wrapper folder) and build it as a `file` source
    game_dir = EMPTY_GAME_DIR
    zip_path = tmp_path / "empty_game-master.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.mkdir("empty_game-master")
        for f in sorted(game_dir.iterdir()):
            zf.write(f, f"empty_game-master/{f.name}")

    template = (FIXTURES / FILE_SOURCE_CONFIG).read_text(encoding="utf-8")
    yaml_text = template.replace(f"{MKCD_PROJECTS}/empty-game.png", zip_path.name)
    assert zip_path.name in yaml_text
    build = Build(tmp_path / "empty_game_zip_source.yaml")
    build.config.write_text(yaml_text, encoding="utf-8")

    result = run_mkcd2app("build", str(build.config))

    # The wrapper is stripped and every file comes through byte for byte (the ZIP
    # was made from the checkout, so this holds with CRLF on Windows too)
    extracted = {p.name for p in build.source.iterdir()}
    assert extracted == {p.name for p in game_dir.iterdir()} | {"mkc.json"}
    for f in game_dir.iterdir():
        assert (build.source / f.name).read_bytes() == f.read_bytes(), f.name
    output = result.stdout + result.stderr
    assert "Project was saved with Arcade" not in output

    assert_is_a_static_website(build.static)
    assert [p.name for p in build.singlefile.iterdir()] == ["index.html"]


def test_git_source_build_to_static(tmp_path: Path) -> None:
    # A local repo, so this runs real dulwich without needing the network
    game_dir = EMPTY_GAME_DIR
    repo = (tmp_path / "repo").resolve()
    shutil.copytree(game_dir, repo)
    porcelain.init(str(repo))
    porcelain.add(str(repo), [str(path) for path in repo.iterdir() if path.is_file()])
    # sign=False so a commit.gpgsign in the user's git config doesn't apply
    identity = b"Test <test@example.com>"
    porcelain.commit(
        str(repo),
        message=b"Add game",
        author=identity,
        committer=identity,
        sign=False,
    )

    (tmp_path / "project").mkdir()
    build = Build(Path(shutil.copy(FIXTURES / STATICS_CONFIG, tmp_path / "project")))
    config = read_config(build)
    config["inputs"]["code"] = {"type": "git", "url": repo.as_uri()}
    write_config(build, config)

    run_mkcd2app("build", str(build.config))

    for f in game_dir.iterdir():
        assert (build.source / f.name).read_bytes() == f.read_bytes(), f.name
    assert (build.source / ".git").is_dir()
    assert_is_a_static_website(build.static)


@pytest.mark.network
def test_share_link_source_build_to_static(tmp_path: Path) -> None:
    build = make_project(tmp_path)
    config = read_config(build)
    config["inputs"]["code"] = {"type": "share_link", "value": RACERS_SHARE_LINK}
    write_config(build, config)

    run_mkcd2app("build", str(build.config))

    assert (build.source / "pxt.json").is_file()
    assert_is_a_static_website(build.static)


# ------------------------------------------------------------ without a network -----


def blocked_env(log: Path) -> dict[str, str]:
    """The environment for a subprocess that can't reach the network."""
    preload = (FIXTURES / "block_network.cjs").resolve().as_posix()
    dead_proxy = "http://127.0.0.1:9"  # Python's requests honours these
    return {
        **os.environ,
        "NODE_OPTIONS": f'--require "{preload}"',
        "MKCD2APP_TEST_BLOCKED_LOG": str(log),
        "HTTP_PROXY": dead_proxy,
        "HTTPS_PROXY": dead_proxy,
        "npm_config_offline": "true",
    }


def read_blocked(log: Path) -> list[str]:
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def test_network_blocker_really_blocks(tmp_path: Path) -> None:
    # Guards the fixture: the tests below would pass by accident if this did nothing
    log = tmp_path / "blocked.log"
    script = "fetch('https://example.com').then(() => process.exit(0), () => process.exit(3))"
    result = subprocess.run(
        ["node", "-e", script], env=blocked_env(log), timeout=60, check=False
    )
    assert result.returncode == 3
    assert read_blocked(log) == ["example.com:443"]


@dataclass
class OfflineBuilds:
    build: Build
    blocked: list[str]
    title_edit_output: str


@pytest.fixture(scope="module")
def offline_builds(tmp_path_factory: pytest.TempPathFactory) -> OfflineBuilds:
    """A full build, then a rebuild after editing the title, with no network."""
    root = tmp_path_factory.mktemp("offline")
    log = root / "blocked.log"
    env = blocked_env(log)
    build = make_project(root)
    run_mkcd2app("build", str(build.config), env=env)

    config = read_config(build)
    config["project"]["title"] = "Edited Title"
    write_config(build, config)
    result = run_mkcd2app("build", str(build.config), env=env)

    return OfflineBuilds(build, read_blocked(log), result.stderr)


def test_build_needs_no_network(offline_builds: OfflineBuilds) -> None:
    # The empty game has no extensions, so everything should be vendored. The one
    # exception is `mkc`'s update check, once a day: when it fails, `mkc` logs that and
    # carries on, so whether it's tried here depends on the age of `mkc`'s cache.
    assert set(offline_builds.blocked) <= {"arcade.makecode.com:443"}
    assert_is_a_static_website(offline_builds.build.static)
    assert [p.name for p in offline_builds.build.singlefile.iterdir()] == ["index.html"]


def test_title_edit_reaches_the_output(offline_builds: OfflineBuilds) -> None:
    for dist in (offline_builds.build.static, offline_builds.build.singlefile):
        text = (dist / "index.html").read_text(encoding="utf-8")
        assert "<title>Edited Title</title>" in text


def test_title_edit_only_rebuilds_the_website(offline_builds: OfflineBuilds) -> None:
    assert tasks_that_ran(offline_builds.title_edit_output) == {
        "build_project",
        "fill_website_template",
        "build_website",
        "build_website_singlefile",
    }
