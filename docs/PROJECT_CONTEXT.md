# MakeCode-Arcade-to-App Rewrite — Project Context
 
_Verified against `toolchain` @ `d7ad64a` plus the `MKCD2APP_HOME` change, the
small known-issue fixes, and the separate deps-install task, and `origin/main` @ `d31e2a5`, as of 2026-10-29.
External program requirements audited against `toolchain` @ `4d518d9` on 2026-11-03, then
updated for the Dulwich git replacement and the generic `git` code source the same day,
and for the `file` code source (PNG/UF2 with embedded project, then ZIPs) the same day.
Test suite section updated for the unit test expansion on 2026-11-03._
 
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
| `utils/` | `run_cmd`, paths (platformdirs), `run_redun_task`, `rmtree_robust`, semver, `git` (Dulwich clone/checkout) |
| `resources/` | Vite+React+TS template, `mkc` js_tools, empty fixture project |
 
Other: `tests/e2e/test_statics.py`, `tests/unit/` (config code sources, `utils/git`, PNG/UF2/ZIP file source, code/website tasks, redun patches, utils), `tests/fixtures/`, `examples/` (Racers), CI
workflows `lint.yaml` (ubuntu), `unit.yaml` and `e2e.yaml` (both ubuntu/windows/macos). Tooling: uv,
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
  `install_website_deps` runs it once in `x-website-deps`, hashing only the template's
  `package.json`/lockfile, so game and asset changes don't bust it. Each
  `build_website*` task copies that `node_modules` into its own copy of the filled site
  and runs only `npm run build*`.
- **redun patches** (`_redun_compat.py`): `get_proto` (Windows drive letters),
  `ContentDir._calc_hash` and `Dir._calc_hash` (hash file contents, not mtimes).
  Covered by `tests/unit/test_redun_compat.py`.
## External programs
`run_cmd` only ever runs `npm` and `mkc`:
- **Node.js ≥ 22.12 + npm, on PATH. Always required.** The floor comes from
  `@rolldown/plugin-babel` (`>=22.12.0`); vite 8 / rolldown accept `^20.19 || >=22.12`,
  `makecode` only needs ≥14. `mkc` is a Node script, so `node` must be on PATH too.
  Nothing declares or checks this yet. Distro Node packages (e.g. Ubuntu apt) are too old.
- **Not git:** `git` (and `github`) code sources are cloned with Dulwich (pure Python,
  `utils/git.py`). The default branch and branches/tags get `depth=1` (+ `branch=`);
  anything else is taken as a (short) SHA and gets a full clone + `porcelain.checkout`. That clone checks out the
  default branch first, because Dulwich's checkout only writes files that differ from
  the current HEAD tree and leaves an empty worktree when the target's tree matches HEAD.
- **Not needed:** system Python (uv downloads 3.14), a C compiler (all Python deps have
  wheels except `redun`, which is a pure-Python sdist), npm native build tools
  (rolldown/lightningcss ship prebuilt optional binaries; `fsevents` is macOS-only).
- The offline npm cache holds platform-specific binaries, so it only works on the OS/arch
  that ran `toolchain install`.
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
 
