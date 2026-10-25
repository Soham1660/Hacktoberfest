"""The audit: claims -> per-excerpt review -> skeptical self-check -> deterministic scoring."""
from __future__ import annotations

import asyncio
import re
import time
from functools import cmp_to_key
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from .config import config
from .diff import parse_unified_diff
from .grounding import citation_coverage, ground_citations, parse_line_refs
from .jsutil import js_strip
from .models import Change, Claim, FileDiff, Hunk, PullRequestInput, SelfCheck, Unit
from .moved import find_moved_lines
from .ollama import ModelError, chat_json  # noqa: F401  (ModelError is part of this module's surface)
from .prompts import (
    CLAIMS_SCHEMA,
    CLAIMS_SYSTEM,
    REVIEW_SYSTEM,
    VERIFY_SYSTEM,
    VerifyItem,
    claims_user,
    review_schema,
    review_user,
    verify_schema,
    verify_user,
)
from .score import ScoreInput, build_report, max_concern, rule_hits, self_check_mode
from .signals import scan_signals
from .status import change_status
from .units import LIMITS, build_units

Emit = Callable[[Dict[str, Any]], None]


class InputError(Exception):
    pass


def prepare(inp: PullRequestInput):
    if not js_strip(inp.diff):
        raise InputError("The diff is empty.")
    if len(inp.diff.encode("utf8", "surrogatepass")) > LIMITS["max_diff_bytes"]:
        raise InputError(f"The diff is larger than {round(LIMITS['max_diff_bytes'] / 1000)} KB. Split the PR or paste a subset.")
    files = parse_unified_diff(inp.diff)
    if not files:
        raise InputError("No files found. Paste a unified diff (the output of `git diff` or a GitHub .diff URL).")
    if not any(f.hunks or f.binary for f in files):
        raise InputError("The diff has file headers but no changes.")
    signals = scan_signals(files)
    units, truncated = build_units(files)
    return files, signals, units, truncated


def _now_ms() -> int:
    return int(time.time() * 1000)


