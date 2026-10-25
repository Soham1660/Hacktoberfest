from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .jsutil import collapse
from .models import DiffLine, FileDiff

_PUNCT = re.compile(r"^[\s{}()\[\];,]*$")
_BARE = re.compile(r"^(return|break|continue|else|try|finally|//|\*|/\*\*?|\*/)\W*$")


def _trivial(t: str) -> bool:
    """Lines too generic to say anything about where code went: braces, blank lines, `return;`…"""
    return len(t) < 8 or bool(_PUNCT.match(t)) or bool(_BARE.match(t))


def find_moved_lines(files: List[FileDiff]) -> Dict[str, str]:
    """Finds lines that a PR moves rather than writes: a removed line whose exact text
    (ignoring whitespace) is added in a different hunk, or the reverse. Like
    `git diff --color-moved`, this lets a reviewer of one excerpt know that code
    which looks deleted still exists elsewhere in the PR.

    Returns a map from `"{hunk_id}:{line_index}"` to the path of the file holding the counterpart.
    """
    Loc = Tuple[str, str]  # (hunk id, path)
    added: Dict[str, List[Loc]] = {}
    removed: Dict[str, List[Loc]] = {}
    for f in files:
        for h in f.hunks:
            for l in h.lines:
                if l.kind == "ctx":
                    continue
                t = collapse(l.text)
                if _trivial(t):
                    continue
                bucket = added if l.kind == "add" else removed
                bucket.setdefault(t, []).append((h.id, f.path))

    moved: Dict[str, str] = {}
    for f in files:
        for h in f.hunks:
            for idx, l in enumerate(h.lines):
                if l.kind == "ctx":
                    continue
                t = collapse(l.text)
                if _trivial(t):
                    continue
                locs = (removed if l.kind == "add" else added).get(t, [])
                counterpart = next((loc for loc in locs if loc[0] != h.id), None)
                if counterpart:
                    moved[f"{h.id}:{idx}"] = counterpart[1]

    # Block pass, like `git diff --color-moved`: inside a contiguous run of removed (or added)
    # lines that mostly moved, also mark the braces and blank lines, and lines that were only
    # lightly edited on the way (contained in a counterpart, e.g. a signature that gained
    # `export default`). A line with a changed value is never contained, so it stays unmarked.
    def soft_match(l: DiffLine, hunk_id: str) -> Optional[str]:
        t = collapse(l.text)
        if _trivial(t):
            return None
        for other, locs in (removed if l.kind == "add" else added).items():
            if len(other) < 12 or not (t in other or other in t):
                continue
            loc = next((x for x in locs if x[0] != hunk_id), None)
            if loc:
                return loc[1]
        return None

    for f in files:
        for h in f.hunks:
            i = 0
            while i < len(h.lines):
                kind = h.lines[i].kind
                if kind == "ctx":
                    i += 1
                    continue
                j = i
                while j < len(h.lines) and h.lines[j].kind == kind:
                    j += 1
                run = list(range(i, j))
                solid = [idx for idx in run if not _trivial(collapse(h.lines[idx].text))]
                match: Dict[int, Optional[str]] = {}
                for idx in solid:
                    match[idx] = moved.get(f"{h.id}:{idx}") or soft_match(h.lines[idx], h.id)
                hits = [p for p in match.values() if p]
                if len(solid) >= 3 and len(hits) / len(solid) >= 0.6:
                    target = _most_common(hits)
                    for idx in run:
                        key = f"{h.id}:{idx}"
                        if key in moved:
                            continue
                        if idx in match:
                            m = match[idx]
                            if m:
                                moved[key] = m
                        else:
                            moved[key] = target  # trivial line inside a moved block
                i = j
    return moved


def _most_common(xs: List[str]) -> str:
    counts: Dict[str, int] = {}
    for x in xs:
        counts[x] = counts.get(x, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])[0][0]
