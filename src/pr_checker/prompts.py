"""Prompts and output schemas for the four model calls: claims, review, self-check, review comment."""
from __future__ import annotations

from typing import Dict, List

from .models import Claim, FileDiff, Hunk, Signal, Unit
from .schema import Arr, Bool, Enum, Node, Obj, Str

# ---------- Stage A: claim extraction ----------

CLAIMS_SYSTEM = """You extract the claims a pull-request author makes about their own change.

Rules:
- Use ONLY the title and description. Never guess what the code does, and never invent claims the author did not state or clearly imply.
- One claim per distinct statement; merge near-duplicates ("pure refactor" and "no behavior change" are one constraint). At most 6 claims, each under 14 words.
- kind "change": something the PR says it adds, fixes, removes, moves, refactors, or tests.
- kind "constraint": an explicit promise that limits scope or says what does NOT change, e.g. "no behavior change", "docs only", "no new dependencies", "backwards compatible".
- Always include the main change itself as a "change" claim, e.g. "Fixes the typo 'recieve' -> 'receive' in the README".
- A narrow title ALSO implies a scope constraint: "Fix typo in README" implies "Only fixes a typo in the README"; "docs: ..." implies "Only changes documentation". Other prefixes like "ci:" or "feat:" do not.
- Ignore greetings, thanks, issue references ("Closes #12"), emoji, and checklist boilerplate. They are never claims.
- area: the part of the codebase the claim is about: "docs" (README, guides, comments in docs), "tests", "ci" (CI workflows), "build" (build or install scripts), "dependencies" (package manifests, lockfiles), "code" (application source, styles, config), or "any" when it is not limited.
- discloses_behavior (change claims): true when the claim says runtime behavior changes (a bug fix, a new feature or option, different output, now tolerates or rejects something); false for moves, renames, refactors, docs, and tests. Always false for constraints.
- limit (constraints only; use "other" for change claims): "no_behavior_change" for promises like "pure refactor" or "no functional change"; "only_area" when the PR promises to touch only that area ("only fixes a typo in the README" -> area "docs", limit "only_area"); otherwise "other".
Respond with compact JSON."""

CLAIMS_SCHEMA: Node = Obj(
    {
        "claims": Arr(
            Obj(
                {
                    "text": Str(min=2, max=200),
                    "kind": Enum(["change", "constraint"]),
                    "area": Enum(["docs", "tests", "ci", "build", "dependencies", "code", "any"]),
                    "limit": Enum(["no_behavior_change", "only_area", "other"]),
                    "discloses_behavior": Bool(),
                }
            ),
            max=6,
        )
    }
)


def claims_user(title: str, description: str) -> str:
    return f"TITLE: {title.strip() or '(none)'}\n\nDESCRIPTION:\n{description.strip() or '(empty)'}"


# ---------- Stage B: per-excerpt review ----------

