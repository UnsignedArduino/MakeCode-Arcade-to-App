import logging
import sys
from collections.abc import Iterator

import pytest

from mkcd2app.utils.logger import create_logger, set_all_stdout_logger_levels


@pytest.fixture
def logger_name(request: pytest.FixtureRequest) -> Iterator[str]:
    """A logger name unique to the test, removed afterwards (loggers are global)."""
    name = f"test-logger-{request.node.name}"
    yield name
    logging.Logger.manager.loggerDict.pop(name, None)


def test_create_logger_setup(logger_name: str) -> None:
    logger = create_logger(logger_name, logging.INFO)
    assert logger.name == logger_name
    assert logger.level == logging.INFO
    assert logger.propagate is False
    assert len(logger.handlers) == 2


def test_info_goes_to_stdout_and_warning_to_stderr(
    logger_name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    logger = create_logger(logger_name, logging.INFO)
    logger.info("some info")
    logger.warning("some warning")
    logger.debug("some debug")
    captured = capsys.readouterr()
    assert "some info" in captured.out and "some warning" not in captured.out
    assert "some warning" in captured.err and "some info" not in captured.err
    assert "some debug" not in captured.out + captured.err


def test_creating_a_logger_twice_does_not_log_twice(
    logger_name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    # Regression: the check for an existing handler compared against new objects
    create_logger(logger_name, logging.INFO)
    logger = create_logger(logger_name, logging.INFO)
    assert len(logger.handlers) == 2
    logger.info("some info")
    logger.warning("some warning")
    captured = capsys.readouterr()
    assert captured.out.count("some info") == 1
    assert captured.err.count("some warning") == 1


def test_creating_a_logger_again_uses_the_new_level(
    logger_name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    create_logger(logger_name, logging.INFO)
    logger = create_logger(logger_name, logging.DEBUG)
    logger.debug("some debug")
    assert "some debug" in capsys.readouterr().out


def test_set_all_stdout_logger_levels(
    logger_name: str, restore_log_levels: None, capsys: pytest.CaptureFixture[str]
) -> None:
    logger = create_logger(logger_name, logging.INFO)
    stdout_handler, stderr_handler = logger.handlers
    assert isinstance(stdout_handler, logging.StreamHandler)
    assert stdout_handler.stream == sys.stdout

    set_all_stdout_logger_levels(logging.DEBUG)

    assert logger.level == logging.DEBUG
    assert stdout_handler.level == logging.DEBUG
    assert stderr_handler.level == logging.WARNING  # only stdout handlers change
    logger.debug("some debug")
    assert "some debug" in capsys.readouterr().out


def test_set_all_stdout_logger_levels_covers_our_module_loggers(
    logger_name: str, restore_log_levels: None
) -> None:
    other = create_logger(f"{logger_name}-other", logging.INFO)
    try:
        set_all_stdout_logger_levels(logging.DEBUG)
        assert logging.getLogger("mkcd2app.utils.logger").level == logging.DEBUG
        assert other.level == logging.DEBUG
    finally:
        logging.Logger.manager.loggerDict.pop(other.name, None)
