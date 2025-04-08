import logging
import sys


def create_logger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """
    A simple function to create a logger. You would typically put this right
    under all the other modules you imported. And then call `logger.debug()`,
    `logger.info()`, `logger.warning()`, `logger.error()`,
    `logger.critical()`, and `logger.exception` everywhere in that module.

    :param name: A string with the logger name.
    :param level: An integer with the logger level. Defaults to logging.DEBUG.
    :return: A logging.Logger which you can use as a regular logger.
    """
    logger = logging.getLogger(name=name)
    logger.setLevel(level=level)
    logger.propagate = False

    console_formatter = logging.Formatter("%(asctime)s - %(name)s - "
                                          "%(levelname)s - %(message)s")

    # https://stackoverflow.com/a/16066513/10291933
    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    stdout_handler.setLevel(level=level)
    # stdout_handler.addFilter(lambda record: record.levelno <= logging.INFO)
    stdout_handler.setFormatter(fmt=console_formatter)
    if stdout_handler not in logger.handlers:
        logger.addHandler(hdlr=stdout_handler)

    stderr_handler = logging.StreamHandler(stream=sys.stderr)
    stderr_handler.setLevel(level=logging.WARNING)
    stderr_handler.setFormatter(fmt=console_formatter)
    if stderr_handler not in logger.handlers:
        logger.addHandler(hdlr=stderr_handler)

    logger.debug(f"Created logger named {repr(name)} with level {repr(level)}")
    logger.debug(f"Handlers for {repr(name)}: {repr(logger.handlers)}")
    return logger


logger = create_logger(name=__name__, level=logging.INFO)


def set_all_stdout_logger_levels(level: int):
    """
    Sets the logging level of all loggers that point to standard output.

    :param level: An integer with the new logger level.
    """
    logger.debug(f"Configuring all stdout handlers to {level}")
    loggers = [logging.getLogger(name) for name in
               logging.root.manager.loggerDict]
    for l in loggers:
        l.setLevel(level)
    for nm, lgr in logging.Logger.manager.loggerDict.items():
        if not isinstance(lgr, logging.PlaceHolder):
            for h in lgr.handlers:
                if "<stdout>" in repr(h):
                    h.setLevel(level)
