"""Structured JSON logging. One line per event, always parseable."""
from __future__ import annotations

import logging
import sys

from pythonjsonlogger.json import JsonFormatter

from .settings import settings


def configure() -> None:
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "ts", "levelname": "level", "name": "logger"},
            static_fields={"service": settings().service_name, "env": settings().environment},
        )
    )
    root.handlers = [handler]
    root.setLevel(settings().log_level)
    logging.getLogger("uvicorn.access").disabled = True
