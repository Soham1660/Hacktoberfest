import { html, useCallback, useEffect, useMemo, useState } from "../vendor/preact-htm.js";
import { changeStatus } from "./status.js";
import { getHealth } from "./api.js";
import { displayFindings, footnotes } from "./format.js";
import { loadDraft, saveDraft, wasInterrupted } from "./persist.js";
import { useAnalysis } from "./analysis.js";
import { Claims } from "./components/Claims.js";
import { Compose } from "./components/Compose.js";
import { DiffView } from "./components/DiffView.js";
import { Findings } from "./components/Findings.js";
import { ModelStatus } from "./components/ModelStatus.js";
import { Progress } from "./components/Progress.js";
import { ReviewDraft } from "./components/ReviewDraft.js";
import { Verdict } from "./components/Verdict.js";
import { Notice } from "./components/ui.js";

const EMPTY = { title: "", description: "", diff: "" };
// Read once at load: the marker is cleared as it is read.
const interruptedOnLoad = wasInterrupted();

export function App() {
  const [health, setHealth] = useState(null);
  const [draft, setDraft] = useState(() => loadDraft() ?? EMPTY);
  const { state, run, runStatic, cancel, reset } = useAnalysis();

  const refreshHealth = useCallback(() => {
    getHealth()
      .then(setHealth)
      .catch((e) => setHealth({ ok: false, ollama: false, host: "", model: "", claimsModel: "", modelInstalled: false, claimsModelInstalled: false, message: e.message }));
  }, []);

  useEffect(() => {
    refreshHealth();
  }, [refreshHealth]);

  useEffect(() => {
    if (health?.ok) return;
    const t = setInterval(refreshHealth, 8000);
    return () => clearInterval(t);
  }, [health?.ok, refreshHealth]);

  // Keep the typed pull request across refreshes.
  useEffect(() => {
    const t = setTimeout(() => saveDraft(draft), 400);
    return () => clearTimeout(t);
  }, [draft]);

  const findings = useMemo(() => displayFindings(state.report, state.changes), [state.report, state.changes]);
  const notes = useMemo(() => footnotes(findings), [findings]);
  const flaggedSoFar = state.changes.filter((c) => ["unexplained", "contradicts"].includes(changeStatus(c))).length;

  const composing = state.mode === "idle" || (state.mode === "error" && !state.parsed);

  return html`<div class="app">
    <a class="skip-link" href="#main">Skip to main content</a>
    <header class="site-header">
      <div class="frame header-row">
        <span class="wordmark">
          <img class="wordmark-logo" src="/favicon.svg" alt="" width="22" height="22" />
          PR Checker
        </span>
        <${ModelStatus} health=${health} onRetry=${refreshHealth} />
      </div>
    </header>

    <main id="main" class="frame">
      ${composing
        ? html`<${Compose}
            draft=${draft}
            setDraft=${setDraft}
            health=${health}
            error=${state.mode === "error" ? state.error : null}
            interrupted=${interruptedOnLoad && state.mode === "idle"}
            onAudit=${() => run(draft)}
            onStatic=${() => runStatic(draft)}
          />`
        : html`<${Review}
            state=${state}
            health=${health}
            findings=${findings}
            notes=${notes}
            flaggedSoFar=${flaggedSoFar}
            onCancel=${cancel}
            onNew=${reset}
            onRun=${run}
          />`}
    </main>

    <footer class="site-footer">
      <div class="frame">Your code stays on this machine. The model runs locally through Ollama. Only GitHub imports use the network.</div>
    </footer>
  </div>`;
}