REVIEW_SYSTEM = """You are a meticulous code reviewer checking whether a pull request does what its author says.
You get the author's claims and ONE excerpt of the diff. Lines are labeled L1, L2, ...; "+" added, "-" removed, " " unchanged context.

Split the excerpt into its distinct atomic changes:
- A modified line shows up as a "-" line and a "+" line; together they are ONE change.
- Give every changed value, flag, option, or condition its own change. Never bury one inside a larger change like "remove helpers" or "move code".
- Every added or removed line belongs to exactly one change.
- In a newly added file, group lines by purpose (usually 1-4 changes), but still separate anything that sends data, runs commands, reads secrets, or decodes hidden values.

For each change:
- lines: its added/removed lines as L-number ranges, e.g. "3-5, 9".
- what: at most 14 words, concrete. Name identifiers and old -> new values, quoting expressions exactly as written (never compute arithmetic), and state the most consequential effect (e.g. what data is sent where, what now runs, what got weaker).
- effect:
  "none" = code moved, renamed, or re-imported with identical behavior, or a NEW helper, file, or test that existing code paths don't depend on yet
  "cosmetic" = formatting, comments, documentation text
  "behavior" = existing runtime behavior changes: values, logic, defaults, conditions, calls
  "security" = a behavior change touching auth, sessions, cookies, tokens, secrets, permissions, crypto, network calls, install scripts, CI execution, or data exposure
- covered_by: the one claim (at most two) whose text directly describes this change. Test: if a careful maintainer read only the claims, would they expect this specific change? If they would want it mentioned separately, it is NOT covered. Never cover a change with a claim about a different purpose (a caching claim does not cover a trigger or permission change). Leave empty when unsure.
- violates: ids of claims this change breaks. "No behavior change" is broken only by effect "behavior" or "security"; new tests, new helpers, and moved code never break it. A narrow scope claim like "only fixes a typo" is broken by anything outside that scope.
- concern: "none" if covered and harmless. Otherwise how much a maintainer should worry: "low", "medium", or "high" (an undisclosed security change, or an undisclosed change to important behavior).
- why: one short sentence (at most 15 words) when concern is not "none", else "".

Static-rule hints, when present, are leads to verify, not conclusions. Respond with compact JSON."""


def review_schema(change_claim_ids: List[str], all_claim_ids: List[str]) -> Node:
    def ids(values: List[str], max: int) -> Node:
        return Arr(Enum(values), max=max) if values else Arr(Str(), max=0)

    return Obj(
        {
            "changes": Arr(
                Obj(
                    {
                        "lines": Str(min=1, max=120),
                        "what": Str(max=240),
                        "effect": Enum(["none", "cosmetic", "behavior", "security"]),
                        "covered_by": ids(change_claim_ids, 2),
                        "violates": ids(all_claim_ids, 4),
                        "concern": Enum(["none", "low", "medium", "high"]),
                        "why": Str(max=300),
                    }
                ),
                min=1,
                max=8,
            )
        }
    )


_MARK = {"add": "+", "del": "-", "ctx": " "}


def _moved_lines(hunk: Hunk, unit: Unit, moved: Dict[str, str]) -> List[str]:
    """Hint lines telling the model which excerpt lines were moved from or to another file."""
    here: Dict[str, List[int]] = {}
    for k, idx in enumerate(unit.line_idx):
        other = moved.get(f"{hunk.id}:{idx}")
        if other:
            here.setdefault(other, []).append(k + 1)
    return [f"- {_format_ranges(ls)} also appear in {path}: this code was moved there (or from there), which by itself does not change behavior." for path, ls in here.items()]


def _format_ranges(ls: List[int]) -> str:
    """[3,4,5,9] -> "L3-L5, L9" """
    out: List[str] = []
    i = 0
    while i < len(ls):
        j = i
        while j + 1 < len(ls) and ls[j + 1] == ls[j] + 1:
            j += 1
        out.append(f"L{ls[i]}" if i == j else f"L{ls[i]}-L{ls[j]}")
        i = j + 1
    return ", ".join(out)


def format_claims(claims: List[Claim]) -> str:
    if not claims:
        return "(The author made no claims. Treat every behavior change as undisclosed.)"
    return "\n".join(f"{c.id} [{c.kind}, {c.area}{', announces a behavior change' if c.discloses_behavior else ''}]: {c.text}" for c in claims)


def format_excerpt(hunk: Hunk, unit: Unit) -> str:
    rows = []
    for k, idx in enumerate(unit.line_idx):
        l = hunk.lines[idx]
        rows.append(f"L{k + 1} {_MARK[l.kind]} {l.text}")
    return "\n".join(rows)


