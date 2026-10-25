from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from .jsutil import js_strip
from .models import Hunk, Unit

_REF = re.compile(r"L?(\d+)(?:\s*(?:-|–|to)\s*L?(\d+))?", re.I)


def parse_line_refs(refs: str) -> List[int]:
    """Parses line references like "3-7, 9, L12" into a list of line numbers."""
    out: List[int] = []
    for m in _REF.finditer(refs):
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        if b < a or b - a > 200:
            continue
        out.extend(range(a, b + 1))
    return out


@dataclass
class GroundedLines:
    line_idx: List[int]
    grounding: str
    note: Optional[str]


def ground_citations(lines: List[int], unit: Unit, hunk: Hunk) -> GroundedLines:
    """Maps the model's L-number citations back to real diff lines and checks them.

    A citation is valid only if it exists in the excerpt and points at an added
    or removed line. Context lines and out-of-range numbers are dropped.
    """
    valid: List[int] = []
    out_of_range = 0
    context = 0
    for l in dict.fromkeys(lines):
        if l < 1 or l > len(unit.line_idx):
            out_of_range += 1
            continue
        idx = unit.line_idx[l - 1]
        if hunk.lines[idx].kind == "ctx":
            context += 1
        else:
            valid.append(idx)
    valid.sort()
    problems = [p for p in (f"{out_of_range} citation(s) outside the excerpt" if out_of_range else "", f"{context} citation(s) of unchanged lines" if context else "") if p]
    grounding = "failed" if not valid else ("partial" if problems else "verified")
    return GroundedLines(valid, grounding, "; ".join(problems) if problems else None)


def citation_coverage(unit: Unit, hunk: Hunk, cited: Iterable[int]) -> Dict[str, int]:
    """Share of changed lines in an excerpt that at least one change cites."""
    cited_set = set(cited)
    changed = 0
    hit = 0
    for idx in unit.line_idx:
        l = hunk.lines[idx]
        if l.kind == "ctx" or js_strip(l.text) == "":
            continue
        changed += 1
        if idx in cited_set:
            hit += 1
    return {"changed": changed, "cited": hit}
