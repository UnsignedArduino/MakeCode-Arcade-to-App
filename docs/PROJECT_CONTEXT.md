# MakeCode-Arcade-to-App Rewrite — Project Context

_Verified as of 2026-11-07, against `toolchain` @ `3bf8a76`. Keep this line to
the latest check, and note any test tier that wasn't run or any OS it wasn't
run on._

Commands, test conventions and the build pipeline are in `AGENTS.md`. This doc
holds what the code can't tell you: status, decisions, plans and open problems.
Fixed bugs don't belong here; their reasoning goes in code comments and
regression tests.

## Goal

Rewrite `UnsignedArduino/MakeCode-Arcade-to-App` (converts MakeCode Arcade
games into a static website, Electron app, or Tauri app). The original was
basically a bash script zwritten in Python. The rewrite turns it into an
incremental build system that runs in CI and copes with churn in the JS
ecosystem.

## Branches / PRs

```
main (legacy)  ←  PR #6 `dag` (draft)  ←  PR #7 `toolchain` (draft, base = dag)
```

- The work is on `toolchain`.
- `main` has 2 legacy-only fixes (`d17b052`, `d31e2a5`) to files the rewrite
  deleted. Merging gives 2 modify/delete conflicts; resolve them by keeping the
  deletions.
- The legacy Electron/Tauri code to use as reference is on **`main`**
  (`src/convert/website_to_{electron,tauri}/`,
  `src/templates/{electron,tauri}_files/`). The `electron-output`/
  `tauri-output` branches are merged and out of date. The legacy code can't be
  ported as is; it has to be reimplemented on the new pipeline.

## Status

- **Done:** `static` and `static-singlefile` outputs; all code sources
  (`share_link`,
  `git`, `github`, `path`, and `file` for a PNG, UF2 or ZIP); the
  toolchain/target split.
- **Not implemented:** Electron and Tauri. Their `case` arm in `build_project`
  raises
  `NotImplementedError` before anything runs.
- **Stubs:** `toolchain status` and `target list`.

## Layout

In `src/mkcd2app/`:

| Path                    | Purpose                                                  |
|-------------------------|----------------------------------------------------------|
| `main.py`, `cli.py`     | argparse CLI → redun tasks                               |
| `_redun_compat.py`      | redun monkey-patches                                     |
| `config/`, `models/`    | YAML loader; pydantic config and metadata models         |
| `build_project/`        | `build_project` task, website tasks, `inputs/` (sources) |
| `toolchain/`, `target/` | install/uninstall tasks                                  |
| `utils/`                | `run_cmd`, paths, `run_redun_task`, Dulwich `git`, etc.  |
| `resources/`            | Vite template, `mkc` js_tools, empty project             |

Tests are in `tests/{unit,integration,e2e}`, and an example config is in
`examples/`.

## Commands

Run the installs first, in this order:

```bash
uv sync
uv run mkcd2app toolchain install
uv run mkcd2app target install 4.0.14
uv run mkcd2app --debug build "examples/Racers.yaml"    # add --full-rebuild to start over
uv run mkcd2app target uninstall 4.0.14
uv run mkcd2app toolchain uninstall
```

Checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m e2e --no-cov
```

## Decisions

- **Caching:** redun's cache is on, and each command has its own SQLite DB
  (toolchain, target, or `build_dir/.redun-cache.db`). What each kind of edit
  should rerun is the
  `CHANGES` table in `tests/integration/test_rebuilds.py`.
- **Out-of-band inputs aren't tracked:** redun can't see changes to a `path` or
  `file`
  code source, a `git`/`github` branch checkout (or omitted `ref`), an icon
  path/URL, or the installed simulator HTML. Editing a path-sourced game
  returns the old cached build until `--full-rebuild`. We decided to rely on
  that flag for all sources rather than track each one.
- **Website builds are offline:** `npm ci --cache <toolchain cache> --offline`.
  Everything that needs the network is vendored at install time **except
  MakeCode extensions**, which are fetched per game. The npm cache holds
  platform-specific binaries, so it only works on the OS/arch that ran
  `toolchain install`.
- **Uninstalls are never cached:** they return `None`, so a cached result
  couldn't notice a reinstall. Install tasks return `ContentDir`/`ContentFile`,
  which redun re-validates, so they stay cached.
- **State dirs** are namespaced by mkcd2app version (static `0.1.0`), so a
  version bump means re-running both installs. `MKCD2APP_HOME` moves them, but
  not `mkc`'s own compiler/extension caches.
- **`github` source** is an older alias of `git`, kept for existing configs.

## External programs

`run_cmd` only ever runs `npm` and `mkc`.

- **Node.js ≥ 22.12 + npm, on PATH, always required.** The floor comes from
  `@rolldown/plugin-babel`; vite 8 / rolldown accept `^20.19 || >=22.12`, and
  `makecode`
  only needs ≥14. `mkc` is a Node script, so `node` must be on PATH too.
  Nothing declares or checks this yet. Distro Node packages (e.g. Ubuntu apt)
  are too old.
- **Not needed:** git (Dulwich handles clones; an `ssh://` URL needs an `ssh`
  binary), system Python (uv downloads 3.14), a C compiler (all Python deps
  have wheels except
  `redun`, a pure-Python sdist), npm native build tools (rolldown/lightningcss
  ship prebuilt binaries).

## Roadmap