Config: `version`, `project`, `inputs.code` (share_link | git | github | path | file),
`inputs.assets.icon` (optional), `build_dir`, `target` (required, strict `x.y.z`),
`outputs` (static | static-singlefile | electron | tauri). `git` takes `url` (pydantic
`AnyUrl`: https/http/git/file, or ssh:// which needs an `ssh` binary) and an optional
`ref` (branch, tag, or SHA; omitted = the remote's default branch). `github` is the older
alias, `{value: <http url>, checkout: <ref, default "master">}`, kept for existing
configs; `fetch_code` handles both in one `case`.
 
## Status
- **Done:** `static` and `static-singlefile` outputs; all code sources, including
  `file` (a PNG or UF2 downloaded from the editor, or a ZIP of the project such as
  GitHub's "Download ZIP", detected by magic bytes; decoded by
  `build_project/inputs/embedded_source.py`, and `fetch_code` warns if `pxt.json`'s
  `targetVersions.target` differs from `target`). A ZIP's root is wherever `pxt.json`
  is: at the top level or inside one wrapping folder (`<repo>-<branch>/`), which is
  stripped. Everything under it is extracted, binary files included. Symlinks are
  skipped, and there are entry-count and 512 MB uncompressed limits. It's the way to
  build a private repo until the `git` source handles credentials; toolchain/target split. Everything that needs the network is vendored at install time **except MakeCode
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
- **CI** (`lint.yaml`, `unit.yaml`, `e2e.yaml`) runs on pushes to `main` and on PRs
  into any branch, so the stacked PRs get CI. Lint and all three e2e jobs are green on
  PR #7. `unit.yaml` runs `pytest -m unit` (no Node.js), and `e2e.yaml` runs
  `pytest -m e2e --no-cov`; neither waits for the other.
- `tests/unit` covers config parsing of the `git`/`github` sources and
  `clone_and_checkout` against a local repo built with Dulwich (default branch, branch,
  tag, short/full SHA, the same-tree-as-HEAD regression, unknown ref), so it runs
  offline. Fixture commits pass `sign=False`, since Dulwich honours a user's
  `commit.gpgsign`. `test_embedded_source.py` covers the `file` source with synthetic
  PNG (including overflow rows) and UF2 (LZMA and plain) round trips, error cases and
  path traversal, plus real editor exports in `tests/fixtures/embedded/`: the
  "falling duck" PNG (512×424) and UF2, both saved from 4.1.27 and identical once
  decoded, and `empty-game.png` from 4.0.14, which matches `tests/fixtures/empty_game`
  except for the `pxt.json` name, and `Racers-master.zip` (GitHub "Download ZIP" of
  Racers, saved with 2.0.48; it builds on 4.0.14 with the mismatch warning but pulls
  GitHub extensions, so it isn't in e2e). ZIP cases also cover the wrapper folder,
  no or ambiguous `pxt.json`, symlinks, traversal, the size limit and truncation. The e2e suite also builds `empty-game.png` through
  `empty_game_file_source.yaml`, and a ZIP of `tests/fixtures/empty_game` made at test
  time with a GitHub-style `empty_game-master/` wrapper (checked byte for byte
  against the checkout, so CRLF on Windows is fine). The duck builds end to end on 4.1.27, and on 4.0.14
  with the version-mismatch warning, but isn't in e2e.
- `test_code.py` and `test_website.py` run every code-input and website task through
  `.func` with `run_cmd` (and `clone_and_checkout`, `requests.get`,
  `get_sim_html_path`) monkeypatched, against a copy of the real bundled template.
  `test_redun_compat.py` checks the `get_proto` patch and that directory hashes
  ignore mtimes but change with content, file adds/removes/renames, and path.
  `utils/` (`paths`, `run`, `filesystem`, `resources`) and `extract_meta_comment` have
  their own small tests. Untested: `cli.py`, `main.py`, the `build_project` DAG
  wiring, toolchain/target install tasks, and `is_strict_semver`.
- pytest config is in `pyproject.toml`: coverage on by default (`--no-cov` to skip),
  `--strict-markers`, and `unit`/`e2e` markers applied by `tests/conftest.py`. Unit
  tests cover about 66% of `src/mkcd2app` (run `uv run pytest -m unit`).
## Roadmap
1. ~~Fix e2e + CI~~ (done: fixture `target:`, isolated install fixture, caching on,
   job-status cache assertion, CI on all PRs).
2. ~~Rename `--clear-cache`~~ (done: now `--full-rebuild`, and its help text says to use
   it for out-of-band input changes). Still belongs in the README once that exists.
3. More unit/integration tests: `cli.py`/`main.py`, `build_project` wiring with
   `run_cmd` stubbed, and the toolchain/target install tasks (redun patches, code and
   website tasks, and utils are covered).
4. Electron, then Tauri (reference: `main`).
5. Save-state for Electron/Tauri (investigate `pxtsim` postMessage).
6. Toolchain polish: `status`/`list`, `build` pre-flight, extension cache, version-pinning
   UX, and cutting external dependencies so that "only uv installed" works for static and
   Electron outputs:
   - **Node: managed by default, system as an opt-in.** `toolchain install` downloads the
     official archive (`nodejs.org/dist/v<ver>/node-v<ver>-<os>-<arch>.{zip|tar.xz}`),
     verifies it against `SHASUMS256.txt`, and extracts it to `<data dir>/node/<ver>/`
     (`.zip` on Windows with binaries at the root; `.tar.xz` on macOS/Linux with
     binaries in `bin/`, keeping symlinks and exec bits; musl needs the unofficial
     builds). It's a redun task keyed on the version and removed by `toolchain uninstall`.
     Nothing is added to the user's PATH.
     - Fallback idea: depend on the `nodejs-wheel` PyPI package (official binaries as
       wheels) instead of writing download code, at the cost of not choosing the Node
       version.
   - **Opting into a global Node/Rust:** a per-tool source of `managed | system | <path>`,
     set with `toolchain install --node=… --rust=…` (persisted in the toolchain state so
     `build` uses the same choice), overridable by `MKCD2APP_NODE` / `MKCD2APP_RUST` env
     vars (useful in CI, e.g. after `actions/setup-node`). `system` resolves from the
     user's PATH; `<path>` points at a specific install dir. In both, mkcd2app checks the
     version (Node ≥ 22.12; Rust per Tauri's MSRV) and fails with a clear message instead
     of downloading. `toolchain status` reports which source and version are active.
   - **`run_cmd` gets an `env=`**, built by one helper that prepends the selected
     Node/cargo bin dirs to the child's `PATH` (npm and the `mkc` shim run `node` from
     PATH, so `which_path` alone isn't enough) and redirects caches into mkcd2app dirs:
     `npm_config_cache`, and later `ELECTRON_CACHE` / `electron_config_cache` and, for a
     managed Rust, `RUSTUP_HOME` / `CARGO_HOME`.
   - **Rust: system by default, managed as an opt-in.** Tauri also needs OS packages that
     need an admin install (MSVC Build Tools + WebView2 on Windows, Xcode CLT on macOS,
     `webkit2gtk-4.1`/`libssl-dev` etc. on Linux), so a private rustup alone doesn't give
     "only uv". `--rust=managed` bootstraps rustup into mkcd2app's own
     `RUSTUP_HOME`/`CARGO_HOME`. Pre-flight checks list the missing OS packages with the
     install command for that OS. Tauri only builds for the host OS.
   - **Electron:** `toolchain install` pre-fetches the Electron (and electron-builder
     helper) binaries into a redirected cache so the offline `npm ci` still works.
     Cross-building, e.g. Windows targets from macOS/Linux, needs Wine; out of scope.
   - ~~**Drop the `git` binary**~~ (done: Dulwich clone + checkout, `depth=1` +
     `branch=` for branches/tags, full clone for SHAs; see External programs).
     ~~Generalise the source to `git: {url, ref}`~~ (done, `github` kept as an alias).
     Still to do: private repos need credentials handled by us (no system credential
     helper); a token embedded in the URL would work but gets logged and written to
     the clone's `.git/config`.
     pygit2 (libgit2 bundled in its wheels) is the compiled alternative.
   - **Distribution:** publish to PyPI so `uvx mkcd2app` / `uv tool install mkcd2app` is
     the install story. A PyInstaller build (one per OS/arch; `--collect-data mkcd2app`;
     check that redun works when frozen; unsigned builds hit Gatekeeper/SmartScreen) is
     optional and doesn't remove the Tauri OS prerequisites.
   - **Declare the Node floor:** add `"engines": {"node": ">=22.12"}` to the template's
     `package.json` and check it in pre-flight.
7. Later: code signing, auto-update, README (currently a stub), schema docs.
## Known issues
- **Out-of-band inputs (by design):** `fetch_code` and
  `copy_support_files` only take the config YAML, so redun can't see changes to a
  `path` or `file` code source, a `git`/`github` branch checkout (or omitted `ref`), an icon path/URL, or the installed
  simulator HTML. Editing a path-sourced game returns the old cached build until
  `--full-rebuild`. Decided to rely on that flag for all sources rather than track
  each one.
- Fixed: the website dep install used to hash the whole filled site, so any asset
  change re-ran `npm ci`; it's now its own task (see Architecture).
- Fixed: `download_sim` now decodes downloads as UTF-8 instead of `res.text`, and all
  text file reads/writes in `src/` pass `encoding="utf-8"`. (The 4.0.14 simulator was
  pure ASCII, so this hadn't caused damage yet.) Also fixed: the `uninstall_toolchain`
  docstring, `get_resource_template_path(name)` ignoring `name`,
  `load_config_from_yaml` raising `AttributeError` on an unknown version, the stale
  `fill_website_template` docstring, and the stray comment in `Racers offline.yaml`.
 
