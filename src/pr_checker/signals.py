from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, List, Optional

from .jsutil import js_strip
from .models import FileDiff, Signal

# Deterministic, pattern-based rules. They are the "static baseline" that the model's
# findings are compared against, and they feed the model as hints. Rules only look at
# lines a PR adds, except where noted.


@dataclass
class LineRule:
    rule: str
    title: str
    severity: str
    on: str  # "add" | "del"
    test: Callable[[str], Optional[str]]  # returns a short detail when the rule fires
    files: Optional[Callable[[FileDiff], bool]] = None


def _match(pattern: str, flags: int = 0) -> Callable[[str], Optional[str]]:
    rx = re.compile(pattern, flags)

    def test(t: str) -> Optional[str]:
        m = rx.search(t)
        return js_strip(m.group(0))[:80] if m else None

    return test


_SAFE_HOSTS = re.compile(
    r"^(localhost|127\.0\.0\.1|0\.0\.0\.0|example\.(com|org)|.*\.example\.com|schemas\.|www\.w3\.org|json-schema\.org|github\.com|docs\.)"
)
_HIDDEN = re.compile("[\u202a-\u202e\u2066-\u2069]|(?<=\\S)[\u200b-\u200d\u2060\ufeff]")
_BLOB = re.compile(r"""['"`][A-Za-z0-9+/]{120,}={0,2}['"`]|['"`](?:[0-9a-fA-F]{2}){80,}['"`]""")
_URL = re.compile(r"\bhttps?://([a-z0-9.-]+)", re.I)
_IP = re.compile(r"\b((?:[0-9]{1,3}\.){3}[0-9]{1,3})\b")
_PRIVATE_IP = re.compile(r"^(127\.|0\.0\.0\.0|10\.|192\.168\.)")
_ACTION = re.compile(r"uses:\s*([\w.-]+/[\w./-]+)@([\w.-]+)")
_SHA = re.compile(r"^[0-9a-f]{40}$")


def _hidden_unicode(t: str) -> Optional[str]:
    m = _HIDDEN.search(t)
    return f"U+{ord(m.group(0)[0]):04X}" if m else None


def _encoded_blob(t: str) -> Optional[str]:
    return "long base64/hex literal" if _BLOB.search(t) else None


def _unpinned_action(t: str) -> Optional[str]:
    m = _ACTION.search(t)
    if not m or _SHA.match(m.group(2)) or m.group(1).startswith("actions/"):
        return None
    return f"{m.group(1)}@{m.group(2)}"


def _network_endpoint(t: str) -> Optional[str]:
    url = _URL.search(t)
    if url and not _SAFE_HOSTS.match(url.group(1).lower()):
        return url.group(1)
    ip = _IP.search(t)
    if ip and not _PRIVATE_IP.match(ip.group(1)) and all(int(o) < 256 for o in ip.group(1).split(".")):
        return ip.group(1)
    return None


def _minified(t: str) -> Optional[str]:
    return f"{len(t)} characters" if len(t) > 400 else None


def _is(category: str) -> Callable[[FileDiff], bool]:
    return lambda f: f.category == category


