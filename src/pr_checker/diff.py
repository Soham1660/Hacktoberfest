from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from .classify import classify_path, is_sensitive_path
from .jsutil import js_strip
from .models import DiffLine, FileDiff, Hunk

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$")
_GIT_HEADER = re.compile(r'^diff --git (?:"?a/(.+?)"?) (?:"?b/(.+?)"?)$')


def _strip_prefix(p: str) -> Optional[str]:
    trimmed = js_strip(p)
    if len(trimmed) >= 2 and trimmed.startswith('"') and trimmed.endswith('"'):
        trimmed = trimmed[1:-1]
    trimmed = trimmed.split("\t")[0]
    if trimmed == "/dev/null":
        return None
    return re.sub(r"^[ab]/", "", trimmed, count=1)


@dataclass
class _Draft:
    old_path: Optional[str] = None
    new_path: Optional[str] = None
    status: str = "modified"
    binary: bool = False
    hunks: List[Hunk] = field(default_factory=list)


def parse_unified_diff(text: str) -> List[FileDiff]:
    """Parses a unified diff (git or plain `diff -u` format) into files and hunks.

    Hunk bodies are consumed using the line counts from the @@ header, so removed
    lines that start with "--" are never mistaken for file headers.
    """
    lines = re.sub(r"\r\n?", "\n", text).split("\n")
    drafts: List[_Draft] = []
    cur: Optional[_Draft] = None
    i = 0

    def start_file() -> _Draft:
        nonlocal cur
        cur = _Draft()
        drafts.append(cur)
        return cur

    while i < len(lines):
        line = lines[i]

        if line.startswith("diff --git "):
            f = start_file()
            m = _GIT_HEADER.match(line)
            if m:
                f.old_path = m.group(1)
                f.new_path = m.group(2)
            i += 1
            continue

        if line.startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
            # Plain unified diffs have no "diff --git" line; start a file on the --- header.
            f = cur if cur is not None and len(cur.hunks) == 0 else start_file()
            old_p = _strip_prefix(line[4:])
            new_p = _strip_prefix(lines[i + 1][4:])
            f.old_path = old_p
            f.new_path = new_p
            if old_p is None:
                f.status = "added"
            elif new_p is None:
                f.status = "deleted"
            i += 2
            continue

        if cur is not None:
            f = cur
            if line.startswith("new file mode"):
                f.status = "added"
            elif line.startswith("deleted file mode"):
                f.status = "deleted"
            elif line.startswith("rename from "):
                f.status = "renamed"
                f.old_path = line[len("rename from "):]
            elif line.startswith("rename to "):
                f.status = "renamed"
                f.new_path = line[len("rename to "):]
            elif line.startswith("Binary files ") or line == "GIT binary patch":
                f.binary = True

            hm = _HUNK.match(line)
            if hm:
                old_start = int(hm.group(1))
                new_start = int(hm.group(3))
                old_left = 1 if hm.group(2) is None else int(hm.group(2))
                new_left = 1 if hm.group(4) is None else int(hm.group(4))
                hunk = Hunk(id="", header=line, section=js_strip(hm.group(5) or ""), old_start=old_start, new_start=new_start, lines=[])
                old_no = old_start
                new_no = new_start
                i += 1
                while i < len(lines) and (old_left > 0 or new_left > 0):
                    l = lines[i]
                    tag = l[:1]
                    if tag == "+":
                        dl = DiffLine("add", l[1:], None, new_no)
                        new_no += 1
                        new_left -= 1
                    elif tag == "-":
                        dl = DiffLine("del", l[1:], old_no, None)
                        old_no += 1
                        old_left -= 1
                    elif tag == " " or l == "":
                        # Some tools strip the leading space from blank context lines.
                        dl = DiffLine("ctx", l[1:], old_no, new_no)
                        old_no += 1
                        new_no += 1
                        old_left -= 1
                        new_left -= 1
                    elif tag == "\\":
                        i += 1
                        continue
                    else:
                        break  # malformed: header counts overstate the body
                    hunk.lines.append(dl)
                    i += 1
                while i < len(lines) and lines[i].startswith("\\"):
                    i += 1
                f.hunks.append(hunk)
                continue
        i += 1

    out: List[FileDiff] = []
    for d in (d for d in drafts if d.new_path or d.old_path):
        index = len(out)
        primary = d.old_path if d.status == "deleted" else d.new_path
        path = primary if primary is not None else (d.old_path if d.old_path is not None else "unknown")
        for hi, h in enumerate(d.hunks):
            h.id = f"F{index + 1}H{hi + 1}"
        additions = sum(1 for h in d.hunks for l in h.lines if l.kind == "add")
        deletions = sum(1 for h in d.hunks for l in h.lines if l.kind == "del")
        out.append(
            FileDiff(
                index=index,
                path=path,
                old_path=d.old_path if d.status == "renamed" else None,
                status=d.status,
                binary=d.binary,
                category=classify_path(path),
                sensitive=is_sensitive_path(path),
                additions=additions,
                deletions=deletions,
                hunks=d.hunks,
            )
        )
    return out


def changed_line_count(files: List[FileDiff]) -> int:
    return sum(f.additions + f.deletions for f in files)
