"""Bounded loggers for model and image-generation calls."""

import logging
from logging.handlers import RotatingFileHandler

from .config import IMAGE_LOG_FILE, LOG_DIR, LOG_FILE

LOGGER = logging.getLogger("nutriparse.llm")
IMAGE_LOGGER = logging.getLogger("nutriparse.image")


def configure_logging():
    """Write bounded, structured AI and image generation logs to separate files."""
    LOG_DIR.mkdir(exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for logger, log_file in (
        (LOGGER, LOG_FILE),
        (IMAGE_LOGGER, IMAGE_LOG_FILE),
    ):
        if logger.handlers:
            continue
        handler = RotatingFileHandler(
            log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
        )
        handler.setFormatter(formatter)
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False
