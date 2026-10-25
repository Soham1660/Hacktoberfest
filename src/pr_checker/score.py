from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cmp_to_key
from typing import Dict, List, Optional

from .jsutil import js_strip
from .models import Baseline, Change, Claim, ClaimResult, FileDiff, Finding, Report, Signal, Stats, Unit
from .status import change_status

RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}
_TEST_CLAIM = re.compile(r"\b(unit |integration |e2e )?tests?\b|\bspecs?\b|test coverage", re.I)


def max_concern(a: str, b: str) -> str:
    return a if RANK[a] >= RANK[b] else b


def self_check_mode(c: Change, signals: List[Signal]) -> Optional[str]:
    """Decides whether a change gets a second, skeptical model pass, and which kind:
    serious flags are re-examined, and so are "covered" changes that a static rule
    fired on or that the model itself called security-relevant."""
    if c.grounding == "failed":
        return None
    s = change_status(c)
    # Violations that code established (a change outside an "only docs" promise) are facts, not judgments.
    if s == "contradicts" and all(cid in c.ruled_by for cid in c.contradicts):
        return None
    if s in ("unexplained", "contradicts") and RANK[c.concern] >= RANK["medium"]:
        return "flag"
    if s == "explained" and (c.effect == "security" or rule_hits(c, signals)):
        return "coverage"
    return None


def rule_hits(c: Change, signals: List[Signal]) -> List[Signal]:
    """Warning or critical static signals on a change's lines."""
    return [s for s in signals if s.severity != "info" and s.hunk_id == c.hunk_id and s.line_index is not None and s.line_index in c.line_idx]


def _finding_severity(c: Change, status: str) -> str:
    if status == "retracted":
        return "none"
    o = c.self_check.outcome if c.self_check else None
    sev = c.self_check.severity if o in ("upheld", "overturned") else c.concern
    if sev == "none":
        sev = "low"  # flagged as undisclosed/contradicting, so never "none"
    if c.grounding == "failed" and RANK[sev] > RANK["low"]:
        sev = "low"  # can't point at the lines: don't escalate
    return sev


@dataclass
class ScoreInput:
    files: List[FileDiff]
    units: List[Unit]
    signals: List[Signal]
    claims: List[Claim]
    changes: List[Change]
    coverage: Dict[str, int]
    failed_units: int
    model_calls: int
    elapsed_ms: int


_HEADLINES = {
    "matches": "Does what it says",
    "undisclosed": "Makes changes it doesn't mention",
    "contradicts": "Contradicts its own description",
    "overclaims": "Claims more than it does",
    "trivial": "Trivial change",
    "incomplete": "Review incomplete",
}


def _finding_order(a: Finding, b: Finding) -> int:
    return (int(a.status == "retracted") - int(b.status == "retracted")) or (RANK[b.severity] - RANK[a.severity])