function Review({ state, health, findings, notes, flaggedSoFar, onCancel, onNew, onRun }) {
  const pr = state.pr;
  const parsed = state.parsed;
  const isStatic = state.mode === "static";
  const cancelled = state.error === "Review cancelled.";

  return html`<div class="review">
    <header class="pr-header">
      <div class="pr-heading">
        ${(pr?.source || state.restored) &&
        html`<p class="meta">
          ${pr?.source && html`<span class="mono">${pr.source}</span>`} ${pr?.source && state.restored && " · "} ${state.restored && "Restored after a refresh"}
        </p>`}
        <h1 class="pr-title">${pr?.title || "Untitled pull request"}</h1>
        ${pr?.description && html`<${Description} text=${pr.description} />`}
      </div>
      <div class="pr-actions">
        ${state.mode === "running"
          ? html`<button type="button" class="btn" onClick=${onCancel}>Cancel review</button>`
          : html`
              ${pr && health?.ok && html`<button type="button" class="btn" onClick=${() => onRun(pr)}>${isStatic ? "Run full AI review" : "Run again"}</button>`}
              <button type="button" class="btn" onClick=${onNew}>New audit</button>
            `}
      </div>
    </header>

    <div class=${`review-grid ${isStatic ? "no-rail" : ""}`}>
      <div class="area-verdict">
        ${state.mode === "error" &&
        html`<${Notice}
          kind=${cancelled ? "warning" : "danger"}
          action=${pr && health?.ok ? html`<button type="button" class="btn small" onClick=${() => onRun(pr)}>Try again</button>` : undefined}
        >
          <b>${cancelled ? "Review cancelled." : "The review stopped."}</b> ${cancelled ? "Findings below are provisional." : state.error}
        <//>`}
        ${isStatic
          ? html`<${StaticVerdict} signals=${parsed?.signals ?? []} />`
          : html`<${Verdict} report=${state.report} running=${state.mode === "running"} flaggedSoFar=${flaggedSoFar} />`}
      </div>

      ${!isStatic &&
      html`<aside class="area-rail" aria-label="Progress and claims">
        <${Progress} state=${state} />
        <${Claims} claims=${state.claims} results=${state.report?.claims ?? null} changes=${state.changes} running=${state.mode === "running"} />
      </aside>`}

      <div class="area-main">
        ${state.report && pr && state.mode === "done" && html`<${ReviewDraft} pr=${pr} report=${state.report} changes=${state.changes} />`}
        ${!isStatic &&
        html`<${Findings} findings=${findings} notes=${notes} changes=${state.changes} signals=${parsed?.signals ?? []} verifying=${state.verifying} final=${!!state.report} />`}
        ${parsed &&
        html`<${DiffView}
          files=${parsed.files}
          units=${parsed.units}
          signals=${parsed.signals}
          changes=${isStatic ? [] : state.changes}
          findings=${findings}
          unitState=${state.units}
          unitErrors=${state.unitErrors}
          notes=${notes}
          verifying=${state.verifying}
          staticOnly=${isStatic}
        />`}
      </div>
    </div>
  </div>`;
}

function StaticVerdict({ signals }) {
  const warnings = signals.filter((s) => s.severity !== "info").length;
  const notes = signals.length - warnings;
  return html`<section class="panel verdict" aria-labelledby="verdict-title">
    <p class="meta">Static rules only · no model</p>
    <h2 class="verdict-headline" id="verdict-title">${warnings} ${warnings === 1 ? "warning" : "warnings"}, ${notes} ${notes === 1 ? "note" : "notes"}</h2>
    <p class="verdict-summary">
      Pattern rules see suspicious strings, not intent. They can’t tell whether a change matches what the description promised. Run the full review for that.
    </p>
  </section>`;
}

/** The description is the premise of the audit, so it stays visible; long ones are clamped with a toggle. */
function Description({ text }) {
  const [open, setOpen] = useState(false);
  const long = text.length > 320 || text.split("\n").length > 5;
  return html`<div class="pr-desc">
    <blockquote class=${long && !open ? "clamped" : undefined}>${text}</blockquote>
    ${long && html`<button type="button" class="link-btn" aria-expanded=${open} onClick=${() => setOpen(!open)}>${open ? "Show less" : "Show full description"}</button>`}
  </div>`;
}
