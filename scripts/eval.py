"""Runs the real pipeline (live model calls) over the bundled samples and scores
it against the planted ground truth, next to the static-rule baseline.

    python scripts/eval.py                 # all samples
    python scripts/eval.py dark-mode       # one sample, verbose

Results are written to eval/results.json, which the UI shows on its About panel.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any, Dict, List

from pr_checker.config import ROOT, config
from pr_checker.jsutil import iso_now
from pr_checker.models import PullRequestInput
from pr_checker.pipeline import run_analysis
from pr_checker.samples import load_samples

RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


async def main() -> None:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    verbose = bool(only)
    results: List[Dict[str, Any]] = []

    for s in (x for x in load_samples() if not only or x["id"] == only):
        files: List[Any] = []
        signals: List[Any] = []
        claims: List[Any] = []
        changes: List[Any] = []
        report = None
        error = None

        def emit(e: Dict[str, Any]) -> None:
            nonlocal files, signals, claims, report, error
            t = e["type"]
            if t == "parsed":
                files, signals = e["data"]["files"], e["data"]["signals"]
            elif t == "claims":
                claims = e["claims"]
            elif t == "unit_result":
                changes.extend(e["changes"])
            elif t == "unit_error":
                print(f"  ! {e['unitId']}: {e['message']}", file=sys.stderr)
            elif t == "verify_result":
                for i, x in enumerate(changes):
                    if x.id == e["changeId"]:
                        changes[i] = e["change"]
                        break
            elif t == "report":
                report = e["report"]
            elif t == "error":
                error = e["message"]

        print(f"\n▸ {s['id']}  “{s['title']}”")
        t0 = time.time()
        try:
            await run_analysis(PullRequestInput(s["title"], s["description"], s["diff"]), emit)
        except Exception as err:
            error = str(err)
        if error or not report:
            print(f"  ERROR {error}")
            results.append({"id": s["id"], "error": error})
            continue
        r = report

        def line_text(file: str, hunk_id: str, idx: int) -> str:
            f = next((f for f in files if f.path == file), None)
            h = next((h for h in f.hunks if h.id == hunk_id), None) if f else None
            return h.lines[idx].text if h and 0 <= idx < len(h.lines) else ""

        flagged = [f for f in r.findings if f.status != "retracted" and RANK[f.severity] >= RANK["medium"]]
        flagged_changes = [next(c for c in changes if c.id == f.change_id) for f in flagged]

        planted = []
        for p in s["expect"]["planted"]:
            model = any(c.file == p["file"] and any(p["needle"] in line_text(c.file, c.hunk_id, i) for i in c.line_idx) for c in flagged_changes)
            rule_hits = [
                sg
                for sg in signals
                if sg.file == p["file"] and sg.hunk_id is not None and sg.line_index is not None and p["needle"] in line_text(sg.file, sg.hunk_id, sg.line_index)
            ]
            planted.append({**p, "model": model, "rulesAny": bool(rule_hits), "rulesWarn": any(h.severity != "info" for h in rule_hits)})

        # A flag is a false positive when none of its lines contain a planted needle and its file isn't wholly undisclosed.
        undisclosed = s["expect"].get("undisclosedFiles") or []
        false_flags = [
            c
            for c in flagged_changes
            if c.file not in undisclosed
            and not any(c.file == p["file"] and any(p["needle"] in line_text(c.file, c.hunk_id, i) for i in c.line_idx) for p in s["expect"]["planted"])
        ]

        row = {
            "id": s["id"],
            "verdict": r.verdict,
            "expectedVerdict": s["expect"]["verdict"],
            "verdictOk": r.verdict == s["expect"]["verdict"],
            "planted": len(planted),
            "caughtByModel": sum(1 for p in planted if p["model"]),
            "caughtByRulesWarn": sum(1 for p in planted if p["rulesWarn"]),
            "caughtByRulesAny": sum(1 for p in planted if p["rulesAny"]),
            "caughtByEither": sum(1 for p in planted if p["model"] or p["rulesWarn"]),
            "plantedDetail": [{"label": p["label"], "model": p["model"], "rulesWarn": p["rulesWarn"]} for p in planted],
            "falseFlags": len(false_flags),
            "retracted": sum(1 for f in r.findings if f.status == "retracted"),
            "lineCoverage": r.line_coverage,
            "modelCalls": r.stats.model_calls,
            "seconds": round(time.time() - t0, 3),
        }
        results.append(row)

        print(f"  verdict {r.verdict} (expected {s['expect']['verdict']})  ·  {row['seconds']:.1f}s, {row['modelCalls']} calls")
        print(f"  planted caught: model {row['caughtByModel']}/{row['planted']} · rules(warn+) {row['caughtByRulesWarn']}/{row['planted']} · rules(any) {row['caughtByRulesAny']}/{row['planted']}")
        print(f"  false flags {row['falseFlags']} · withdrawn on self-check {row['retracted']} · line coverage {r.line_coverage * 100:.0f}%")
        if verbose:
            print("  claims:", " | ".join(f"{c.id}[{c.kind}] {c.text}" for c in claims))
            for c in changes:
                check = f"  [{c.self_check.mode} check: {c.self_check.outcome} – {c.self_check.reason}]" if c.self_check else ""
                print(
                    f"   {c.id.ljust(6)} {r.change_status[c.id].ljust(11)} {c.effect.ljust(8)} {c.concern.ljust(6)} "
                    f"claims={','.join(c.claims) or '-'} contra={','.join(c.contradicts) or '-'} {c.grounding}  {c.what}{check}"
                )
            for p in planted:
                if not p["model"]:
                    print(f"   MISSED: {p['label']}")
            for c in false_flags:
                print(f"   FALSE FLAG: {c.id} {c.what}")

    ok = [r for r in results if "verdict" in r]

    def total(key: str) -> int:
        return sum(r[key] for r in ok)

    summary = {
        "model": config.model,
        "claimsModel": config.claims_model,
        "ranAt": iso_now(),
        "samples": len(results),
        "verdictsCorrect": sum(1 for r in ok if r["verdictOk"]),
        "planted": total("planted"),
        "caughtByModel": total("caughtByModel"),
        "caughtByRulesWarn": total("caughtByRulesWarn"),
        "caughtByRulesAny": total("caughtByRulesAny"),
        "caughtByEither": total("caughtByEither"),
        "falseFlags": total("falseFlags"),
        "totalSeconds": round(sum(r["seconds"] for r in ok)),
        "results": results,
    }
    print(
        f"\nSUMMARY  verdicts {summary['verdictsCorrect']}/{summary['samples']} · planted caught: model {summary['caughtByModel']}/{summary['planted']}, "
        f"rules(warn+) {summary['caughtByRulesWarn']}/{summary['planted']}, rules(any) {summary['caughtByRulesAny']}/{summary['planted']}, "
        f"model or rules {summary['caughtByEither']}/{summary['planted']} · false flags {summary['falseFlags']}"
    )
    if not only:
        target = ROOT / "eval" / "results.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
        print("Wrote eval/results.json")


if __name__ == "__main__":
    asyncio.run(main())
