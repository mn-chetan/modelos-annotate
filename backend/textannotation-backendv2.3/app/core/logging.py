from __future__ import annotations

import logging
import re
from logging.config import dictConfig

_REDACTION_PATTERNS = [
    re.compile(r"(MONGODB_URI=)([^\s]+)", re.IGNORECASE),
]


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in _REDACTION_PATTERNS:
            message = pattern.sub(r"\1[REDACTED]", message)
        record.msg = message
        record.args = ()
        return True


def configure_logging() -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"redact": {"()": RedactionFilter}},
            "formatters": {
                "default": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "filters": ["redact"],
                }
            },
            "root": {"handlers": ["console"], "level": "INFO"},
        }
    )
