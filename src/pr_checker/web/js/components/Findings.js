import { html } from "../../vendor/preact-htm.js";
import { scrollToLine, STATUS_LABEL } from "../format.js";
import { ConcernMark, SelfCheckLine, Spinner } from "./ui.js";

export function Findings({ findings, notes, changes, signals, verifying, final }) {
  const byId = new Map(changes.map((c) => [c.id, c]));
  const live = findings.filter((f) => f.status !== "retracted");
  const withdrawn = findings.filter((f) => f.status === "retracted");

  const lineLabel = (f) => {
    const c = byId.get(f.changeId);
    return `${f.file}${f.firstLine ? `:${f.firstLine}` : ""}${c && c.lineIdx.length > 1 ? ` (+${c.lineIdx.length - 1} lines)` : ""}`;
  };
  const go = (f) => {
    const c = byId.get(f.changeId);
    if (c?.lineIdx.length) scrollToLine(c.hunkId, c.lineIdx[0]);
  };

  if (!findings.length) {
    return final
      ? html`<section aria-labelledby="findings-title">
          <h2 class="section-title" id="findings-title">Findings</h2>
          <p class="empty">Every change the model identified traces back to a claim in the description. Check the claims list for any that nothing in the diff supports.</p>
        </section>`
      : null;
  }

  return html`<section aria-labelledby="findings-title">
    <div class="section-head">
      <h2 class="section-title" id="findings-title">Findings <span class="count">${live.length}</span></h2>
      ${!final && html`<span class="help">Provisional until the review finishes</span>`}
    </div>
    <ol class="findings">
      ${live.map((f) => {
        const check = byId.get(f.changeId)?.selfCheck;
        return html`<li key=${f.changeId} class=${`finding c-${f.severity}`}>
          <button type="button" class="fn" onClick=${() => go(f)} aria-label=${`Finding ${notes.get(f.changeId)}: show in the diff`}>${notes.get(f.changeId)}</button>
          <div class="finding-body">
            <p class="finding-meta">
              <${ConcernMark} level=${f.severity} />
              ${f.contradicts.length > 0 ? html`<span class="chip chip-break">breaks ${f.contradicts.join(", ")}</span>` : html`<span class="chip">${STATUS_LABEL[f.status]}</span>`}
              ${f.signalIds.map((id) => {
                const s = signals.find((x) => x.id === id);
                return s ? html`<span key=${id} class="chip">rule: ${s.title.toLowerCase()}</span>` : null;
              })}
            </p>
            <p class="finding-what">${f.what}</p>
            ${f.why && html`<p class="finding-why">${f.why}</p>`}
            ${verifying.includes(f.changeId)
              ? html`<p class="self-check"><${Spinner} /> Second look in progress…</p>`
              : check
                ? html`<${SelfCheckLine} check=${check} />`
                : null}
            ${f.grounding !== "verified" &&
            html`<p class="self-check text-warning">Citation ${f.grounding === "failed" ? "could not be matched to the diff." : "partly matched the diff."}</p>`}
            <button type="button" class="loc mono" onClick=${() => go(f)}>${lineLabel(f)}</button>
          </div>
        </li>`;
      })}
    </ol>
    ${withdrawn.length > 0 &&
    html`<details class="withdrawn">
      <summary>${withdrawn.length} flag${withdrawn.length === 1 ? "" : "s"} withdrawn on second look</summary>
      <ul>
        ${withdrawn.map(
          (f) => html`<li key=${f.changeId}>
            <button type="button" class="loc mono" onClick=${() => go(f)}>${lineLabel(f)}</button>
            <s>${f.what}</s>
            <span class="text-3"> ${f.selfCheckReason}</span>
          </li>`,
        )}
      </ul>
    </details>`}
  </section>`;
}
