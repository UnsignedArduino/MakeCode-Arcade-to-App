import logging
from pathlib import Path

import redun
from redun import Scheduler
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
    # TODO: don't forget to remove cache=False after done testing
    return scheduler.run(expr, cache=False)
