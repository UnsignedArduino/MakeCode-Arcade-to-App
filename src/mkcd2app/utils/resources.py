from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import as_file, files
from pathlib import Path


@contextmanager
def get_template_path(name: str) -> Iterator[Path]:
    ref = files("mkcd2app").joinpath("resources", "templates", name)
    with as_file(ref) as path:
        yield path


@contextmanager
def get_js_tools_path() -> Iterator[Path]:
    ref = files("mkcd2app").joinpath("resources", "js_tools")
    with as_file(ref) as path:
        yield path