def build_report(inp: ScoreInput) -> Report:
    files, units, signals, claims, changes = inp.files, inp.units, inp.signals, inp.claims, inp.changes
    hunks = {h.id: h for f in files for h in f.hunks}
    category_of = {f.path: f.category for f in files}

    status_map: Dict[str, str] = {c.id: change_status(c) for c in changes}

    # Claims ledger.
    claim_results: List[ClaimResult] = []
    for cl in claims:
        live_changes = [c for c in changes if status_map[c.id] != "retracted"]
        if cl.kind == "constraint":
            breaking = [c for c in live_changes if cl.id in c.contradicts]
            claim_results.append(ClaimResult(**vars(cl), status="violated" if breaking else "held", change_ids=[c.id for c in breaking]))
            continue
        # Only changes that are actually explained count as evidence for a claim.
        supporting = [c for c in changes if cl.id in c.claims and status_map[c.id] == "explained"]
        # A claim about tests needs a change in a test file, whatever the model said.
        if _TEST_CLAIM.search(cl.text):
            supporting = [c for c in supporting if category_of.get(c.file) == "test"]
        claim_results.append(ClaimResult(**vars(cl), status="supported" if supporting else "not_found", change_ids=[c.id for c in supporting]))

    # Findings: flagged changes, including withdrawn ones so the self-check is visible.
    findings: List[Finding] = []
    for c in changes:
        status = status_map[c.id]
        if status in ("explained", "incidental"):
            continue
        hunk = hunks.get(c.hunk_id)
        first = hunk.lines[c.line_idx[0]] if hunk and c.line_idx else None
        sig_ids: List[str] = []
        for i in c.line_idx:
            for s in signals:
                if s.hunk_id == c.hunk_id and s.line_index == i and s.id not in sig_ids:
                    sig_ids.append(s.id)
        findings.append(
            Finding(
                change_id=c.id,
                status=status,
                severity=_finding_severity(c, status),
                file=c.file,
                hunk_id=c.hunk_id,
                first_line=(first.new_no if first.new_no is not None else first.old_no) if first else None,
                what=c.what,
                why=c.why,
                contradicts=c.contradicts,
                self_check_reason=c.self_check.reason if c.self_check else None,
                grounding=c.grounding,
                signal_ids=sig_ids,
            )
        )
    findings.sort(key=cmp_to_key(_finding_order))
    live = [f for f in findings if f.status != "retracted"]
    serious = [f for f in live if RANK[f.severity] >= RANK["medium"]]

    # Disclosure: how much of the behavior-changing code a claim accounts for.
    behavior_lines = 0
    covered_lines = 0
    for c in changes:
        if c.effect not in ("behavior", "security"):
            continue
        behavior_lines += len(c.line_idx)
        if status_map[c.id] in ("explained", "retracted"):
            covered_lines += len(c.line_idx)

    # Risk combines model findings with critical static signals.
    risk = "none"
    for f in live:
        risk = max_concern(risk, f.severity)
    if any(s.severity == "critical" for s in signals):
        risk = max_concern(risk, "high")

    model_units = sum(1 for u in units if u.mode == "model")
    not_found = [c for c in claim_results if c.status == "not_found"]
    violated = [c for c in claim_results if c.status == "violated"]
    any_behavior = any(c.effect in ("behavior", "security") for c in changes)
    meaningful_lines = sum(1 for f in files for h in f.hunks for l in h.lines if l.kind != "ctx" and js_strip(l.text))

    if model_units > 0 and inp.failed_units / model_units > 0.5:
        verdict = "incomplete"
    elif any(f.status == "contradicts" for f in serious):
        verdict = "contradicts"
    elif serious:
        verdict = "undisclosed"
    elif not_found:
        verdict = "overclaims"
    elif not any_behavior and meaningful_lines <= 12 and all(f.category in ("docs", "config") for f in files):
        verdict = "trivial"
    else:
        verdict = "matches"

    parts: List[str] = []
    n_changes = len(changes)
    unexplained = sum(1 for f in live if f.status == "unexplained")
    if verdict == "incomplete":
        parts.append(f"The model could not review {inp.failed_units} of {model_units} excerpts.")
    if violated:
        quoted = ", ".join(f"“{c.text}”" for c in violated)
        parts.append(
            f"{'The claim' if len(violated) == 1 else 'Claims'} {quoted} {'is' if len(violated) == 1 else 'are'} broken by {sum(len(c.change_ids) for c in violated)} change(s)."
        )
    if unexplained:
        parts.append(f"{unexplained} of {n_changes} changes aren't covered by any claim.")
    if not_found:
        parts.append(f"{len(not_found)} stated claim(s) have no matching change in the diff.")
    retracted = len(findings) - len(live)
    if retracted:
        parts.append(f"{retracted} flag(s) withdrawn on self-check.")
    if verdict == "matches":
        if live:
            parts.append(f"No serious issues: the {'one unmentioned change is' if len(live) == 1 else f'{len(live)} unmentioned changes are'} minor.")
        else:
            parts.append(f"All {n_changes} identified changes trace back to the description.")
    if verdict == "trivial":
        parts.append(f"Only {meaningful_lines} meaningful line(s) changed, with no effect on behavior.")

    sev = [s for s in signals if s.severity != "info"]
    sev_ids = {s.id for s in sev}
    return Report(
        verdict=verdict,
        headline=_HEADLINES[verdict],
        summary=" ".join(parts),
        risk=risk,
        disclosure=(covered_lines / behavior_lines) if behavior_lines else None,
        line_coverage=(inp.coverage["cited"] / inp.coverage["changed"]) if inp.coverage["changed"] else 1,
        change_status=status_map,
        claims=claim_results,
        findings=findings,
        baseline=Baseline(
            signals=len(signals),
            warn_or_critical=len(sev),
            findings_missed_by_rules=sum(1 for f in serious if not any(i in sev_ids for i in f.signal_ids)),
        ),
        stats=Stats(
            files=len(files),
            additions=sum(f.additions for f in files),
            deletions=sum(f.deletions for f in files),
            units=len(units),
            model_units=model_units,
            failed_units=inp.failed_units,
            model_calls=inp.model_calls,
            elapsed_ms=inp.elapsed_ms,
        ),
    )
