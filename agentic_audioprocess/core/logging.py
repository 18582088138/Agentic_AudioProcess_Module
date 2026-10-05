"""日志 / Logging.

日志里不出现路径以外的敏感信息（本模组本来也不持有凭证）。
"""

from __future__ import annotations

import logging
import os
import sys

_LOGGER_NAME = "agentic_audioprocess"
_configured = False


def _configure() -> None:
    global _configured
    if _configured:
        return
    level = os.environ.get("AUDIOPROCESS_LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", datefmt="%H:%M:%S"))
    root = logging.getLogger(_LOGGER_NAME)
    root.handlers[:] = [handler]
    root.setLevel(getattr(logging, level, logging.INFO))
    root.propagate = False
    _configured = True


def get_logger(suffix: str = "") -> logging.Logger:
    """取子 logger / get a child logger."""
    _configure()
    return logging.getLogger(f"{_LOGGER_NAME}.{suffix}" if suffix else _LOGGER_NAME)


__all__ = ["get_logger"]
