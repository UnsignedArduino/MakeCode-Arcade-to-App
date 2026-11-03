import re
import shutil
import subprocess
from collections.abc import Generator
from pathlib import Path

import pytest

from mkcd2app.build_project.inputs.embedded_source import read_embedded_files

TARGET_VERSION = "4.0.14"
BUILD_DIR = Path("examples/testing/empty_game_build")
FILE_BUILD_DIR = Path("examples/testing/empty_game_file_build")
FIXTURES = Path("tests/fixtures")


def run_mkcd2app(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["mkcd2app", *args],
        capture_output=True,
        text=True,
        timeout=600,
        check=True,
    )


def run_empty_game_build(*extra_args: str) -> subprocess.CompletedProcess[str]:
    yaml_path = Path.cwd() / "tests" / "fixtures" / "empty_game_build_to_statics.yaml"
    return run_mkcd2app("build", str(yaml_path), *extra_args)


def parse_job_status_totals(redun_output: str) -> dict[str, int]:
    """
    Parse the ``ALL`` row of the last job status table redun logs after a run.

    This relies on redun's log format, which is stable because redun is pinned.
    Example::

        [redun] | TASK     PENDING RUNNING  FAILED  CACHED    DONE   TOTAL
        [redun] |
        [redun] | ALL            0       0       0       7       0       7
    """
    header = re.findall(r"\| TASK((?:\s+[A-Z]+)+)\s*$", redun_output, re.MULTILINE)
    rows = re.findall(r"\| ALL((?:\s+\d+)+)\s*$", redun_output, re.MULTILINE)
    assert header and rows, f"no redun job status table in output:\n{redun_output}"
    return dict(zip(header[-1].split(), map(int, rows[-1].split()), strict=True))


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


@pytest.fixture(scope="module")
def empty_game_build_to_statics() -> Generator[None]:
    # Clear any previous build (and its redun cache) so the first build runs fully
    run_empty_game_build("--full-rebuild")

    yield

    shutil.rmtree(Path.cwd() / BUILD_DIR)


def test_empty_game_build_to_statics_static(empty_game_build_to_statics: None) -> None:
    static_dist = BUILD_DIR / "empty-game-website-filled-built" / "dist"

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
    static_singlefile_dist = (
        BUILD_DIR / "empty-game-website-filled-singlefile-built" / "dist"
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
    # Nothing changed, so every job should be served from redun's cache
    result = run_empty_game_build()
    totals = parse_job_status_totals(result.stderr)

    assert totals["TOTAL"] > 0, f"expected redun to schedule jobs, got {totals}"
    assert totals["DONE"] == 0 and totals["CACHED"] == totals["TOTAL"], (
        f"expected every job on the second build to hit the cache, got {totals}"
    )


def test_empty_game_file_source_build_to_static() -> None:
    # Same empty game, but exported as a PNG from the 4.0.14 editor (`file` source)
    yaml_path = Path.cwd() / FIXTURES / "empty_game_file_source.yaml"
    try:
        result = run_mkcd2app("build", str(yaml_path), "--full-rebuild")

        source = FILE_BUILD_DIR / "empty-game-source"
        # Extraction keeps the embedded bytes exactly, so compare against the PNG's
        # own contents; the checked-in fixture may have CRLF from git on Windows
        embedded = read_embedded_files(FIXTURES / "embedded" / "empty-game.png")
        assert (source / "main.ts").read_bytes() == embedded["main.ts"].encode()
        expected = FIXTURES / "empty_game" / "main.ts"
        assert (source / "main.ts").read_text(encoding="utf-8") == expected.read_text(
            encoding="utf-8"
        )
        assert (source / "mkc.json").is_file(), "expected mkc.json written"
        # The PNG was saved with the same Arcade version as `target`
        output = result.stdout + result.stderr
        assert "Project was saved with Arcade" not in output

        static_dist = FILE_BUILD_DIR / "empty-game-website-filled-built" / "dist"
        assert (static_dist / "index.html").is_file(), "expected index.html present"
        assert list((static_dist / "assets").glob("*.js")), "expected js files"
    finally:
        shutil.rmtree(Path.cwd() / FILE_BUILD_DIR, ignore_errors=True)