def review_user(claims: List[Claim], file: FileDiff, hunk: Hunk, unit: Unit, signals: List[Signal], moved: Dict[str, str] = None) -> str:
    moved = moved or {}
    flags = ", ".join(x for x in (file.category, "sensitive path" if file.sensitive else None, file.status) if x)
    hints = [
        f"- L{unit.line_idx.index(s.line_index) + 1}: {s.title} ({s.detail})"
        for s in signals
        if s.hunk_id == hunk.id and s.line_index is not None and s.line_index in unit.line_idx
    ]
    moved_hints = _moved_lines(hunk, unit, moved)
    parts = [
        "CLAIMS",
        format_claims(claims),
        "",
        f"FILE {file.path} ({flags})" + (f"\nENCLOSING SCOPE {hunk.section}" if hunk.section else ""),
        "STATIC-RULE HINTS\n" + "\n".join(hints) if hints else "",
        "MOVED CODE\n" + "\n".join(moved_hints) if moved_hints else "",
        "",
        "EXCERPT",
        format_excerpt(hunk, unit),
    ]
    # Drop empty sections, but keep single blank separators.
    kept = [s for i, s in enumerate(parts) if s != "" or (i > 0 and parts[i - 1] != "")]
    return "\n".join(kept)


# ---------- Stage C: skeptical self-check ----------

VERIFY_SYSTEM = """You are a second reviewer double-checking a colleague's judgments about changes in one excerpt of a pull request.
For each judgment, first give your reason, then decide: "colleague_is_right" or "colleague_is_wrong".
Facts to apply:
- Moving code, re-importing it, deleting a helper that now lives elsewhere, and adding a new helper or test do NOT change behavior.
- Changing a value, default, condition, cookie flag, trigger, permission, secret, network destination, or what data is sent DOES change behavior.
- A claim covers a change only if a careful maintainer reading the claim would expect that specific change. A claim about one purpose (e.g. caching, a typo) does not cover security-relevant changes for another purpose.
- severity: how much a maintainer should care if the colleague's flag stands, or if the change turns out NOT to be covered.
Reason in one sentence of at most 20 words. Respond with compact JSON."""


class VerifyItem:
    """One judgment to double-check."""

    def __init__(self, key: str, lines: List[int], what: str, judgment: str):
        self.key = key  # K1, K2…
        self.lines = lines
        self.what = what
        self.judgment = judgment  # what the colleague concluded, phrased as a statement


def verify_schema(keys: List[str]) -> Node:
    return Obj(
        {
            "verdicts": Arr(
                Obj(
                    {
                        "key": Enum(keys),
                        "reason": Str(max=300),
                        "decision": Enum(["colleague_is_right", "colleague_is_wrong"]),
                        "severity": Enum(["low", "medium", "high"]),
                    }
                ),
                min=1,
                max=len(keys),
            )
        }
    )


def verify_user(claims: List[Claim], file: FileDiff, hunk: Hunk, unit: Unit, items: List[VerifyItem], moved: Dict[str, str] = None) -> str:
    moved = moved or {}
    moved_hints = _moved_lines(hunk, unit, moved)
    return "\n".join(
        [
            "CLAIMS",
            format_claims(claims),
            "",
            f"FILE {file.path} ({file.status})",
            *(["MOVED CODE", *moved_hints] if moved_hints else []),
            "EXCERPT",
            format_excerpt(hunk, unit),
            "",
            "JUDGMENTS TO CHECK",
            *[f"{it.key} (lines {', '.join(f'L{l}' for l in it.lines)}): {it.what}\n   Colleague: {it.judgment}" for it in items],
        ]
    )


# ---------- Stage D: maintainer review comment ----------

COMMENT_SYSTEM = """You draft a GitHub pull-request review comment for an open-source maintainer.
Write in plain, courteous, direct language. Use GitHub Markdown.
Start with one sentence acknowledging what the PR does well or does as described.
Then list each finding as a bullet: `file:line`, what the change does, and a specific question asking the author to explain it, move it to a separate PR, or revert it.
If a stated claim was not found in the diff, ask about it.
Use only the facts given. No speculation about intent, no accusations, no headings, under 160 words."""
