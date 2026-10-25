import { html } from "../../vendor/preact-htm.js";
import { CONCERN_LABEL } from "../format.js";
import { Alert, Check, Info } from "./icons.js";

/** Always sits next to words that name the work in progress. */
export const Spinner = () => html`<span class="spinner" aria-hidden="true" />`;

/** Concern is the only thing that colors a finding. The label and glyph carry it for readers who can't see the color. */
export function ConcernMark({ level }) {
  const Icon = level === "high" || level === "medium" ? Alert : Info;
  return html`<span class=${`concern c-${level}`}><${Icon} /> ${CONCERN_LABEL[level]}</span>`;
}

export function Notice({ kind, children, action }) {
  const Icon = kind === "success" ? Check : kind === "neutral" ? Info : Alert;
  return html`<div class=${`notice n-${kind}`} role=${kind === "danger" ? "alert" : "status"}>
    <${Icon} />
    <div class="notice-body">${children}</div>
    ${action}
  </div>`;
}

const OUTCOME = {
  upheld: "Flag upheld on second look.",
  withdrawn: "Flag withdrawn on second look.",
  confirmed: "Coverage confirmed on second look.",
  overturned: "Not actually covered, on second look.",
};

export function SelfCheckLine({ check }) {
  return html`<p class=${`self-check ${check.outcome}`}>
    <b>${OUTCOME[check.outcome]}</b> ${check.reason}
    ${check.outcome === "overturned" && check.claimsBefore.length > 0 && html`<span class="text-3"> First pass said: covered by ${check.claimsBefore.join(", ")}.</span>`}
  </p>`;
}
