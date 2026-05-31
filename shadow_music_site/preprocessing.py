from __future__ import annotations

import re
from datetime import datetime


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_publish_time(value: object) -> str:
    if value in (None, "", 0):
        return ""
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        text = normalize_whitespace(str(value))
        if not text:
            return ""
        for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y/%m", "%Y"):
            try:
                parsed = datetime.strptime(text, pattern)
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return ""
    timestamp = numeric / 1000 if numeric > 10_000_000_000 else numeric
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return ""
