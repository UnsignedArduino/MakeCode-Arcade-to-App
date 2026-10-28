# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Rewrite status, branch/PR stack, roadmap, and known bugs live in the project context
doc, which is imported here. Update that doc (and its "verified as of" line) rather
than duplicating its content in this file.

@docs/PROJECT_CONTEXT.md

## Commands

Python ≥3.14 and Node.js (LTS) are required. Everything runs through uv.

```bash
uv sync                          # install deps + the mkcd2app entry point
uv run ruff check .              # lint
uv run ruff format --check .     # format check (drop --check to apply)
uv run mypy .                    # strict type check
uv run pytest                    # all tests
uv run pytest tests/e2e/test_statics.py::test_empty_game_build_to_statics_static
```

CI (`lint.yaml`, `e2e.yaml`) runs exactly these lint/format/mypy/pytest commands.
pre-commit runs ruff check, ruff format --check, and mypy on staged Python files.

Running the tool end to end (installs must happen first, in this order):

```bash
uv run mkcd2app toolchain install
uv run mkcd2app target install 4.0.14
uv run mkcd2app --debug build "examples/Racers.yaml"
```

Notes on the e2e tests:
- Run pytest from the repo root: tests use `Path.cwd()` and repo-relative paths, and
  shell out to the installed `mkcd2app` executable rather than importing it.
- Builds go to `examples/testing/empty_game_build/`, which the module fixture deletes.

## Architecture

Every unit of work is a redun `@task(namespace="mkcd2app")`. `main.py` parses the CLI
and hands a task expression to `run_redun_task()` with the SQLite DB for that command.
redun builds the DAG from how task results feed into other tasks, so data dependencies
between tasks must go through task arguments/returns, not side channels.

Build pipeline (`build_project/__init__.py`), each step a task:
`fetch_code` → `build_binary_js` (runs `mkc`) + `copy_support_files` (simulator HTML
from the target dir, icon) + `copy_website_template` → `fill_website_template` → one
`install_deps_and_build_website*` task per entry in `outputs`. A new output type means
a new `case` arm in that `match` plus a field on `BuildProjectResult`.

Conventions that matter for redun hashing:
- Tasks take the config as the raw YAML string and call `load_config_from_yaml` inside;
  never pass pydantic models as task arguments.
- Each stage writes to a fresh directory (named via `_website_dir` in `website.py`) and
  returns a `ContentDir`/`ContentFile`; never modify a path another task returned.
- `mkcd2app/__init__.py` imports `_redun_compat` first, which monkey-patches redun and
  asserts the pinned version. Changing the redun version means re-checking those patches.

Paths under the user data/state dirs (toolchain, `js_tools/node_modules/.bin` for `mkc`,
npm cache, per-version target dirs, redun DBs) all come from `utils/paths.py`; use those
helpers instead of building paths by hand. Bundled templates and fixtures under
`resources/` are reached through `utils/resources.py`.
