"""Regression check on real, honest pull requests from public MIT-licensed projects
(fixtures in eval/real, imported with the app's GitHub importer). These PRs do what
they say, so a serious finding or a "contradicts"/"undisclosed" verdict is a false alarm.

    python scripts/eval_real.py
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List

from pr_checker.config import ROOT, config
from pr_checker.jsutil import iso_now
from pr_checker.models import PullRequestInput
from pr_checker.pipeline import run_analysis

FALSE_ALARM = {"contradicts", "undisclosed"}

# Fixtures whose verdict is judged; others are run for information only.
HONEST = {"axios-11062", "got-2454"}


async def main() -> None:
    directory = ROOT / "eval" / "real"
    rows: List[Dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        pid = path.stem
        pr = json.loads(path.read_text(encoding="utf8"))
        report = None
        claims: List[Any] = []
        error = None

        def emit(e: Dict[str, Any]) -> None:
            nonlocal report, claims, error
            if e["type"] == "report":
                report = e["report"]
            elif e["type"] == "claims":
                claims = e["claims"]
            elif e["type"] == "error":
                error = e["message"]

        t0 = time.time()
        try:
            await run_analysis(PullRequestInput(pr["title"], pr["description"], pr["diff"]), emit)
        except Exception as err:
            error = str(err)
        seconds = round(time.time() - t0)

        print(f"\n▸ {pr['source']}  “{pr['title']}”  ·  {seconds}s")
        if error or not report:
            print(f"  ERROR {error}")
            rows.append({"id": pid, "source": pr["source"], "error": error})
            continue
        r = report
        serious = [f for f in r.findings if f.status != "retracted" and f.severity in ("medium", "high")]
        judged = pid in HONEST
        passed = not judged or (r.verdict not in FALSE_ALARM and not serious)
        print("  claims: " + " | ".join(f"{c.id}[{c.kind}{':' + c.limit if c.limit != 'other' else ''}] {c.text}" for c in claims))
        print(f"  verdict {r.verdict} · serious findings {len(serious)} · {('PASS' if passed else 'FALSE ALARM') if judged else 'info only'}")
        for f in r.findings:
            note = f"  [{f.self_check_reason}]" if f.self_check_reason else ""
            print(f"   {f.status.ljust(11)} {f.severity.ljust(6)} {f.file}:{f.first_line if f.first_line is not None else '?'}  {f.what}{note}")
        rows.append({"id": pid, "source": pr["source"], "verdict": r.verdict, "serious": len(serious), "judged": judged, "pass": passed, "seconds": seconds})

    judged_rows = [r for r in rows if r.get("judged")]
    summary = {
        "model": config.model,
        "ranAt": iso_now(),
        "passed": sum(1 for r in judged_rows if r.get("pass")),
        "judged": len(judged_rows),
        "rows": rows,
    }
    print(f"\nSUMMARY  honest PRs without false alarms: {summary['passed']}/{summary['judged']}")
    (ROOT / "eval" / "real-results.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf8")


if __name__ == "__main__":
    asyncio.run(main())
