import logging
from pathlib import Path

import redun
from redun import Scheduler
from redun.backends.db import RedunBackendDb
from redun.expression import Expression, Result

from mkcd2app.utils.logger import create_logger

logger = create_logger(name=__name__, level=logging.INFO)


def run_redun_task(expr: Expression[Result] | Result, redun_db_path: Path) -> Result:
    redun_db_path.parent.mkdir(parents=True, exist_ok=True)
    db_uri = f"sqlite:///{redun_db_path.resolve()}"
    logger.debug(f"redun cache DB: {db_uri}")
    # noinspection PyUnresolvedReferences
    redun_config = redun.config.Config(
        {
            "scheduler": {"log_level": "DEBUG"},
            "backend": {"db_uri": db_uri},
        }
    )
    scheduler = Scheduler(config=redun_config)
    scheduler.load()
    try:
        return scheduler.run(expr)
    finally:
        # Close the SQLite connections, so a process that runs several commands
        #  (like the tests) doesn't leak one per run
        backend = scheduler.backend
        if isinstance(backend, RedunBackendDb):
            if backend.session is not None:
                backend.session.close()
            if backend.engine is not None:
                backend.engine.dispose()
