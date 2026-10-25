import { html } from "../../vendor/preact-htm.js";
import { scrollToLine } from "../format.js";
import { Check, Cross, Question, Ring } from "./icons.js";

const STATUS = {
  supported: { label: "Found in diff", icon: Check, tone: "success" },
  held: { label: "Kept", icon: Check, tone: "success" },
  not_found: { label: "Not in diff", icon: Question, tone: "warning" },
  violated: { label: "Broken", icon: Cross, tone: "danger" },
};

export function Claims({ claims, results, changes, running }) {
  if (!claims.length && running) return null;
  const byId = new Map(changes.map((c) => [c.id, c]));

  return html`<section class="rail-section" id="claims" aria-labelledby="claims-title">
    <h2 class="section-title" id="claims-title">Claims in the description</h2>
    ${!claims.length && html`<p class="help">The description makes no checkable claims, so every behavior change counts as not mentioned.</p>`}
    <ol class="claims">
      ${claims.map((cl) => {
        const r = results?.find((x) => x.id === cl.id);
        const st = r ? STATUS[r.status] : null;
        return html`<li key=${cl.id} class="claim">
          <span class="claim-id mono">${cl.id}</span>
          <div>
            <p class="claim-text">${cl.text}${cl.kind === "constraint" && html`<span class="chip">promise</span>`}</p>
            <p class=${`claim-status ${st ? `t-${st.tone}` : ""}`}>
              ${st ? html`<${st.icon} /> ${st.label}` : html`<${Ring} /> Checking…`}
            </p>
            ${r &&
            r.changeIds.length > 0 &&
            html`<p class="refs">
              ${r.changeIds.slice(0, 8).map((id) => {
                const c = byId.get(id);
                return html`<button key=${id} type="button" class="ref mono" onClick=${() => c && scrollToLine(c.hunkId, c.lineIdx[0])} disabled=${!c?.lineIdx.length}>${id}</button>`;
              })}
              ${r.changeIds.length > 8 && html`<span class="meta">+${r.changeIds.length - 8}</span>`}
            </p>`}
          </div>
        </li>`;
      })}
    </ol>
  </section>`;
}
