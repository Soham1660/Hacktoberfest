"""Types shared by the API server and the web client.

Everything that crosses the wire is serialized by `to_json`, which renders snake_case
field names as the camelCase the web client reads (`old_no` -> `oldNo`).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Literal-like aliases, kept as plain str for readability:
#   LineKind      "add" | "del" | "ctx"
#   FileStatus    "added" | "deleted" | "modified" | "renamed"
#   FileCategory  "source" | "test" | "docs" | "ci" | "build" | "manifest" | "lockfile" | "config" | "asset"
#   Severity      "info" | "warn" | "critical"
#   UnitMode      "model" | "whitespace" | "lockfile" | "binary" | "skipped"
#   ClaimKind     "change" | "constraint"
#   ClaimArea     "docs" | "tests" | "ci" | "build" | "dependencies" | "code" | "any"
#   ClaimLimit    "no_behavior_change" | "only_area" | "other"
#   Effect        "none" | "cosmetic" | "behavior" | "security"
#   Concern       "none" | "low" | "medium" | "high"
#   Grounding     "verified" | "partial" | "failed"
#   ChangeStatus  "explained" | "incidental" | "unexplained" | "contradicts" | "retracted"
#   ClaimStatus   "supported" | "not_found" | "held" | "violated"
#   Verdict       "matches" | "undisclosed" | "contradicts" | "overclaims" | "trivial" | "incomplete"


@dataclass
class DiffLine:
    kind: str
    text: str
    old_no: Optional[int]
    new_no: Optional[int]


@dataclass
class Hunk:
    id: str
    header: str
    section: str
    old_start: int
    new_start: int
    lines: List[DiffLine] = field(default_factory=list)


@dataclass
class FileDiff:
    index: int
    path: str
    old_path: Optional[str]
    status: str
    binary: bool
    category: str
    sensitive: bool
    additions: int
    deletions: int
    hunks: List[Hunk]


@dataclass
class Signal:
    id: str
    rule: str
    title: str
    severity: str
    detail: str
    file: str
    hunk_id: Optional[str]
    line_index: Optional[int]  # index into hunk.lines


@dataclass
class Unit:
    """A slice of one hunk that the model reviews in a single call."""

    id: str
    file: str
    file_index: int
    hunk_id: str
    line_idx: List[int]  # indices into hunk.lines, in order. Unit line Lk = line_idx[k-1].
    mode: str
    note: Optional[str]


@dataclass
class Claim:
    id: str  # C1, C2…
    text: str
    kind: str
    area: str
    limit: str
    discloses_behavior: bool  # for change claims: the author says this change alters behavior


@dataclass
class SelfCheck:
    """Result of the second, skeptical model pass.

    "flag" mode re-examines a change flagged as unmentioned or contradicting: upheld or withdrawn.
    "coverage" mode re-examines a change the model called covered although a static rule fired
    on it or it is security-relevant: confirmed or overturned.
    """

    mode: str
    outcome: str
    severity: str
    reason: str
    claims_before: List[str]


@dataclass
class Change:
    """One atomic change the model identified inside a unit."""

    id: str  # U3.1
    unit_id: str
    file: str
    hunk_id: str
    line_idx: List[int]  # indices into hunk.lines the model cited (validated)
    what: str
    effect: str
    claims: List[str]
    contradicts: List[str]
    ruled_by: List[str]  # subset of `contradicts` established by deterministic rules
    concern: str
    why: str
    grounding: str
    grounding_note: Optional[str]
    self_check: Optional[SelfCheck]


@dataclass
class ClaimResult(Claim):
    status: str = "held"
    change_ids: List[str] = field(default_factory=list)


@dataclass
class Finding:
    change_id: str
    status: str
    severity: str
    file: str
    hunk_id: str
    first_line: Optional[int]
    what: str
    why: str
    contradicts: List[str]
    self_check_reason: Optional[str]
    grounding: str
    signal_ids: List[str]  # static-rule signals that fire on the same lines


@dataclass
class Baseline:
    signals: int
    warn_or_critical: int
    findings_missed_by_rules: int  # confirmed model findings whose lines no static rule flagged


@dataclass
class Stats:
    files: int
    additions: int
    deletions: int
    units: int
    model_units: int
    failed_units: int
    model_calls: int
    elapsed_ms: int


@dataclass
class Report:
    verdict: str
    headline: str
    summary: str
    risk: str
    disclosure: Optional[float]  # share of behavior-changing lines covered by a claim, 0..1
    line_coverage: float  # share of changed lines (in model-reviewed units) cited by the model
    change_status: Dict[str, str]
    claims: List[ClaimResult]
    findings: List[Finding]
    baseline: Baseline
    stats: Stats


@dataclass
class ParsedPayload:
    files: List[FileDiff]
    units: List[Unit]
    signals: List[Signal]
    truncated: bool


@dataclass
class Health:
    ok: bool
    ollama: bool
    host: str
    model: str
    claims_model: str
    model_installed: bool
    claims_model_installed: bool
    message: Optional[str]


@dataclass
class PullRequestInput:
    title: str
    description: str
    diff: str
    source: Optional[str] = None


@dataclass
class SampleSummary:
    id: str
    title: str
    repo: str
    hint: str


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(p[:1].upper() + p[1:] for p in rest)


def to_json(obj: Any) -> Any:
    """Converts dataclasses (recursively) to plain dicts with camelCase keys, ready for json.dumps."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {_camel(f.name): to_json(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {k: to_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json(v) for v in obj]
    return obj
