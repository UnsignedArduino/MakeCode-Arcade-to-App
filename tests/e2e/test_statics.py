import shutil
import subprocess
import time
from collections.abc import Generator
from pathlib import Path

import pytest


def run_build(config_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["mkcd2app", "build", str(config_path)],
        capture_output=True,
        text=True,
        timeout=300,
        check=True,
    )


def run_empty_game_build() -> subprocess.CompletedProcess[str]:
    yaml_path = Path.cwd() / "tests" / "fixtures" / "empty_game_build_to_statics.yaml"
    return run_build(yaml_path)


@pytest.fixture(scope="module")
def empty_game_build_to_statics() -> Generator[None]:
    run_empty_game_build()

    yield

    dir_path = Path.cwd() / "examples" / "testing" / "empty_game_build"
    shutil.rmtree(dir_path)


def test_empty_game_build_to_statics_static(empty_game_build_to_statics: None) -> None:
    build_dir = Path("examples/testing/empty_game_build")
    static_dist = build_dir / "empty-game-website-filled-built" / "dist"

    # check for index.html and assets dir
    assert (static_dist / "index.html").is_file(), "expected index.html file present"
    assert (static_dist / "assets").is_dir(), "expected assets directory present"
    # ensure nonzero amount of css and js files
    css_files = list((static_dist / "assets").glob("*.css"))
    js_files = list((static_dist / "assets").glob("*.js"))
    assert css_files, "expected css files present"
    assert js_files, "expected js files present"


def test_empty_game_build_to_statics_static_singlefile(
    empty_game_build_to_statics: None,
) -> None:
    build_dir = Path("examples/testing/empty_game_build")
    static_singlefile_dist = (
        build_dir / "empty-game-website-filled-singlefile-built" / "dist"
    )

    # ensure no other files or directories are present in the dist
    items = list(static_singlefile_dist.iterdir())
    assert len(items) == 1, (
        f"expected only index.html in {static_singlefile_dist}, found: {[p.name for p in items]}"
    )
    only = items[0]
    assert only.is_file(), "expected only index.html present"
    assert only.name == "index.html", "expected only index.html present"


def test_empty_game_build_to_statics_second_build_caches(
    empty_game_build_to_statics: None,
) -> None:
    start_time = time.monotonic()
    run_empty_game_build()  # this should do nothing file wise, all hit caches
    end_time = time.monotonic()
    elapsed_time = end_time - start_time

    assert elapsed_time < 5, (
        f"expected second build to all hit cache and take less than 5s, took {elapsed_time}s"
    )