async def run_analysis(inp: PullRequestInput, emit: Emit) -> None:
    """Runs the full audit and reports progress through `emit`. Every model output is
    validated, grounded against the real diff, and scored by deterministic code.

    Cancel the surrounding task to stop it.
    """
    started = _now_ms()
    files, signals, units, truncated = prepare(inp)
    emit({"type": "parsed", "data": {"files": files, "units": units, "signals": signals, "truncated": truncated}, "model": config.model, "claimsModel": config.claims_model})
    categories = {f.path: f.category for f in files}
    moved = find_moved_lines(files)

    file_by_index = {f.index: f for f in files}
    hunk_by_id: Dict[str, Hunk] = {h.id: h for f in files for h in f.hunks}
    model_calls = 0

    # Stage A: what does the author say this PR does?
    emit({"type": "stage", "stage": "claims", "status": "start"})
    claims_res = await chat_json(
        model=config.claims_model,
        system=CLAIMS_SYSTEM,
        user=claims_user(inp.title, inp.description),
        schema=CLAIMS_SCHEMA,
        max_tokens=400,
    )
    model_calls += 1
    claims = _build_claims(claims_res.data["claims"], inp)
    emit({"type": "claims", "claims": claims})
    emit({"type": "stage", "stage": "claims", "status": "done"})

    # Stage B: what does each excerpt of the diff actually do?
    emit({"type": "stage", "stage": "review", "status": "start"})
    schema = review_schema([c.id for c in claims if c.kind == "change"], [c.id for c in claims])
    changes: List[Change] = []
    coverage = {"changed": 0, "cited": 0}
    failed_units = 0

    model_units = [u for u in units if u.mode == "model"]
    unit_order = {u.id: i for i, u in enumerate(units)}

    async def review_unit(unit: Unit) -> None:
        nonlocal model_calls, failed_units
        file = file_by_index[unit.file_index]
        hunk = hunk_by_id[unit.hunk_id]
        emit({"type": "unit_start", "unitId": unit.id})
        try:
            res = await chat_json(
                model=config.model,
                system=REVIEW_SYSTEM,
                user=review_user(claims, file, hunk, unit, signals, moved),
                schema=schema,
                max_tokens=900,
            )
            model_calls += 1
            unit_changes = to_changes(res.data["changes"], unit, hunk, claims, file, moved)
            cov = citation_coverage(unit, hunk, [i for c in unit_changes for i in c.line_idx])
            coverage["changed"] += cov["changed"]
            coverage["cited"] += cov["cited"]
            changes.extend(unit_changes)
            emit({"type": "unit_result", "unitId": unit.id, "changes": unit_changes, "ms": res.ms})
        except asyncio.CancelledError:
            raise
        except Exception as err:  # a failed excerpt is reported, not fatal
            failed_units += 1
            emit({"type": "unit_error", "unitId": unit.id, "message": str(err)})

    await pool(model_units, config.concurrency, review_unit)

    def by_order(a: Change, b: Change) -> int:
        d = unit_order[a.unit_id] - unit_order[b.unit_id]
        if d:
            return d
        if not a.line_idx or not b.line_idx:
            return 0  # NaN in the original comparator: treated as equal
        return a.line_idx[0] - b.line_idx[0]

    changes.sort(key=cmp_to_key(by_order))
    emit({"type": "stage", "stage": "review", "status": "done"})

    # Stage C: a skeptical second pass over serious flags and suspicious "covered" verdicts,
    # batched per excerpt so each excerpt costs at most one extra call.
    to_verify: List[Tuple[Change, str]] = []
    for c in changes:
        mode = self_check_mode(c, signals)
        if mode is not None:
            to_verify.append((c, mode))
    if to_verify:
        emit({"type": "stage", "stage": "verify", "status": "start"})
        by_unit: Dict[str, List[Tuple[Change, str]]] = {}
        for entry in to_verify:
            by_unit.setdefault(entry[0].unit_id, []).append(entry)

        def claim_text(cid: str) -> str:
            found = next((cl for cl in claims if cl.id == cid), None)
            return f"{cid} (“{found.text if found else 'undefined'}”)"

        async def verify_batch(item: Tuple[str, List[Tuple[Change, str]]]) -> None:
            nonlocal model_calls
            unit_id, batch = item
            unit = next(u for u in units if u.id == unit_id)
            hunk = hunk_by_id[unit.hunk_id]
            file = file_by_index[unit.file_index]
            for c, _ in batch:
                emit({"type": "verify_start", "changeId": c.id})
            items: List[VerifyItem] = []
            for i, (c, mode) in enumerate(batch):
                if mode == "coverage":
                    hits = [s.title.lower() for s in rule_hits(c, signals)]
                    extra = f", even though static rules flagged it ({'; '.join(hits)})" if hits else ""
                    judgment = f"this change IS covered by {' and '.join(claim_text(x) for x in c.claims)}{extra}."
                elif change_status(c) == "contradicts":
                    judgment = f"this change BREAKS {' and '.join(claim_text(x) for x in c.contradicts)}. {c.why}"
                else:
                    judgment = f"this change is NOT covered by any claim. {c.why}"
                items.append(VerifyItem(f"K{i + 1}", [unit.line_idx.index(idx) + 1 for idx in c.line_idx], c.what, judgment))
            try:
                res = await chat_json(
                    model=config.model,
                    system=VERIFY_SYSTEM,
                    user=verify_user(claims, file, hunk, unit, items, moved),
                    schema=verify_schema([it.key for it in items]),
                    max_tokens=120 + 90 * len(items),
                )
                model_calls += 1
                for v in res.data["verdicts"]:
                    n = int(v["key"][1:]) - 1
                    if not 0 <= n < len(batch):
                        continue
                    c, mode = batch[n]
                    apply_self_check(c, mode, v["decision"] == "colleague_is_right", v["severity"], js_strip(v["reason"]), categories)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass  # Keep the first-pass judgment if the check itself fails; it is shown without a self-check.
            for c, _ in batch:
                emit({"type": "verify_result", "changeId": c.id, "change": c})

        await pool(list(by_unit.items()), config.concurrency, verify_batch)
        emit({"type": "stage", "stage": "verify", "status": "done"})

    emit({"type": "stage", "stage": "report", "status": "start"})
    report = build_report(
        ScoreInput(
            files=files,
            units=units,
            signals=signals,
            claims=claims,
            changes=changes,
            coverage=coverage,
            failed_units=failed_units,
            model_calls=model_calls,
            elapsed_ms=_now_ms() - started,
        )
    )
    emit({"type": "report", "report": report})
    emit({"type": "stage", "stage": "report", "status": "done"})
    emit({"type": "done", "elapsedMs": _now_ms() - started})


def _build_claims(raw: List[Dict[str, Any]], inp: PullRequestInput) -> List[Claim]:
    seen = set()
    kept: List[Dict[str, Any]] = []
    text_all = f"{inp.title}\n{inp.description}"
    for c in raw:
        text = js_strip(c["text"])
        if _ISSUE_REF.search(text):  # issue references are not claims
            continue
        key = text.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        # A promise is only enforced by code if the author's own words make it (see promise_has_evidence).
        if not (c["kind"] == "change" or c["limit"] == "other" or promise_has_evidence(c["limit"], text_all)):
            continue
        kept.append(c)
    claims = [
        Claim(
            id=f"C{i + 1}",
            text=js_strip(c["text"]),
            kind=c["kind"],
            area=c["area"],
            limit=c["limit"] if c["kind"] == "constraint" else "other",
            discloses_behavior=c["kind"] == "change" and c["discloses_behavior"],
        )
        for i, c in enumerate(kept)
    ]
    implied = implied_constraint(inp.title)
    if implied and not any(c.limit == "only_area" and c.area == implied.area for c in claims):
        implied.id = f"C{len(claims) + 1}"
        claims.append(implied)
    return claims