LINE_RULES: List[LineRule] = [
    LineRule(
        "pipe-to-shell", "Downloads and pipes into a shell", "critical", "add",
        _match(r"\b(curl|wget|iwr|Invoke-WebRequest)\b[^\n|]*\|\s*(sudo\s+)?(ba|z|da)?sh\b", re.I),
    ),
    LineRule("hidden-unicode", "Invisible or bidirectional Unicode characters", "critical", "add", _hidden_unicode),
    LineRule(
        "secret-literal", "Looks like a credential", "critical", "add",
        _match(r"(AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{36}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|xox[baprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9]{32,})"),
    ),
    LineRule(
        "install-hook", "Adds a package install hook", "warn", "add",
        _match(r'"(pre|post)?install"\s*:\s*"[^"]*"|cmdclass\s*='),
        files=_is("manifest"),
    ),
    LineRule(
        "runtime-decode", "Decodes encoded data at runtime", "warn", "add",
        _match(r"""Buffer\.from\([^)]*['"](base64|hex)['"]\)|\batob\(|b64decode\(|base64\s+(-d|--decode)|fromCharCode\(\s*\d+\s*,\s*\d+"""),
    ),
    LineRule("encoded-blob", "Long encoded string literal", "warn", "add", _encoded_blob),
    LineRule(
        "dynamic-exec", "Executes code or commands dynamically", "warn", "add",
        _match(r"\beval\s*\(|new Function\s*\(|\bchild_process\b|\bexecSync\s*\(|\bspawn\s*\(|\bos\.system\s*\(|\bsubprocess\.(run|Popen|call)\b|Runtime\.getRuntime\(\)\.exec"),
    ),
    LineRule(
        "env-harvest", "Uses the whole environment as a value", "warn", "add",
        # process.env passed or serialized as a whole (not one variable like process.env.NODE_ENV)
        _match(r"(?<![\w.])process\.env\s*(?=[,)}\];]|$)|\.\.\.process\.env\b|os\.environ\.copy\(\)|dict\(os\.environ\)|json\.dumps\(\s*os\.environ"),
    ),
    LineRule(
        "tls-disabled", "Disables TLS certificate checks", "critical", "add",
        _match(r"rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED|verify\s*=\s*False|InsecureSkipVerify\s*:\s*true|--insecure\b|-k\s+https?:"),
    ),
    LineRule("ci-privileged-trigger", "Privileged CI trigger", "warn", "add", _match(r"\bpull_request_target\b|\bworkflow_run\b"), files=_is("ci")),
    LineRule(
        "ci-untrusted-checkout", "Checks out code from the PR author's branch", "warn", "add",
        _match(r"github\.event\.pull_request\.head\.(sha|ref)|github\.head_ref"),
        files=_is("ci"),
    ),
    LineRule("ci-secret", "Exposes a CI secret to a step", "warn", "add", _match(r"\$\{\{\s*secrets\.[A-Za-z0-9_]+\s*\}\}"), files=_is("ci")),
    LineRule(
        "ci-write-permissions", "Broad CI token permissions", "warn", "add",
        _match(r"permissions\s*:\s*write-all|\b(contents|packages|id-token|actions)\s*:\s*write\b"),
        files=_is("ci"),
    ),
    LineRule("unpinned-action", "Third-party action not pinned to a commit", "info", "add", _unpinned_action, files=_is("ci")),
    LineRule("network-endpoint", "New network endpoint", "info", "add", _network_endpoint),
    LineRule("world-writable", "Grants broad file permissions", "warn", "add", _match(r"chmod\s+(-R\s+)?(777|666|a\+w|o\+w)\b|0o?777\b")),
    LineRule("minified-line", "Very long added line", "info", "add", _minified),
    LineRule(
        "guard-removed", "Removes a check or guard", "info", "del",
        _match(
            r"""\bif\s*\(.*\b(auth|permission|isAdmin|role|verify|valid|allowed|csrf|token)\w*|\bassert\w*\s*\(|\bthrow new \w*(Auth|Permission|Forbidden|Unauthori)|\braise \w*(Permission|Auth)|\b(httpOnly|secure|sameSite)\s*:\s*(true|['"]strict['"])""",
            re.I,
        ),
    ),
]


def scan_signals(files: List[FileDiff]) -> List[Signal]:
    out: List[Signal] = []

    def push(**kw) -> None:
        out.append(Signal(id=f"S{len(out) + 1}", **kw))

    for f in files:
        for h in f.hunks:
            for idx, l in enumerate(h.lines):
                if l.kind == "ctx":
                    continue
                for r in LINE_RULES:
                    if r.on != l.kind:
                        continue
                    if r.files and not r.files(f):
                        continue
                    detail = r.test(l.text)
                    if detail:
                        push(rule=r.rule, title=r.title, severity=r.severity, detail=detail, file=f.path, hunk_id=h.id, line_index=idx)

        if f.binary and f.category != "asset":
            push(rule="binary-file", title="Binary file outside assets", severity="warn", detail=f.status, file=f.path, hunk_id=None, line_index=None)

    # Lockfile changed while no manifest did: a classic way to slip in a dependency.
    lockfiles = [f for f in files if f.category == "lockfile"]
    if lockfiles and not any(f.category == "manifest" for f in files):
        for f in lockfiles:
            push(
                rule="lockfile-only",
                title="Lockfile changed without a manifest change",
                severity="warn",
                detail=f"{f.additions + f.deletions} lines",
                file=f.path,
                hunk_id=None,
                line_index=None,
            )

    return out
