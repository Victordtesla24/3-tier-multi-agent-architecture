from __future__ import annotations

import logging
import re


_SECRET_PATTERNS = [
    # Google Generative Language API key query param
    (re.compile(r"([?&]key=)([^&\s]+)", flags=re.IGNORECASE), r"\1[REDACTED]"),
    # OpenAI style keys
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "[REDACTED]"),
    # Generic bearer tokens
    (re.compile(r"(Bearer\s+)([A-Za-z0-9._-]{12,})", flags=re.IGNORECASE), r"\1[REDACTED]"),
]


def redact_sensitive_text(value: str) -> str:
    redacted = value
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


class RedactionFilter(logging.Filter):
    """Redacts common API key patterns from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
            record.msg = redact_sensitive_text(str(rendered))
            record.args = ()
        except Exception:
            # Never block logging if redaction fails.
            pass
        return True


def install_log_redaction() -> None:
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.addFilter(RedactionFilter())