_ISSUE_REF = re.compile(r"^(closes|fixes|resolves|refs?)\b[^a-z]*#\d+\.?$", re.I)

_NO_BEHAVIOR_EVIDENCE = re.compile(
    r"\bno\s+(other\s+)?(functional|behaviou?r(al)?|runtime|logic|user[- ]facing)\s+changes?\b|\bpure(ly)?\s+(a\s+)?refactor|\brefactor(ing)?[ -]only\b|\bbehaviou?r[- ]preserving\b|\bnon[- ]functional\b|\bdoes(n't| not) change (any )?(behaviou?r|functionality)\b|\bno[- ]op\b",
    re.I,
)
_ONLY_AREA_EVIDENCE = re.compile(
    r"\b(docs?|documentation|readme|tests?|ci|comments?|typos?)[- ]only\b|\bonly\s+(changes?|touches|updates|modifies|affects|fixes|adds)\b|\bnothing else\b|\bno (code|source|functional) changes\b",
    re.I,
)


def promise_has_evidence(limit: str, text: str) -> bool:
    """The claims model sometimes turns a description into promises the author never made
    ("only changes code in lib/", "no behavior change in tests"). Code only enforces a
    promise when the title or description actually says it."""
    if limit == "no_behavior_change":
        return bool(_NO_BEHAVIOR_EVIDENCE.search(text))
    if limit == "only_area":
        return bool(_ONLY_AREA_EVIDENCE.search(text))
    return True


def _effect_floor(effect: str, category: Optional[str]) -> str:
    """Minimum concern for a change that is unmentioned or breaks a promise, by what it does."""
    if category in ("test", "docs"):
        return "low"
    return "high" if effect == "security" else "medium" if effect == "behavior" else "low"


def apply_self_check(c: Change, mode: str, agree: bool, severity: str, reason: str, categories: Dict[str, str]) -> None:
    category = categories.get(c.file)
    if mode == "flag":
        c.self_check = SelfCheck(mode=mode, outcome="upheld" if agree else "withdrawn", severity=severity, reason=reason, claims_before=c.claims)
        if agree:
            c.concern = max_concern(severity, _effect_floor(c.effect, category))
    else:
        c.self_check = SelfCheck(mode=mode, outcome="confirmed" if agree else "overturned", severity=severity, reason=reason, claims_before=c.claims)
        if not agree:
            c.claims = []
            c.concern = max_concern(severity, _effect_floor(c.effect, category))
            c.why = reason


def implied_constraint(title: str) -> Optional[Claim]:
    """Conventional-commit types and narrow titles promise a scope even when the
    description doesn't say so. Code adds that promise if the model didn't.
    The returned claim has an empty id for the caller to assign."""
    t = js_strip(title)
    conv = re.match(r"^(docs|test|tests|ci)(\([^)]*\))?!?:", t, re.I)
    if conv:
        kind = conv.group(1).lower()
        if kind == "docs":
            return Claim("", "Only changes documentation (implied by the “docs:” title)", "constraint", "docs", "only_area", False)
        if kind == "ci":
            return Claim("", "Only changes CI configuration (implied by the “ci:” title)", "constraint", "ci", "only_area", False)
        return Claim("", "Only changes tests (implied by the “test:” title)", "constraint", "tests", "only_area", False)
    if re.search(r"\btypos?\b", t, re.I) and re.search(r"\b(readme|docs?|documentation|guide|comment)", t, re.I):
        return Claim("", "Only fixes a typo in the documentation (implied by the title)", "constraint", "docs", "only_area", False)
    return None


_AREA_FILES: Dict[str, Optional[List[str]]] = {
    "any": None,
    "docs": ["docs"],
    "tests": ["test"],
    "ci": ["ci"],
    "build": ["build", "manifest", "lockfile"],
    "dependencies": ["manifest", "lockfile"],
    "code": ["source", "config", "build", "manifest", "lockfile", "asset"],
}


def in_area(area: str, category: str) -> bool:
    """Whether a file of `category` falls inside a claim's `area`."""
    allowed = _AREA_FILES.get(area)
    return True if allowed is None else category in allowed


