"""The bundled sample pull requests (built by scripts/build_samples.py)."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict, List

from .config import PACKAGE_DIR

SAMPLES_PATH = PACKAGE_DIR / "data" / "samples.json"


@lru_cache(maxsize=1)
def load_samples() -> List[Dict[str, Any]]:
    return json.loads(SAMPLES_PATH.read_text(encoding="utf8"))
