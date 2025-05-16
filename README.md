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

1. Create a yaml configuration file. See 
   [`Racers to Electron.yaml`](examples/Racers%20to%20Electron.yaml) for an 
   example.
2. Run the script with `python main.py "examples/Racers to Electron.yaml"`.