async def pool(items: List[Any], limit: int, fn: Callable[[Any], Awaitable[None]]) -> None:
    """Runs `fn` over `items` with at most `limit` in flight. Raises the first error and cancels the rest."""
    queue = list(items)
    nxt = 0

    async def worker() -> None:
        nonlocal nxt
        while nxt < len(queue):
            item = queue[nxt]
            nxt += 1
            await fn(item)

    workers = [asyncio.ensure_future(worker()) for _ in range(min(max(1, limit), len(queue)))]
    try:
        await asyncio.gather(*workers)
    except BaseException:
        for w in workers:
            w.cancel()
        raise


def to_changes(raw: List[Dict[str, Any]], unit: Unit, hunk: Hunk, claims: List[Claim], file: FileDiff, moved: Dict[str, str]) -> List[Change]:
    """Turns the model's raw judgments into Changes, applying the deterministic rules
    the model is unreliable at: claim areas bound what a claim can cover, and
    scope or no-behavior-change promises are enforced by code."""
    by_id = {c.id: c for c in claims}
    test_claim = next((c for c in claims if c.kind == "change" and c.area == "tests"), None)
    out: List[Change] = []
    for r in raw:
        g = ground_citations(parse_line_refs(r["lines"]), unit, hunk)
        # Code that appears unchanged elsewhere in the PR was moved, not rewritten.
        meaningful = [i for i in g.line_idx if len(js_strip(hunk.lines[i].text)) > 0]
        # (Block-level detection in find_moved_lines already covers braces and blank lines inside a moved block.)
        moved_share = (sum(1 for i in meaningful if f"{hunk.id}:{i}" in moved) / len(meaningful)) if meaningful else 0
        effect = r["effect"]
        if moved_share >= 0.8 and effect != "cosmetic":
            effect = "none"
        # Documentation can't change runtime behavior, whatever the model says.
        if file.category == "docs" and effect in ("behavior", "security"):
            effect = "cosmetic"
        changes_behavior = effect in ("behavior", "security") and file.category != "test"
        # A brand-new file can't alter existing behavior by itself; wiring it in shows up elsewhere.
        alters_existing = changes_behavior and file.status != "added"

        # Only "change" claims about this file's area can cover a change.
        covering = list(dict.fromkeys(cid for cid in r["covered_by"] if cid in by_id and by_id[cid].kind == "change" and in_area(by_id[cid].area, file.category)))
        # Changes to test files are what a claim like "adds regression tests" is about.
        if not covering and file.category == "test" and test_claim:
            covering = [test_claim.id]
        # A behavior change the author announced ("now tolerates undefined headers") doesn't break "no other behavior change".
        disclosed = any(by_id[cid].discloses_behavior for cid in covering)

        contradicts: Dict[str, None] = {}
        ruled: Dict[str, None] = {}  # violations established by code, not by the model
        for cid in r["violates"]:
            cl = by_id.get(cid)
            if cl is None:
                continue
            # Test code doesn't ship, so it can't break a promise about runtime behavior.
            if cl.limit == "no_behavior_change" and (not alters_existing or disclosed):
                continue
            contradicts[cid] = None
        for cl in claims:
            if cl.kind != "constraint":
                continue
            if cl.limit == "only_area" and not in_area(cl.area, file.category):
                contradicts[cl.id] = None
                ruled[cl.id] = None
            if cl.limit == "no_behavior_change" and alters_existing and not disclosed:
                contradicts[cl.id] = None
        # A claim can't both cover a change and be broken by it.
        claimed = [cid for cid in covering if cid not in contradicts]

        concern = r["concern"]
        if claimed and not contradicts:
            concern = "none"  # covered: nothing to flag
        minor = effect in ("none", "cosmetic") or file.category == "test"
        if minor and concern in ("medium", "high"):
            concern = "low"
        # Floors for anything that is unmentioned or breaks a promise; the model tends to under-rate these.
        if not claimed or contradicts:
            concern = max_concern(concern, "none" if (minor and not contradicts) else _effect_floor(effect, file.category))

        why = "" if concern == "none" else js_strip(r["why"])
        if not why and concern != "none":
            broken = [by_id[cid] for cid in contradicts]
            why = f"Breaks “{broken[0].text}”." if broken else "No claim in the description mentions this change."
        out.append(
            Change(
                id=f"{unit.id}.{len(out) + 1}",
                unit_id=unit.id,
                file=unit.file,
                hunk_id=unit.hunk_id,
                line_idx=g.line_idx,
                what=js_strip(r["what"]),
                effect=effect,
                claims=claimed,
                contradicts=list(contradicts),
                ruled_by=list(ruled),
                concern=concern,
                why=why,
                grounding=g.grounding,
                grounding_note=g.note,
                self_check=None,
            )
        )
    return out
