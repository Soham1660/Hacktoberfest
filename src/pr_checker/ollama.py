"""Talks to the local Ollama server: JSON-schema-constrained chat, token streaming, health and warm-up."""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Optional

import httpx

from .config import config
from .models import Health
from .schema import Node, SchemaError, top_level_schema


class ModelError(Exception):
    pass


# Keep num_ctx identical on every request: a different value makes Ollama reload the model.
NUM_CTX = 6144
BASE_OPTIONS: Dict[str, Any] = {"temperature": 0, "num_ctx": NUM_CTX, "top_k": 1}


@dataclass
class JsonResult:
    data: Any
    ms: int
    output_tokens: int


def _seconds(ms: float) -> float:
    return ms / 1000


async def _post(client: httpx.AsyncClient, path: str, body: Dict[str, Any]) -> httpx.Response:
    try:
        res = await client.post(f"{config.host}{path}", json=body)
    except httpx.TimeoutException as err:
        raise ModelError("Model call timed out") from err
    except httpx.HTTPError as err:
        raise ModelError(f"Cannot reach Ollama at {config.host}. Is it running? ({err})") from err
    if res.status_code >= 400:
        raise ModelError(f"Ollama returned {res.status_code}: {res.text[:200]}")
    return res


async def chat_json(
    *,
    model: str,
    system: str,
    user: str,
    schema: Node,
    max_tokens: Optional[int] = None,
) -> JsonResult:
    """Calls the model with a JSON schema enforced by Ollama's constrained decoding,
    then validates the result against the same schema. Retries once on malformed output."""
    fmt = top_level_schema(schema)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last_err = ""
    for _attempt in range(2):
        started = time.monotonic()
        body = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": False,
            "format": fmt,
            "keep_alive": "30m",
            "options": {**BASE_OPTIONS, "num_predict": max_tokens or 700},
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(_seconds(config.timeout_ms))) as client:
            res = await _post(client, "/api/chat", body)
        payload = res.json()
        raw = (payload.get("message") or {}).get("content") or ""
        ms = int((time.monotonic() - started) * 1000)
        if config.debug:
            print(f"[model] {model} {ms}ms out={payload.get('eval_count')} prompt={payload.get('prompt_eval_count')} chars={len(raw)}", file=sys.stderr)
        try:
            data = schema.parse(json.loads(raw))
            return JsonResult(data=data, ms=ms, output_tokens=payload.get("eval_count") or 0)
        except SchemaError as err:
            last_err = err.pretty()
        except ValueError as err:
            last_err = str(err)
    raise ModelError(f"Model output did not match the expected shape: {last_err[:200]}")


async def chat_stream(*, model: str, system: str, user: str, max_tokens: Optional[int] = None) -> AsyncIterator[str]:
    """Streams plain-text tokens from the model."""
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": True,
        "think": False,
        "keep_alive": "30m",
        "options": {**BASE_OPTIONS, "temperature": 0.3, "top_k": 40, "num_predict": max_tokens or 400},
    }
    deadline = time.monotonic() + _seconds(config.timeout_ms)
    async with httpx.AsyncClient(timeout=httpx.Timeout(_seconds(config.timeout_ms))) as client:
        try:
            async with client.stream("POST", f"{config.host}/api/chat", json=body) as res:
                if res.status_code >= 400:
                    text = (await res.aread()).decode("utf8", "replace")
                    raise ModelError(f"Ollama returned {res.status_code}: {text[:200]}")
                async for line in res.aiter_lines():
                    if time.monotonic() > deadline:
                        raise ModelError("Model call timed out")
                    line = line.strip()
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if chunk.get("error"):
                        raise ModelError(chunk["error"])
                    content = (chunk.get("message") or {}).get("content")
                    if content:
                        yield content
        except httpx.TimeoutException as err:
            raise ModelError("Model call timed out") from err
        except httpx.HTTPError as err:
            raise ModelError(f"Cannot reach Ollama at {config.host}. Is it running? ({err})") from err


async def check_health() -> Health:
    base = dict(host=config.host, model=config.model, claims_model=config.claims_model)
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            res = await client.get(f"{config.host}/api/tags")
        names = {m["name"] for m in res.json()["models"]}
        has = lambda m: m in names or f"{m}:latest" in names
        model_installed = has(config.model)
        claims_installed = has(config.claims_model)
        missing = [m for m in (config.model, config.claims_model) if not has(m)]
        message = None
        if missing:
            message = "Model not installed. Run: ollama pull " + " && ollama pull ".join(dict.fromkeys(missing))
        return Health(ok=not missing, ollama=True, model_installed=model_installed, claims_model_installed=claims_installed, message=message, **base)
    except Exception:
        return Health(
            ok=False,
            ollama=False,
            model_installed=False,
            claims_model_installed=False,
            message=f"Ollama is not reachable at {config.host}. Start it with: ollama serve",
            **base,
        )


async def warm_up() -> None:
    """Loads the model into memory so the first real request is not slowed by a cold start."""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            await client.post(
                f"{config.host}/api/generate",
                json={"model": config.model, "prompt": "", "keep_alive": "30m", "options": {"num_ctx": NUM_CTX}},
            )
    except Exception:
        pass
