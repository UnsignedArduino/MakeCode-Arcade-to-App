from mkcd2app.utils.resources import (
    get_resource_empty_project_path,
    get_resource_js_tools_path,
    get_resource_template_path,
)


def test_templates_dir() -> None:
    with get_resource_template_path() as path:
        assert (path / "vite-project").is_dir()


def test_vite_template() -> None:
    with get_resource_template_path("vite-project") as path:
        for name in ("package.json", "package-lock.json", "index.html"):
            assert (path / name).is_file(), name
        # fill_website_template copies binary.js and the simulator in here
        assert (path / "src" / "assets").is_dir()


def test_js_tools() -> None:
    with get_resource_js_tools_path() as path:
        assert (path / "package.json").is_file()
        assert (path / "package-lock.json").is_file()


def test_empty_project() -> None:
    with get_resource_empty_project_path() as path:
        assert (path / "pxt.json").is_file()
        assert (path / "main.ts").is_file()
