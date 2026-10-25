"""HTTP API and static web UI. One process serves both on port 8787 (PORT)."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from .config import PACKAGE_DIR, ROOT, config
from .github import GitHubError, fetch_pull_request
from .models import PullRequestInput, to_json
from .ollama import chat_stream, check_health, warm_up
from .pipeline import InputError, prepare, run_analysis
from .prompts import COMMENT_SYSTEM
from .samples import load_samples
from .schema import Arr, Obj, SchemaError, Str
from .units import LIMITS

WEB_DIR = PACKAGE_DIR / "web"

PR_INPUT = Obj(
    {
        "title": Str(max=500, required="Title is required.", too_long="The title is longer than 500 characters."),
        "description": Str(max=20_000, required="Description is required.", too_long="The description is longer than 20,000 characters."),
        "diff": Str(
            max=LIMITS["max_diff_bytes"],
            required="Diff is required.",
            too_long=f"The diff is larger than {LIMITS['max_diff_bytes'] // 1000} KB. Split the PR or paste a subset.",
        ),
        "source": Str(max=200),
    },
    optional=["source"],
)

COMMENT_INPUT = Obj(
    {
        "title": Str(max=500),
        "claims": Arr(Obj({"id": Str(), "text": Str(max=300), "status": Str()}), max=12),
        "findings": Arr(
            Obj({"location": Str(max=300), "what": Str(max=300), "why": Str(max=400), "status": Str(max=40)}),
            max=30,
        ),
    }
)


def _input_error(err: SchemaError) -> str:
    """The first validation message for a PR payload, in words a user can act on."""
    return err.message if err.path else "Send a JSON body with title, description and diff."


async def _json_body(request: Request) -> Any:
    try:
        return await request.json()
    except Exception:
        return None


def _parse_pr(body: Any) -> Tuple[Optional[PullRequestInput], Optional[str]]:
    try:
        data = PR_INPUT.parse(body)
    except SchemaError as err:
        return None, _input_error(err)
    return PullRequestInput(data["title"], data["description"], data["diff"], data.get("source")), None


def _error(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    port = os.environ.get("PORT", "8787")
    print(f"PR Checker on http://127.0.0.1:{port}  ·  model {config.model} via {config.host}", flush=True)

    async def setup_check() -> None:
        h = await check_health()
        if h.ok:
            await warm_up()
        else:
            print(f"[setup] {h.message}", file=sys.stderr, flush=True)

    task = asyncio.create_task(setup_check())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="PR Checker", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.exception_handler(Exception)
async def _on_error(_request: Request, err: Exception) -> JSONResponse:
    print(f"[api] {err}", file=sys.stderr, flush=True)
    return _error("Unexpected server error.", 500)


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse(to_json(await check_health()))


@app.get("/api/eval")
async def eval_results() -> JSONResponse:
    path = ROOT / "eval" / "results.json"
    return JSONResponse(json.loads(path.read_text(encoding="utf8")) if path.exists() else None)


@app.get("/api/samples")
async def samples() -> JSONResponse:
    return JSONResponse([{k: s[k] for k in ("id", "title", "repo", "hint")} for s in load_samples()])


@app.get("/api/samples/{sample_id}")
async def sample(sample_id: str) -> JSONResponse:
    s = next((x for x in load_samples() if x["id"] == sample_id), None)
    if s is None:
        return _error("Unknown sample", 404)
    return JSONResponse({"title": s["title"], "description": s["description"], "diff": s["diff"], "source": s["repo"]})


@app.post("/api/github")
async def github(request: Request) -> JSONResponse:
    body = await _json_body(request)
    if not isinstance(body, dict) or not isinstance(body.get("url"), str) or len(body["url"]) > 300:
        return _error("Send { url }.")
    try:
        return JSONResponse(to_json(await fetch_pull_request(body["url"])))
    except GitHubError as err:
        return _error(str(err))


@app.post("/api/scan")
async def scan(request: Request) -> JSONResponse:
    """Static rules only. Works without a model; the UI labels it as such."""
    pr, err = _parse_pr(await _json_body(request))
    if err or pr is None:
        return _error(err or "")
    try:
        files, signals, units, truncated = prepare(pr)
    except InputError as e:
        return _error(str(e))
    return JSONResponse(to_json({"files": files, "signals": signals, "units": units, "truncated": truncated}))


@app.post("/api/analyze")
async def analyze(request: Request) -> Any:
    """Full audit. Streams newline-delimited JSON events as each stage completes."""
    pr, err = _parse_pr(await _json_body(request))
    if err or pr is None:
        return _error(err or "")
    try:
        prepare(pr)  # fail fast with a 400 on unusable input
    except InputError as e:
        return _error(str(e))

    async def events() -> AsyncIterator[str]:
        queue: "asyncio.Queue[Optional[str]]" = asyncio.Queue()

        def emit(event: Dict[str, Any]) -> None:
            queue.put_nowait(json.dumps(to_json(event), ensure_ascii=False) + "\n")

        async def run() -> None:
            try:
                await run_analysis(pr, emit)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                emit({"type": "error", "message": str(e) or type(e).__name__})
            finally:
                queue.put_nowait(None)

        task = asyncio.create_task(run())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            task.cancel()  # the client went away or the run finished

    return StreamingResponse(events(), media_type="application/x-ndjson; charset=utf-8", headers={"Cache-Control": "no-store"})


@app.post("/api/comment")
async def comment(request: Request) -> Any:
    """Drafts a maintainer review comment from confirmed findings. The user copies it; nothing is posted."""
    try:
        data = COMMENT_INPUT.parse(await _json_body(request))
    except SchemaError:
        return _error("Invalid input.")
    user = "\n".join(
        [
            f"PR TITLE: {data['title']}",
            "",
            "CLAIM CHECK",
            *[f"- {cl['id']} “{cl['text']}”: {cl['status'].replace('_', ' ', 1)}" for cl in data["claims"]],
            "",
            "FINDINGS",
            *([f"- {f['location']} [{f['status']}]: {f['what']}. {f['why']}" for f in data["findings"]] or ["(none)"]),
        ]
    )

    async def tokens() -> AsyncIterator[str]:
        try:
            async for tok in chat_stream(model=config.model, system=COMMENT_SYSTEM, user=user, max_tokens=450):
                yield tok
        except asyncio.CancelledError:
            raise
        except Exception as e:
            yield f"\n\n[Could not finish the draft: {e}]"

    return StreamingResponse(tokens(), media_type="text/plain; charset=utf-8")


@app.get("/{path:path}", include_in_schema=False)
async def web(path: str) -> Any:
    """The web UI. Unknown non-API paths get index.html."""
    if path == "api" or path.startswith("api/"):
        return JSONResponse({"error": "Not found"}, status_code=404)
    target = (WEB_DIR / path).resolve()
    if path and target.is_file() and WEB_DIR.resolve() in target.parents:
        return FileResponse(target)
    index = WEB_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    return JSONResponse({"error": "Web UI not found."}, status_code=404)
