from contextlib import contextmanager
from importlib.resources import as_file, files
from pathlib import Path
from typing import Iterator


@contextmanager
def get_template_path(name: str) -> Iterator[Path]:
    ref = files("mkcd2app").joinpath("templates", name)
    with as_file(ref) as path:
        yield path


@contextmanager
def get_js_tools_path() -> Iterator[Path]:
    ref = files("mkcd2app").joinpath("js_tools")
    with as_file(ref) as path:
        yield path
