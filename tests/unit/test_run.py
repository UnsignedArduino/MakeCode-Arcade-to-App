import sys
from pathlib import Path

import pytest

from mkcd2app.utils import paths
from mkcd2app.utils.run import BuildError, run_cmd


def python(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_returns_stdout(tmp_path: Path) -> None:
    assert run_cmd(python("print('hello')"), cwd=tmp_path).strip() == "hello"


def test_runs_in_cwd(tmp_path: Path) -> None:
    out = run_cmd(python("import os; print(os.getcwd())"), cwd=tmp_path)
    assert Path(out.strip()).samefile(tmp_path)


def test_accepts_str_cwd(tmp_path: Path) -> None:
    assert run_cmd(python("print(1)"), cwd=str(tmp_path)).strip() == "1"


def test_failure_raises_build_error(tmp_path: Path) -> None:
    command = python(
        "import sys; print('to stdout'); print('to stderr', file=sys.stderr); "
        "sys.exit(3)"
    )
    with pytest.raises(BuildError) as exc_info:
        run_cmd(command, cwd=tmp_path)
    err = exc_info.value
    assert err.returncode == 3
    assert err.command == command
    assert err.cwd == tmp_path
    assert "to stdout" in err.output
    assert "to stderr" in err.output
    assert "(3)" in str(err)


def test_missing_executable(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="definitely-not-a-real-program"):
        run_cmd(["definitely-not-a-real-program"], cwd=tmp_path)


def test_which_path_limits_search(tmp_path: Path) -> None:
    # The interpreter's own name is on PATH, but not in an empty which_path dir
    name = Path(sys.executable).name
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        run_cmd([name, "-c", "pass"], cwd=tmp_path, which_path=empty)


def test_which_path_finds_executable(tmp_path: Path) -> None:
    exe = Path(sys.executable)
    out = run_cmd(
        [exe.name, "-c", "print('found')"], cwd=tmp_path, which_path=exe.parent
    )
    assert out.strip() == "found"


def _write_fake_mkc(bin_dir: Path) -> None:
    """A tiny ``mkc`` that prints ok, runnable through shutil.which on any OS."""
    bin_dir.mkdir(parents=True)
    if sys.platform == "win32":
        (bin_dir / "mkc.cmd").write_text("@echo ok\r\n", encoding="utf-8")
    else:
        exe = bin_dir / "mkc"
        exe.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
        exe.chmod(0o755)


def test_relative_home_executable_runs_from_other_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression: a relative MKCD2APP_HOME gave a relative which_path, so the
    #  resolved executable didn't exist from the subprocess's cwd
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(paths.HOME_ENV_VAR, "home")
    _write_fake_mkc(paths.get_js_tools_bin_dir())
    other = tmp_path / "build"
    other.mkdir()

    out = run_cmd(
        ["mkc", "build", "-j"], cwd=other, which_path=paths.get_js_tools_bin_dir()
    )

    assert out.strip() == "ok"


def test_relative_home_cache_dir_is_same_from_other_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression: npm got a relative --cache, which it resolved against its own cwd
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(paths.HOME_ENV_VAR, "home")
    cache = paths.get_templates_npm_cache_dir()
    other = tmp_path / "build"
    other.mkdir()

    run_cmd(
        python("import pathlib, sys; pathlib.Path(sys.argv[1]).mkdir(parents=True)")
        + [str(cache)],
        cwd=other,
    )

    assert (tmp_path / "home").resolve() in cache.parents
    assert cache.is_dir()
    assert not (other / "home").exists()
