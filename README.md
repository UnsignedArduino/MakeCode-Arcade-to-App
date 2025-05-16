# MakeCode Arcade to App

Convert your MakeCode Arcade games into a standalone offline executable!

## Install

### Dependencies

* Python (tested with version 3.12)
* Node (tested with version v20)
* Rust if building with Tauri (tested with compiler version 1.87)

### Steps

1. Clone repo.
2. Create virtual environment and install Python dependencies in [
   `requirements.txt`](requirements.txt) into it.
3. Install JavaScript dependencies with `yarn`.

## Usage

Quick start:

1. Create a yaml configuration file. See
   [`Racers to Electron.yaml`](examples/Racers%20to%20Electron.yaml) for an
   example.
2. Run the script with `python main.py "examples/Racers to Electron.yaml"`.

### Input

A yaml configuration file is used. Check out the examples in the
[`examples`](examples) directory to see how it's used, as it's
self-explanatory. Pass it as the first positional argument to the script.

### Output

The script will print the path to the output directory, which changes depending
on the output specified.

#### Static files

If the output is set to `static`, you will get HTML, CSS, and JS files that you
can serve from a web server. (maybe on your own website?) The script will print
out something like this:

```commandline
...
dist/assets/index-D3F42Pqm.js   225.78 kB │ gzip: 70.51 kB
✓ built in 532ms
Done in 1.60s.
2025-05-15 20:28:48,660 - __main__ - INFO - Static website files are at C:\Users\ckyiu\Documents\Projects\MakeCode-Arcade-to-App\examples\Racers\racers-website\dist
2025-05-15 20:28:48,660 - __main__ - INFO - Build finished
```

You will find the HTML, CSS, and JS files at the specified path, where
`index.html` is the entry point.

#### Executable with Electron

If the output is set to `electron`, you will get an executable using the
Electron framework. The script will print out something like this:

```commandline
...
› Artifacts available at: C:\Users\ckyiu\Documents\Projects\MakeCode-Arcade-to-App\examples\Racers\racers-electron\out\make
√ Running postMake hook
Done in 50.25s.
2025-05-15 20:32:22,652 - __main__ - INFO - Electron app executables are at C:\Users\ckyiu\Documents\Projects\MakeCode-Arcade-to-App\examples\Racers\racers-electron\out
2025-05-15 20:32:22,652 - __main__ - INFO - Build finished
```

You will find the directory with the executable and supporting files at the
specified path. (all of those files alongside the executable are needed, so
it's recommended to zip up the entire directory to distribute) You will also
find an installer in the `make` subdirectory.

#### Executable with Tauri (recommended option)

> This is the recommended option due to the small size and standalone nature of
> the executable. (~10 mb single executable with Tauri compared to almost 300 mb
> in files with Electron)

If the output is set to `tauri`, you will get an executable using the Tauri
framework. The script will print out something like this:

```commandline
...
        C:\Users\ckyiu\Documents\Projects\MakeCode-Arcade-to-App\examples\Racers\racers-tauri\src-tauri\target\release\bundle\nsis\Racers v1.3.2_1.3.2_x64-setup.exe

Done in 37.90s.
2025-05-15 23:39:14,612 - __main__ - INFO - Tauri app executables are at C:\Users\ckyiu\Documents\Projects\MakeCode-Arcade-to-App\examples\Racers\racers-tauri\src-tauri\target\release
2025-05-15 23:39:14,612 - __main__ - INFO - Build finished
```

You will find the executable at the specified path. (only the executable is
needed, no supporting files necessary) You will also find installers in the
`bundle` subdirectory. 
