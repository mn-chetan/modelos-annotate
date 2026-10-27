from __future__ import annotations

import logging
import re
from logging.config import dictConfig

_REDACTION_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{15,}", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"AIza[0-9A-Za-z-_]{35}"), "[REDACTED]"),
    (re.compile(r'("(?:password|secret|token|api_key|access_token|private_key)"\s*:\s*")[^"]+(")', re.IGNORECASE), r"\1[REDACTED]\2"),
    (re.compile(r"((?:password|secret|token|api_key)=)[^&\s]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b"), "[REDACTED-SSN]"),
    (re.compile(r"\b[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}\b"), "[REDACTED-CC]"),
]

# Expose patterns for backwards compatibility
_REDACTION_PATTERNS = [rule[0] for rule in _REDACTION_RULES]


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern, replacement in _REDACTION_RULES:
            message = pattern.sub(replacement, message)
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
