"""Allowlisted structured logging: never log arbitrary exception bodies or inputs."""

import json
import logging
from datetime import datetime, timezone


class SafeJSONFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "time": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        for key in ("iteration_id", "error_type"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        return json.dumps(data)


def configure_logging():
    logger = logging.getLogger("workflow")
    handler = logging.StreamHandler()
    handler.setFormatter(SafeJSONFormatter())
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
