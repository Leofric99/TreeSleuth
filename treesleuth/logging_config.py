import logging
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from treesleuth.app_data import application_data_directory

_LOGGER_NAME = "treesleuth"
_LOG_FILENAME = "treesleuth.log"
_MAX_LOG_BYTES = 10 * 1024 * 1024
_BACKUP_COUNT = 5
_CONFIGURATION_LOCK = threading.Lock()


def configure_logging(log_directory: Path | None = None) -> Path:
    directory = log_directory or application_data_directory("logs")
    directory.mkdir(parents=True, exist_ok=True)
    log_path = (directory / _LOG_FILENAME).resolve()

    with _CONFIGURATION_LOCK:
        logger = logging.getLogger(_LOGGER_NAME)
        file_handler = next(
            (
                handler
                for handler in logger.handlers
                if getattr(handler, "_treesleuth_file_handler", False)
            ),
            None,
        )
        if file_handler is not None and Path(file_handler.baseFilename) == log_path:
            return log_path
        if file_handler is not None:
            logger.removeHandler(file_handler)
            file_handler.close()

        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=_MAX_LOG_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler._treesleuth_file_handler = True
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s"
            )
        )
        logger.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)

    return log_path
