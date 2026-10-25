"""Runtime configuration, read from the environment (and an optional .env file) once at import."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Repository root when running from a checkout (src/pr_checker/config.py -> root). Override with PR_CHECKER_ROOT.
ROOT = Path(os.environ.get("PR_CHECKER_ROOT") or Path(__file__).resolve().parents[2])
PACKAGE_DIR = Path(__file__).resolve().parent


def load_dotenv(path: Path) -> None:
    """Minimal .env reader: KEY=value lines; real environment variables win."""
    try:
        text = path.read_text(encoding="utf8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv(Path.cwd() / ".env")
load_dotenv(ROOT / ".env")


def _number(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Config:
    host: str
    model: str
    claims_model: str
    timeout_ms: float
    concurrency: int  # parallel model calls. Match OLLAMA_NUM_PARALLEL on the Ollama server; extra requests just queue.
    github_token: Optional[str]
    debug: bool


def _build() -> Config:
    model = os.environ.get("PR_CHECKER_MODEL") or "qwen3:8b"
    return Config(
        host=(os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/"),
        model=model,
        claims_model=os.environ.get("PR_CHECKER_CLAIMS_MODEL") or model,
        timeout_ms=_number("PR_CHECKER_TIMEOUT_MS", 180_000),
        concurrency=int(_number("PR_CHECKER_CONCURRENCY", 3)),
        github_token=os.environ.get("GITHUB_TOKEN") or None,
        debug=bool(os.environ.get("PR_CHECKER_DEBUG")),
    )


config = _build()
