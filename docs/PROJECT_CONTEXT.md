# MakeCode-Arcade-to-App Rewrite — Project Context

_Verified against `toolchain` @ `d7ad64a` plus the `MKCD2APP_HOME` change and the
small known-issue fixes, and `origin/main` @ `d31e2a5`, as of 2026-10-29._

## Goal
Rewrite `UnsignedArduino/MakeCode-Arcade-to-App` (converts MakeCode Arcade games into a
static website, Electron app, or Tauri app). The original was basically a bash script
written in Python. The rewrite turns it into an incremental build system that runs in CI
and copes with churn in the JS ecosystem.

## Branches / PRs
```
main (legacy)  ←  PR #6 `dag` (draft)  ←  PR #7 `toolchain` (draft, base = dag)
```
- The work is on `toolchain`: 53 commits ahead of `main`, 13 ahead of `dag` (`b9c2ab2`)
  as of `d7ad64a`.
- `main` has 2 legacy-only fixes (`d17b052`, `d31e2a5`) to files the rewrite deleted.
  Merging gives 2 modify/delete conflicts; resolve them by keeping the deletions.
- The legacy Electron/Tauri code to use as reference is on **`main`**
  (`src/convert/website_to_{electron,tauri}/`, `src/templates/{electron,tauri}_files/`).
  The `electron-output`/`tauri-output` branches are merged and out of date. The legacy
  code can't be ported as is; it has to be reimplemented on the new pipeline.

## Layout (`src/mkcd2app/`)
| Path | Purpose |
|---|---|
| `__init__.py` | Applies redun patches, asserts redun version |
| `main.py`, `cli.py` | argparse CLI → redun tasks |
| `_redun_compat.py` | redun monkey-patches |
| `config/`, `models/` | YAML loader; pydantic `BuildConfig`, `BinaryJSMetadata` |
| `build_project/` | `build_project` task, website tasks, code inputs |
| `toolchain/`, `target/` | install/uninstall tasks |
| `utils/` | `run_cmd`, paths (platformdirs), `run_redun_task`, `rmtree_robust`, semver |
| `resources/` | Vite+React+TS template, `mkc` js_tools, empty fixture project |

Other: `tests/e2e/test_statics.py`, `tests/fixtures/`, `examples/` (Racers), CI
workflows `lint.yaml` (ubuntu) and `e2e.yaml` (ubuntu/windows/macos). Tooling: uv,
hatchling, Python ≥3.14, ruff + mypy strict, pre-commit.

## Architecture
- **redun `0.44.1`** (pinned) is the DAG engine, embedded via
  `utils/run_redun_task.py`. Each command keeps its own SQLite DB (toolchain, target,
  or `build_dir/.redun-cache.db`).
- **Caching is enabled:** an unchanged rebuild is served entirely from the redun cache.
  Inputs outside the config aren't tracked, so picking up their changes needs
  `--full-rebuild` (see "Out-of-band inputs" under Known issues).
- **Config is passed to tasks as raw YAML text**, because pickling pydantic objects
  isn't deterministic and that breaks redun's hashing.
- **Copy-on-write stages:** a path is never written after it's been returned as a
  `ContentDir`/`ContentFile` (`x-website` → `-filled` → `-filled-built`).
- **Website builds are offline:** `npm ci --cache <toolchain cache> --offline`.
- **redun patches** (`_redun_compat.py`): `get_proto` (Windows drive letters),
  `ContentDir._calc_hash` and `Dir._calc_hash` (hash file contents, not mtimes). No
  tests cover them yet.

## CLI
Global `--debug` (goes before the subcommand). Commands must run in this order:
```
mkcd2app toolchain install           # mkc CLI + warm template npm cache
mkcd2app target install <x.y.z>      # warm mkc compiler cache + download/inline simulator HTML
mkcd2app build <config.yaml> [--full-rebuild]
```
Also `toolchain uninstall` and `target uninstall <ver>`. `toolchain status` and
`target list` are **stubs**. `build` has **no pre-flight checks**: a missing target
fails with a raw `FileNotFoundError`, a missing toolchain with "Executable 'mkc' not found".

State lives under `platformdirs` user dirs, namespaced by mkcd2app version (static
`0.1.0`). A version bump means re-running both installs. Setting `MKCD2APP_HOME`
moves them to `$MKCD2APP_HOME/{data,state}/<version>` (`utils/paths.py`). `mkc`'s own
compiler/extension caches aren't covered by this.

Config: `version`, `project`, `inputs.code` (share_link | github | path),
`inputs.assets.icon` (optional), `build_dir`, `target` (required, strict `x.y.z`),
`outputs` (static | static-singlefile | electron | tauri).

## Status
- **Done:** `static` and `static-singlefile` outputs; all code sources; toolchain/target
  split. Everything that needs the network is vendored at install time **except MakeCode
  extensions**, which are fetched per game; `mkc`'s extension cache isn't redirected.
- **Not implemented:** Electron and Tauri. The models and result fields exist, but
  `build_project` has no `case` arms for them.
- **E2E test passes** locally (Windows, ~1 min with installs cached) and in CI on
  ubuntu/windows/macos (PR #7 @ `d7ad64a`). A session fixture sets `MKCD2APP_HOME` to
  `.pytest_cache/d/mkcd2app-home` and runs `toolchain install` and
  `target install 4.0.14` there, so the real user dirs are untouched and reruns hit
  the install cache. The cache test parses the `ALL` row of the job status table redun
  logs to stderr and requires `DONE == 0` and `CACHED == TOTAL` on an unchanged
  rebuild; this depends on redun's log format, which is safe while redun is pinned.
  Nothing yet tests that changing an input does trigger a rebuild.
- **CI** (`lint.yaml`, `e2e.yaml`) runs on pushes to `main` and on PRs into any branch,
  so the stacked PRs get CI. Lint and all three e2e jobs are green on PR #7.
- Only `tests/e2e` exists; there are no unit or integration tests yet.

## Roadmap
1. ~~Fix e2e + CI~~ (done: fixture `target:`, isolated install fixture, caching on,
   job-status cache assertion, CI on all PRs).
2. ~~Rename `--clear-cache`~~ (done: now `--full-rebuild`, and its help text says to use
   it for out-of-band input changes). Still belongs in the README once that exists.
3. Unit/integration tests, including the redun patches.
4. Electron, then Tauri (reference: `main`).
5. Save-state for Electron/Tauri (investigate `pxtsim` postMessage).
6. Toolchain polish: `status`/`list`, `build` pre-flight, extension cache, version-pinning UX.
7. Later: code signing, auto-update, README (currently a stub), schema docs.

## Known issues
- **Out-of-band inputs (by design):** `fetch_code` and
  `copy_support_files` only take the config YAML, so redun can't see changes to a
  `path` code source, a `github` branch checkout, an icon path/URL, or the installed
  simulator HTML. Editing a path-sourced game returns the old cached build until
  `--full-rebuild`. Decided to rely on that flag for all sources rather than track
  each one.
- `install_deps_and_build_website*` hash the whole filled site, not just
  `package.json`/lockfile, so changing an asset busts the dep cache.
- Fixed: `download_sim` now decodes downloads as UTF-8 instead of `res.text`, and all
  text file reads/writes in `src/` pass `encoding="utf-8"`. (The 4.0.14 simulator was
  pure ASCII, so this hadn't caused damage yet.) Also fixed: the `uninstall_toolchain`
  docstring, `get_resource_template_path(name)` ignoring `name`,
  `load_config_from_yaml` raising `AttributeError` on an unknown version, the stale
  `fill_website_template` docstring, and the stray comment in `Racers offline.yaml`.
