import { html, useEffect, useState } from "../../vendor/preact-htm.js";
import { clock, secs } from "../format.js";
import { Check, Cross, Dash, Ring } from "./icons.js";
import { Spinner } from "./ui.js";

const LABELS = {
  parse: "Parse the diff, run static rules",
  claims: "Read the description into claims",
  review: "Review each excerpt against the claims",
  verify: "Second, skeptical look at each flag",
  report: "Check citations and score",
};

export function Progress({ state }) {
  const running = state.mode === "running";
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [running]);

  const units = Object.values(state.units);
  const done = units.filter((u) => u === "done" || u === "error").length;
  const failedUnits = units.filter((u) => u === "error").length;
  const active = units.filter((u) => u === "active").length;
  const flagged = state.changes.filter((c) => c.selfCheck).length;
  const toVerify = flagged + state.verifying.length;
  const p = state.parsed;

  const detail = {
    parse: p ? `${p.files.length} files · ${p.files.reduce((n, f) => n + f.hunks.length, 0)} hunks · ${p.signals.length} rule ${p.signals.length === 1 ? "hit" : "hits"}` : null,
    claims: state.stages.claims.status === "done" ? `${state.claims.length} ${state.claims.length === 1 ? "claim" : "claims"}` : null,
    review: units.length ? `${done} of ${units.length} excerpts${active ? ` · ${active} in progress` : ""}${failedUnits ? ` · ${failedUnits} failed` : ""}` : null,
    verify: state.stages.verify.status === "skipped" ? "Nothing serious to double-check" : toVerify ? `${flagged} of ${toVerify} flags` : null,
    report: state.report ? `${state.report.stats.modelCalls} model calls` : null,
  };

  const elapsed = state.elapsedMs ?? (state.startedAt ? now - state.startedAt : 0);

  const steps = html`<ol class="steps">
    ${Object.keys(LABELS).map((id) => {
      const st = state.stages[id];
      const failed = state.mode === "error" && st.status === "active";
      const status = failed ? "failed" : st.status;
      const t = st.startedAt && (st.endedAt ?? (st.status === "active" ? now : undefined));
      const glyph =
        status === "failed" ? html`<${Cross} />` : status === "done" ? html`<${Check} />` : status === "active" ? html`<${Spinner} />` : status === "skipped" ? html`<${Dash} />` : html`<${Ring} />`;
      return html`<li key=${id} class=${`step ${status}`}>
        <span class="step-glyph">${glyph}</span>
        <span class="step-label">${LABELS[id]}<span class="sr-only"> (${status})</span></span>
        <span class="step-time meta">${t && st.startedAt ? secs(Math.max(0, t - st.startedAt)) : ""}</span>
        ${detail[id] && html`<span class="step-detail">${detail[id]}</span>`}
        ${id === "review" &&
        units.length > 0 &&
        html`<span class="meter" role="img" aria-label=${`${done} of ${units.length} excerpts reviewed`}>${units.map((u, i) => html`<i key=${i} class=${u} />`)}</span>`}
      </li>`;
    })}
  </ol>`;

  if (running || state.mode === "error")
    return html`<section class="rail-section" aria-label="Review progress">
      <div class="section-head">
        <h2 class="section-title">Progress</h2>
        <span class="meta mono">${elapsed ? clock(elapsed) : ""}</span>
      </div>
      ${steps} ${state.model && html`<p class="help mono">${state.model}</p>`}
    </section>`;

  return html`<details class="rail-section run-details">
    <summary>How this review ran <span class="meta">· ${state.elapsedMs ? secs(state.elapsedMs) : ""}</span></summary>
    ${steps} ${state.model && html`<p class="help mono">${state.model}</p>`}
  </details>`;
}
