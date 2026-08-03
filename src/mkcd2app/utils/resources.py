from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import as_file, files
from pathlib import Path


@contextmanager
def get_resource_template_path(name: str | None = None) -> Iterator[Path]:
    ref = files("mkcd2app").joinpath("resources", "templates")
    if name:
        ref.joinpath(name)
    with as_file(ref) as path:
        yield path


@contextmanager
def get_resource_js_tools_path() -> Iterator[Path]:
    ref = files("mkcd2app").joinpath("resources", "js_tools")
    with as_file(ref) as path:
        yield path


@contextmanager
def get_resource_empty_project_path() -> Iterator[Path]:
    ref = files("mkcd2app").joinpath("resources", "empty_project")
    with as_file(ref) as path:
        yield path
