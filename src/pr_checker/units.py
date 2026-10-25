from __future__ import annotations

from typing import Dict, List, Tuple

from .jsutil import squash
from .models import FileDiff, Hunk, Unit

LIMITS: Dict[str, int] = {
    "max_diff_bytes": 600_000,
    "max_model_units": 40,
    "max_unit_lines": 70,
    "context_around": 3,
}


def is_whitespace_only(h: Hunk) -> bool:
    """True when a hunk only changes whitespace: same tokens added as removed."""
    added = [s for s in (squash(l.text) for l in h.lines if l.kind == "add") if s]
    removed = [s for s in (squash(l.text) for l in h.lines if l.kind == "del") if s]
    if not added and not removed:
        return any(l.kind != "ctx" for l in h.lines)
    return "\n".join(added) == "\n".join(removed)


def window_hunk(h: Hunk, max_lines: int = LIMITS["max_unit_lines"]) -> List[List[int]]:
    """Splits a hunk's lines into windows the model can review in one call.

    Each window holds at most `max_lines` lines, and window boundaries fall
    on context lines where possible so a change is not cut in half.
    """
    # Trim long context runs so prompts stay small: keep `context_around` lines near changes.
    n = len(h.lines)
    around = LIMITS["context_around"]
    changed = [l.kind != "ctx" for l in h.lines]
    keep: List[int] = []
    for i in range(n):
        lo = max(0, i - around)
        hi = min(n - 1, i + around)
        if any(changed[j] for j in range(lo, hi + 1)):
            keep.append(i)
    if len(keep) <= max_lines:
        return [keep]

    windows: List[List[int]] = []
    cur: List[int] = []
    for idx in keep:
        cur.append(idx)
        at_break = h.lines[idx].kind == "ctx"
        if len(cur) >= max_lines or (len(cur) >= max_lines * 0.75 and at_break):
            windows.append(cur)
            cur = []
    if cur:
        windows.append(cur)
    return windows


def build_units(files: List[FileDiff]) -> Tuple[List[Unit], bool]:
    units: List[Unit] = []
    model_units = 0
    truncated = False
    n = 0

    def add(file: FileDiff, hunk_id: str, line_idx: List[int], mode: str, note) -> None:
        nonlocal n
        n += 1
        units.append(Unit(id=f"U{n}", file=file.path, file_index=file.index, hunk_id=hunk_id, line_idx=line_idx, mode=mode, note=note))

    for f in files:
        if f.binary:
            add(f, "", [], "binary", "Binary file: content not reviewable")
            continue
        for h in f.hunks:
            every = list(range(len(h.lines)))
            if f.category == "lockfile":
                add(f, h.id, every, "lockfile", "Generated lockfile: checked by static rules only")
                continue
            if is_whitespace_only(h):
                add(f, h.id, every, "whitespace", "Whitespace-only change")
                continue
            for w in window_hunk(h):
                if model_units >= LIMITS["max_model_units"]:
                    truncated = True
                    add(f, h.id, w, "skipped", f"Over the {LIMITS['max_model_units']}-excerpt review limit")
                    continue
                model_units += 1
                add(f, h.id, w, "model", None)
    return units, truncated
