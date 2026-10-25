import { html } from "../../vendor/preact-htm.js";
import { pct } from "../format.js";
import { Alert, Info } from "./icons.js";
import { Notice } from "./ui.js";

export function Verdict({ report, running, flaggedSoFar }) {
  if (!report) {
    return html`<section class="panel verdict" aria-live="polite" aria-labelledby="verdict-title">
      <h2 class="verdict-headline" id="verdict-title">${running ? "Review in progress" : "No verdict"}</h2>
      <p class="verdict-summary">
        ${running
          ? flaggedSoFar
            ? `${flaggedSoFar} change${flaggedSoFar === 1 ? "" : "s"} flagged so far. Flags are provisional until the second look finishes.`
            : "The verdict appears once every excerpt has been reviewed and each flag double-checked."
          : "The review stopped before a verdict was reached."}
      </p>
    </section>`;
  }

  const b = report.baseline;
  const Icon = report.risk === "high" || report.risk === "medium" ? Alert : Info;
  const riskLabel = report.risk === "none" ? "No risk found" : `${report.risk[0].toUpperCase()}${report.risk.slice(1)} risk`;
  return html`<section class=${`panel verdict risk-${report.risk}`} aria-live="polite" aria-labelledby="verdict-title">
    <p class=${`concern c-${report.risk}`}><${Icon} /> ${riskLabel}</p>
    <h2 class="verdict-headline" id="verdict-title">${report.headline}</h2>
    <p class="verdict-summary">${report.summary}</p>
    <dl class="facts">
      <div>
        <dt>Disclosed</dt>
        <dd>${pct(report.disclosure)}</dd>
        <dd class="fact-note">of behavior-changing lines a claim accounts for</dd>
      </div>
      <div>
        <dt>Lines accounted for</dt>
        <dd>${pct(report.lineCoverage)}</dd>
        <dd class="fact-note">of changed lines tied to a change</dd>
      </div>
      <div>
        <dt>Static rule warnings</dt>
        <dd>${b.warnOrCritical}</dd>
        <dd class="fact-note">rules that fired before the model ran</dd>
      </div>
    </dl>
    ${b.findingsMissedByRules > 0 &&
    html`<p class="baseline">
      ${b.findingsMissedByRules === 1 ? "One serious finding" : `${b.findingsMissedByRules} serious findings`} below matched no static rule. Pattern matching alone would have missed${" "}
      ${b.findingsMissedByRules === 1 ? "it" : "them"}.
    </p>`}
    ${report.stats.failedUnits > 0 &&
    html`<${Notice} kind="warning">
      ${report.stats.failedUnits} excerpt${report.stats.failedUnits === 1 ? "" : "s"} could not be reviewed. Their lines are marked in the diff.
    <//>`}
  </section>`;
}
