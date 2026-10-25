from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from pr_checker import pipeline, server
from pr_checker.ollama import JsonResult
from pr_checker.samples import load_samples

DIFF = "--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n-Teh project\n+The project\n"


@pytest.fixture()
def client():
    with TestClient(server.app) as c:
        yield c


def test_lists_samples_without_their_diffs(client):
    r = client.get("/api/samples")
    assert r.status_code == 200
    assert [s["id"] for s in r.json()] == [s["id"] for s in load_samples()]
    assert set(r.json()[0]) == {"id", "title", "repo", "hint"}


def test_returns_a_sample_and_404s_unknown_ones(client):
    first = load_samples()[0]
    r = client.get(f"/api/samples/{first['id']}")
    assert r.json()["source"] == first["repo"]
    assert client.get("/api/samples/nope").status_code == 404


@pytest.mark.parametrize(
    "body,message",
    [
        (None, "Send a JSON body with title, description and diff."),
        ({"description": "", "diff": DIFF}, "Title is required."),
        ({"title": "t", "diff": DIFF}, "Description is required."),
        ({"title": "t", "description": ""}, "Diff is required."),
        ({"title": "t" * 501, "description": "", "diff": DIFF}, "The title is longer than 500 characters."),
        ({"title": "t", "description": "", "diff": "hello"}, "No files found. Paste a unified diff (the output of `git diff` or a GitHub .diff URL)."),
        ({"title": "t", "description": "", "diff": "   "}, "The diff is empty."),
    ],
)
def test_scan_rejects_unusable_input_in_words_a_user_can_act_on(client, body, message):
    r = client.post("/api/scan", json=body) if body is not None else client.post("/api/scan", content="not json")
    assert r.status_code == 400
    assert r.json() == {"error": message}


def test_scan_returns_camel_case_static_results(client):
    r = client.post("/api/scan", json={"title": "docs: typo", "description": "", "diff": DIFF})
    body = r.json()
    assert r.status_code == 200
    assert set(body) == {"files", "signals", "units", "truncated"}
    assert body["files"][0]["category"] == "docs"
    assert body["units"][0]["lineIdx"] == [0, 1]


def test_analyze_streams_ndjson_events_ending_in_a_report(client, monkeypatch):
    async def fake_chat_json(*, schema, **_kw):
        first_key = next(iter(schema.fields))
        if first_key == "claims":
            data = {"claims": [{"text": "Fixes a typo", "kind": "change", "area": "docs", "limit": "other", "discloses_behavior": False}]}
        else:
            data = {"changes": [{"lines": "L1-L2", "what": "Fix typo", "effect": "cosmetic", "covered_by": ["C1"], "violates": [], "concern": "none", "why": ""}]}
        return JsonResult(data=data, ms=5, output_tokens=1)

    monkeypatch.setattr(pipeline, "chat_json", fake_chat_json)
    with client.stream("POST", "/api/analyze", json={"title": "Fix typo", "description": "Fixes a typo", "diff": DIFF}) as r:
        assert r.headers["content-type"].startswith("application/x-ndjson")
        events = [json.loads(line) for line in r.iter_lines() if line]
    assert [e["type"] for e in events][0] == "parsed"
    assert events[-1]["type"] == "done"
    report = next(e["report"] for e in events if e["type"] == "report")
    assert report["verdict"] in {"matches", "trivial"}
    assert report["claims"][0]["status"] == "supported"
    assert "lineCoverage" in report and "changeStatus" in report


def test_analyze_reports_model_failures_as_an_error_event(client, monkeypatch):
    async def broken(**_kw):
        raise pipeline.ModelError("Cannot reach Ollama at http://127.0.0.1:1. Is it running? (boom)")

    monkeypatch.setattr(pipeline, "chat_json", broken)
    with client.stream("POST", "/api/analyze", json={"title": "t", "description": "d", "diff": DIFF}) as r:
        events = [json.loads(line) for line in r.iter_lines() if line]
    assert events[-1] == {"type": "error", "message": "Cannot reach Ollama at http://127.0.0.1:1. Is it running? (boom)"}


def test_comment_rejects_invalid_input(client):
    assert client.post("/api/comment", json={"title": 1}).json() == {"error": "Invalid input."}


def test_serves_the_web_ui_and_falls_back_to_index_for_unknown_routes(client):
    assert "<title>PR Checker" in client.get("/").text
    assert client.get("/js/main.js").headers["content-type"].startswith("text/javascript")
    assert "<title>PR Checker" in client.get("/some/client/route").text
    assert client.get("/api/unknown").status_code == 404
