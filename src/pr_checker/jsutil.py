"""Small helpers that keep Python string handling identical to the JavaScript the logic was designed around."""
from __future__ import annotations

import re
from datetime import datetime, timezone

# JavaScript's String.prototype.trim() and /\s/ cover these characters (including the BOM, U+FEFF).
JS_WHITESPACE = " \t\n\v\f\r                 　﻿"

_WS_RUN = re.compile(r"[\s﻿]+")


def js_strip(text: str) -> str:
    return text.strip(JS_WHITESPACE)


def squash(text: str) -> str:
    """Removes all whitespace."""
    return _WS_RUN.sub("", text)


def collapse(text: str) -> str:
    """Collapses whitespace runs to one space and trims."""
    return js_strip(_WS_RUN.sub(" ", text))


def iso_now() -> str:
    """Like JavaScript's new Date().toISOString(): UTC with milliseconds, e.g. 2026-10-25T17:35:27.571Z."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
