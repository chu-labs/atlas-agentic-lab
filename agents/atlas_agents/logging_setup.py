from __future__ import annotations

import logging
import sys

from pythonjsonlogger.json import JsonFormatter

from .config import config


def configure() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(
        JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "ts", "levelname": "level", "name": "logger"},
            static_fields={"agent": config().agent_name},
        )
    )
    root.addHandler(h)
    root.setLevel("INFO")
    for noisy in ("botocore", "boto3", "urllib3", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel("WARNING")