1. Electron, then Tauri (reference: `main`).
2. Save-state for Electron/Tauri (investigate `pxtsim` postMessage).
3. Toolchain polish: `status`/`list`, `build` pre-flight, extension cache,
   version-pinning UX, and cutting external dependencies so that "only uv
   installed" works for static and Electron outputs:
    - **Node: managed by default, system as an opt-in.** `toolchain install`
      downloads the official archive
      (`nodejs.org/dist/v<ver>/node-v<ver>-<os>-<arch>.{zip|tar.xz}`), verifies
      it against `SHASUMS256.txt`, and extracts it to `<data dir>/node/<ver>/`
      (`.zip` on Windows with binaries at the root; `.tar.xz` on macOS/Linux
      with binaries in `bin/`, keeping symlinks and exec bits; musl needs the
      unofficial builds). It's a redun task keyed on the version and removed by
      `toolchain uninstall`. Nothing is added to the user's PATH.
        - Fallback idea: depend on the `nodejs-wheel` PyPI package (official
          binaries as wheels) instead of writing download code, at the cost of
          not choosing the Node version.
    - **Opting into a global Node/Rust:** a per-tool source of
      `managed | system | <path>`, set with
      `toolchain install --node=… --rust=…` (persisted in the toolchain state
      so
      `build` uses the same choice), overridable by `MKCD2APP_NODE` /
      `MKCD2APP_RUST` env vars (useful in CI, e.g. after `actions/setup-node`).
      `system` resolves from the user's PATH; `<path>` points at a specific
      install dir. In both, mkcd2app checks the version (Node ≥ 22.12; Rust per
      Tauri's MSRV) and fails with a clear message instead of downloading.
      `toolchain status` reports which source and version are active.
    - **`run_cmd` gets an `env=`**, built by one helper that prepends the
      selected Node/cargo bin dirs to the child's `PATH` (npm and the `mkc`
      shim run `node` from PATH, so `which_path` alone isn't enough) and
      redirects caches into mkcd2app dirs:
      `npm_config_cache`, and later `ELECTRON_CACHE` / `electron_config_cache`
      and, for a managed Rust, `RUSTUP_HOME` / `CARGO_HOME`.
    - **Rust: system by default, managed as an opt-in.** Tauri also needs OS
      packages that need an admin install (MSVC Build Tools + WebView2 on
      Windows, Xcode CLT on macOS,
      `webkit2gtk-4.1`/`libssl-dev` etc. on Linux), so a private rustup alone
      doesn't give
      "only uv". `--rust=managed` bootstraps rustup into mkcd2app's own
      `RUSTUP_HOME`/`CARGO_HOME`. Pre-flight checks list the missing OS
      packages with the install command for that OS. Tauri only builds for the
      host OS.
    - **Electron:** `toolchain install` pre-fetches the Electron (and
      electron-builder helper) binaries into a redirected cache so the offline
      `npm ci` still works. Cross-building, e.g. Windows targets from
      macOS/Linux, needs Wine; out of scope.
    - **Private git repos:** need credentials handled by us (no system
      credential helper). A token embedded in the URL would work but gets
      logged and written to the clone's
      `.git/config`. pygit2 (libgit2 bundled in its wheels) is the compiled
      alternative. Until then, a ZIP through the `file` source is the way to
      build a private repo.
    - **Distribution:** publish to PyPI so `uvx mkcd2app` /
      `uv tool install mkcd2app` is the install story. A PyInstaller build (one
      per OS/arch; `--collect-data mkcd2app`; check that redun works when
      frozen; unsigned builds hit Gatekeeper/SmartScreen) is optional and
      doesn't remove the Tauri OS prerequisites.
    - **Declare the Node floor:** add `"engines": {"node": ">=22.12"}` to the
      template's
      `package.json` and check it in pre-flight.
4. Later: code signing, auto-update, README (currently a stub; should cover
   `--full-rebuild`), schema docs.

## Known issues

- **Little pre-flight checking in `build`:** `build_project` raises if the
  target isn't installed, naming the install command, but a missing toolchain
  only fails with
  "Executable 'mkc' not found".
- **`mkc` checks for updates once a day:** it tries `arcade.makecode.com` if
  its last check (in `~/.pxt/mkc-cache`, which isn't redirected) is over 24
  hours old. Offline, that fails, and `mkc` logs it and builds from its cache,
  so builds still work.
- **The `static` output needs a web server:** its `index.html` loads module
  scripts, which browsers don't normally allow from `file://` (not tested
  here). `static-singlefile` is the one meant to be opened directly.
- **Files inside `build_dir` aren't all protected:** a `path` source
  overlapping
  `build_dir` is a config error, but a `file` source or `path` icon inside it
  isn't checked, so a build can still delete it. A `path` source next to
  `build_dir` still copies its own `built/`, `node_modules/` and
  `pxt_modules/`.
- **`path_friendly_name`** still accepts npm's blocked names, `node_modules`
  and
  `favicon.ico`.
- **`run_cmd` limits:** a failed command's output is logged about 80 lines
  above the end of stderr, followed by redun's status table and tracebacks, and
  the final `BuildError` line doesn't point back to it. Output also isn't
  streamed, so a long `npm ci` shows no progress, and there's no timeout.
- **Test gaps:**
    - Nothing checks that a built site really runs. A Playwright smoke test (no
      page errors, simulator iframe present) was left out, as it adds a browser
      install to CI.
    - Integration tests fake `run_cmd`, so its logging is only covered by
      `tests/unit/test_run.py`.
    - The symlink integration test skips on Windows, so only CI runs it.
    - The `share_link` e2e test needs `--run-network` (about 7 minutes), so CI
      skips it.
    - `Racers-master.zip` and the falling-duck exports aren't in e2e: Racers
      pulls GitHub extensions, and the duck was saved from 4.1.27 (it builds on
      4.0.14 with the version-mismatch warning).
