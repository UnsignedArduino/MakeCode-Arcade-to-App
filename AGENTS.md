# AGENTS.md

This file provides guidance to AI coding agents when working with code in this repository.

Rewrite status, branch/PR stack, roadmap, and known bugs live in the project context
doc, [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md). Read it before starting work.
Update that doc (and its "verified as of" line) rather than duplicating its content in
this file.

## Commands

Python ≥3.14 and Node.js (LTS) are required. Everything runs through uv.

```bash
uv sync                          # install deps + the mkcd2app entry point
uv run ruff check .              # lint
uv run ruff format --check .     # format check (drop --check to apply)
uv run mypy .                    # strict type check
uv run pytest                    # all tests, with a coverage report
uv run pytest -m unit            # only the fast offline tests (tests/unit)
uv run pytest -m integration     # only the offline scheduler tests (tests/integration)
uv run pytest -m e2e --no-cov    # only the e2e tests (tests/e2e)
uv run pytest --no-cov           # skip coverage (e.g. when using a debugger)
uv run pytest tests/e2e/test_statics.py::test_empty_game_build_to_statics_static
```

CI runs exactly these commands: `lint.yaml` the lint/format/mypy checks, and
`unit.yaml` (`-m unit`), `integration.yaml` (`-m integration`) and `e2e.yaml`
(`-m e2e --no-cov`) the tests, independently, on ubuntu/windows/macos. Every test must
be under `tests/unit`, `tests/integration` or `tests/e2e`, or collection fails, since a
test anywhere else would run in no workflow. Test file names must be unique across those
folders, since they have no `__init__.py`. Warnings are errors in pytest.
On a PR, `[skip-<tier>-tests]`, `[no-<tier>-tests]`, `[skip-<tier>]` or `[no-<tier>]` in
the last commit's message skips that tier (`unit`, `integration` or `e2e`; see
`check-skip.yaml`), `[skip-tests]` or `[no-tests]` skips all three, and GitHub's own
`[skip ci]` skips every workflow. Pushes to `main` ignore all but `[skip ci]`.
pre-commit runs ruff check, ruff format --check, and mypy on staged Python files.

Running the tool end to end (installs must happen first, in this order):

```bash
uv run mkcd2app toolchain install
uv run mkcd2app target install 4.0.14
uv run mkcd2app --debug build "examples/Racers.yaml"
```

Notes on the tests:
- `tests/conftest.py` marks every test with its tier by its directory, and holds the
  shared fixtures, such as `mkcd2app_home` (points `MKCD2APP_HOME` at a temp dir). Keep
  it the only `conftest.py`: mypy fails on two modules both named `conftest`.
- Shared helpers (`make_config_yaml`, `FakeRunCmd`, `capture_logger`, ...) are in
  `tests/helpers.py`, imported as `from helpers import ...`.

Notes on the unit tests:
- Call a redun task's plain function with `.func(...)`, and monkeypatch `run_cmd` in
  the module under test, so no `npm`/`mkc` runs.
- Our loggers set `propagate = False`, so `caplog` needs `capture_logger` to see them.

Notes on the integration tests:
- They run the real `main()` and redun scheduler in this process, with `run_cmd` faked,
  so no Node.js is needed. Use the `project` fixture (a game with a config and an
  installed target) or `cli` (runs any command), which return what ran as a `Ran`.
- `FakeToolchain` does to the disk what each `mkc` and `npm` command would, and fails the
  test on any other command, so a new command needs a new case there.
- `TaskSpy` records the tasks that really ran, since a cache hit doesn't call a task's
  function. What each change should rerun is the `CHANGES` table in `test_rebuilds.py`.

Notes on the e2e tests:
- Run pytest from the repo root: tests use repo-relative paths, and shell out to the
  installed `mkcd2app` executable rather than importing it.
- Builds go in temp folders, each with a copy of the game and config next to each other,
  since a config's relative paths are relative to it. A full build takes about a minute,
  so share one (module fixtures) where a test only needs to read the output.
- `--run-network` also runs the tests marked `network`, which need a public share link.
  CI doesn't pass it.
- `tests/fixtures/block_network.cjs` is a Node preload that fails any network connection
  and logs it, for testing offline builds, as Node ignores `HTTP_PROXY` by default.

## Architecture

Every unit of work is a redun `@task(namespace="mkcd2app")`. `main.py` parses the CLI
and hands a task expression to `run_redun_task()` with the SQLite DB for that command.
redun builds the DAG from how task results feed into other tasks, so data dependencies
between tasks must go through task arguments/returns, not side channels.

Build pipeline (`build_project/__init__.py`), each step a task:
`fetch_code` → `build_binary_js` (runs `mkc` in its own copy of the source) +
`copy_support_files` (simulator HTML from the target dir, icon) +
`copy_website_template` → `fill_website_template`, plus `install_website_deps`
(`npm ci` from only the template's `package.json` and lockfile) → one `build_website*`
task per entry in `outputs`. A new output type means a new `case` arm in that `match`
plus a field on `BuildProjectResult`; until then `electron` and `tauri` raise
`NotImplementedError`.

Relative paths in a config are relative to the config file. `main.py` makes them
absolute with `resolve_config_paths` before any task runs.

Conventions that matter for redun hashing:
- `build_project` takes the whole config as JSON (`model_dump_json`) and passes each
  task only what it uses, as strings (models dumped to JSON). Every argument is part of
  a task's cache key, so an unused one causes needless reruns. Never pass pydantic
  models as task arguments.
- Each stage writes to a fresh directory (named via `_website_dir` in `website.py`) and
  returns a `ContentDir`/`ContentFile`; never modify a path another task returned.
- `mkcd2app/__init__.py` imports `_redun_compat` first, which monkey-patches redun and
  asserts the pinned version. Changing the redun version means re-checking those patches.

Paths under the user data/state dirs (toolchain, `js_tools/node_modules/.bin` for `mkc`,
npm cache, per-version target dirs, redun DBs) all come from `utils/paths.py`; use those
helpers instead of building paths by hand. Bundled templates and fixtures under
`resources/` are reached through `utils/resources.py`.

## Claude Code specific instructions

When you create a GitHub issue, also add the `found by claude` label (it already exists).

## ChatGPT Codex specific instructions

When you create a GitHub issue, also add the `found by chatgpt` label (it already exists).
