import sys
from pathlib import Path

import pytest

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
