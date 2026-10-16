import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from treesleuth.logging_config import configure_logging


def file_handlers() -> list[logging.Handler]:
    return [
        handler
        for handler in logging.getLogger("treesleuth").handlers
        if getattr(handler, "_treesleuth_file_handler", False)
    ]


def test_configure_logging_creates_appendable_debug_log(tmp_path: Path) -> None:
    log_path = configure_logging(tmp_path / "nested" / "logs")

    logging.getLogger("treesleuth.test").debug("first diagnostic")
    file_handlers()[0].flush()
    assert log_path.is_file()
    assert "DEBUG treesleuth.test" in log_path.read_text(encoding="utf-8")

    configure_logging(tmp_path / "nested" / "logs")
    logging.getLogger("treesleuth.test").error("later diagnostic")
    file_handlers()[0].flush()
    content = log_path.read_text(encoding="utf-8")
    assert "first diagnostic" in content
    assert "later diagnostic" in content
    assert len(file_handlers()) == 1


def test_configure_logging_uses_bounded_rotation(tmp_path: Path) -> None:
    log_path = configure_logging(tmp_path / "logs")

    handler = file_handlers()[0]
    assert isinstance(handler, RotatingFileHandler)
    assert handler.maxBytes == 10 * 1024 * 1024
    assert handler.backupCount == 5
    assert handler.encoding == "utf-8"
    assert log_path.name == "treesleuth.log"


def test_configure_logging_rotates_existing_log(tmp_path: Path) -> None:
    log_path = configure_logging(tmp_path / "logs")
    handler = file_handlers()[0]
    handler.maxBytes = 1

    logger = logging.getLogger("treesleuth.test")
    logger.warning("first record")
    logger.warning("second record")
    handler.flush()

    assert (log_path.parent / "treesleuth.log.1").is_file()
    assert "second record" in log_path.read_text(encoding="utf-8")
