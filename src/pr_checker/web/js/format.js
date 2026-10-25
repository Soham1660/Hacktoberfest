import { changeStatus } from "./status.js";

export const pct = (x) => (x === null ? "n/a" : `${Math.round(x * 100)}%`);
/** m:ss, for run timers. */
export const clock = (ms) => `${Math.floor(ms / 60_000)}:${String(Math.floor((ms % 60_000) / 1000)).padStart(2, "0")}`;
export const secs = (ms) => (ms < 10_000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms / 1000)}s`);

export const STATUS_LABEL = {
  explained: "Covered",
  incidental: "Incidental",
  unexplained: "Not mentioned",
  contradicts: "Contradicts",
  retracted: "Withdrawn",
};

export const CONCERN_LABEL = { none: "No concern", low: "Low concern", medium: "Medium concern", high: "High concern" };

const RANK = { none: 0, low: 1, medium: 2, high: 3 };

/**
 * Findings to display. Uses the final report when present; while the review is
 * streaming, derives provisional findings from the changes seen so far.
 */
export function displayFindings(report, changes) {
  if (report) return report.findings;
  return changes
    .map((c) => {
      const status = changeStatus(c);
      if (status === "explained" || status === "incidental") return null;
      return {
        changeId: c.id,
        status,
        severity: status === "retracted" ? "none" : c.concern === "none" ? "low" : c.concern,
        file: c.file,
        hunkId: c.hunkId,
        firstLine: null,
        what: c.what,
        why: c.why,
        contradicts: c.contradicts,
        selfCheckReason: c.selfCheck?.reason ?? null,
        grounding: c.grounding,
        signalIds: [],
      };
    })
    .filter((f) => f !== null)
    .sort((a, b) => Number(a.status === "retracted") - Number(b.status === "retracted") || RANK[b.severity] - RANK[a.severity]);
}

/** Footnote numbers for live findings; withdrawn ones get none. */
export function footnotes(findings) {
  const m = new Map();
  findings.filter((f) => f.status !== "retracted").forEach((f, i) => m.set(f.changeId, i + 1));
  return m;
}

export function scrollToLine(hunkId, idx) {
  const el = document.getElementById(`L-${hunkId}-${idx}`);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.remove("flash");
  void el.offsetWidth;
  el.classList.add("flash");
  window.setTimeout(() => el.classList.remove("flash"), 1300);
}
