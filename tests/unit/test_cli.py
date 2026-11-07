import sys

import pytest

from mkcd2app.cli import generate_and_parse_args


@pytest.mark.parametrize(
    "argv",
    [
        [],  # a subcommand is required
        ["nonsense"],
        ["build"],  # config is required
        ["toolchain"],  # these need their own subcommand
        ["toolchain", "nonsense"],
        ["target"],
        ["target", "nonsense"],
        ["target", "install"],  # version is required
        ["target", "uninstall"],
        ["build", "c.yaml", "--debug"],  # --debug must come before the subcommand
        ["target", "list", "--debug"],
        ["--full-rebuild", "build", "c.yaml"],  # --full-rebuild belongs to build
        ["target", "install", "4.0.14", "--full-rebuild"],
    ],
)
def test_invalid_arguments_exit_2(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        generate_and_parse_args(argv)
    assert exc.value.code == 2


def test_build_defaults() -> None:
    args = generate_and_parse_args(["build", "c.yaml"])
    assert (args.command, args.config) == ("build", "c.yaml")
    assert args.full_rebuild is False
    assert args.debug is False


def test_build_full_rebuild() -> None:
    assert generate_and_parse_args(["build", "c.yaml", "--full-rebuild"]).full_rebuild


def test_debug_before_subcommand() -> None:
    assert generate_and_parse_args(["--debug", "build", "c.yaml"]).debug is True


@pytest.mark.parametrize("command", ["install", "status", "uninstall"])
def test_toolchain_commands(command: str) -> None:
    args = generate_and_parse_args(["toolchain", command])
    assert (args.command, args.toolchain_command) == ("toolchain", command)


@pytest.mark.parametrize("command", ["install", "uninstall"])
def test_target_commands_take_version(command: str) -> None:
    args = generate_and_parse_args(["target", command, "4.0.14"])
    assert (args.command, args.target_command) == ("target", command)
    assert args.version == "4.0.14"


def test_target_list() -> None:
    args = generate_and_parse_args(["target", "list"])
    assert (args.command, args.target_command) == ("target", "list")


def test_version_is_not_validated_by_the_parser() -> None:
    # main.py checks it's strict semver, so that's where the error comes from
    assert generate_and_parse_args(["target", "install", "4.0"]).version == "4.0"


def test_defaults_to_sys_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["mkcd2app", "build", "from-argv.yaml"])
    assert generate_and_parse_args().config == "from-argv.yaml"
