"""日志配置。"""

from __future__ import annotations

import logging


def setup_logger(name: str, level: str = "INFO") -> logging.Logger:
    """配置并返回控制台日志记录器。"""
    logger = logging.getLogger(name)

    if logger.handlers:
        logger.setLevel(level)
        return logger

    logger.setLevel(level)
    logger.propagate = False

    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logger.addHandler(handler)
    return logger
