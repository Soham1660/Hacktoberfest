import { html, useMemo, useState } from "../../vendor/preact-htm.js";
import { changeStatus } from "../status.js";
import { STATUS_LABEL } from "../format.js";
import { Chevron, Flag } from "./icons.js";
import { SelfCheckLine, Spinner } from "./ui.js";

const FLAGGED = ["unexplained", "contradicts"];

/** CSS tone for a change: its finding's concern when flagged, "covered" when explained, otherwise none. */
function tone(c, severity) {
  const st = changeStatus(c);
  if (st === "explained") return "covered";
  if (FLAGGED.includes(st)) return `c-${severity.get(c.id) ?? c.concern}`;
  return st === "retracted" ? "withdrawn-tone" : "plain";
}

export function DiffView(props) {
  const { files, changes, signals, findings } = props;
  const [focus, setFocus] = useState(false);
  const [collapsed, setCollapsed] = useState(() => Object.fromEntries(files.filter((f) => f.category === "lockfile").map((f) => [f.index, true])));
  const severity = useMemo(() => new Map(findings.map((f) => [f.changeId, f.severity])), [findings]);

  const fileHasFlags = useMemo(() => {
    const m = new Map();
    for (const c of changes) if (FLAGGED.includes(changeStatus(c))) m.set(c.file, true);
    for (const s of signals) if (s.severity !== "info") m.set(s.file, true);
    return m;
  }, [changes, signals]);

  const shown = focus ? files.filter((f) => fileHasFlags.get(f.path)) : files;

  return html`<section class="diff" aria-labelledby="diff-title">
    <div class="section-head">
      <h2 class="section-title" id="diff-title">Diff <span class="count">${files.length} ${files.length === 1 ? "file" : "files"}</span></h2>
      <label class="check">
        <input type="checkbox" checked=${focus} onChange=${(e) => setFocus(e.target.checked)} /> Flagged files only
      </label>
    </div>
    ${!props.staticOnly &&
    html`<p class="legend help">
      Numbers beside the code match the findings above. A <span class="swatch covered" aria-hidden="true" /> green bar marks a change a claim covers; a hollow dot marks a changed
      line tied to no change.
    </p>`}
    ${shown.length === 0 && html`<p class="empty">No flagged files.</p>`}
    ${shown.map(
      (f) => html`<article key=${f.index} class="file">
        <h3 class="file-heading">
          <button type="button" class="file-head" onClick=${() => setCollapsed((c) => ({ ...c, [f.index]: !c[f.index] }))} aria-expanded=${!collapsed[f.index]}>
            <${Chevron} class="chev" />
            <span class="path mono">${f.oldPath ? `${f.oldPath} → ` : ""}${f.path}</span>
            <span class="file-tags">
              ${f.status !== "modified" && html`<span class="chip">${f.status}</span>`}
              <span class="chip">${f.category}</span>
              ${f.sensitive && html`<span class="chip chip-warn">sensitive path</span>`}
            </span>
            <span class="counts mono"><span class="plus">+${f.additions}</span> <span class="minus">−${f.deletions}</span></span>
          </button>
        </h3>
        ${!collapsed[f.index] &&
        html`<div class="file-body">
          ${f.binary && html`<p class="unit-note">Binary file. Its content can’t be reviewed.</p>`}
          ${f.hunks.map((h) => html`<${HunkView} key=${h.id} hunk=${h} file=${f} severity=${severity} ...${props} />`)}
        </div>`}
      </article>`,
    )}
  </section>`;
}

function HunkView({ hunk, file, severity, units, signals, changes, unitState, unitErrors, notes, verifying, staticOnly }) {
  const hunkUnits = units.filter((u) => u.hunkId === hunk.id);
  const hunkChanges = changes.filter((c) => c.hunkId === hunk.id);

  const { lineChange, endsAt, unitOf, orphans } = useMemo(() => {
    const lineChange = new Map();
    const endsAt = new Map();
    const orphans = [];
    for (const c of hunkChanges) {
      if (!c.lineIdx.length) {
        orphans.push(c);
        continue;
      }
      for (const i of c.lineIdx) if (!lineChange.has(i)) lineChange.set(i, c);
      const last = c.lineIdx[c.lineIdx.length - 1];
      endsAt.set(last, [...(endsAt.get(last) ?? []), c]);
    }
    const unitOf = new Map();
    for (const u of hunkUnits) for (const i of u.lineIdx) unitOf.set(i, u);
    return { lineChange, endsAt, unitOf, orphans };
  }, [hunkChanges, hunkUnits]);

  const sigAt = (i) => signals.filter((s) => s.hunkId === hunk.id && s.lineIndex === i);
  const states = hunkUnits.filter((u) => u.mode === "model").map((u) => unitState[u.id]);
  const reviewing = states.includes("active");
  const errored = hunkUnits.find((u) => unitState[u.id] === "error");
  const special = hunkUnits.find((u) => u.mode !== "model");
  const range = /^@@[^@]*@@/.exec(hunk.header)?.[0] ?? hunk.header;

  return html`<div class="hunk">
    <div class="hunk-head mono">
      <span>${range}</span>
      ${hunk.section && html`<span class="hunk-section">${hunk.section}</span>`}
      <span class="hunk-state">
        ${reviewing && html`<${Spinner} /> reviewing`} ${!reviewing && !staticOnly && states.length > 0 && states.every((s) => s === "pending") && "queued"}
      </span>
    </div>
    ${special && html`<p class="unit-note">${special.note}</p>`}
    ${errored && html`<p class="unit-note text-danger">This excerpt could not be reviewed: ${unitErrors[errored.id]}</p>`}
    <table class="lines">
      <caption class="sr-only">${file.path}, ${range}</caption>
      <colgroup>
        <col class="col-mark" />
        <col class="col-no col-old" />
        <col class="col-no" />
        <col class="col-sign" />
        <col />
      </colgroup>
      <thead class="sr-only">
        <tr>
          <th scope="col">Finding</th>
          <th scope="col">Old line</th>
          <th scope="col">New line</th>
          <th scope="col">Change</th>
          <th scope="col">Code</th>
        </tr>
      </thead>
      <tbody>
        ${hunk.lines.flatMap((l, i) => {
          const c = lineChange.get(i);
          const u = unitOf.get(i);
          const uncited = !c && l.kind !== "ctx" && !!l.text.trim() && u?.mode === "model" && unitState[u.id] === "done";
          const sigs = sigAt(i);
          const t = c ? tone(c, severity) : "";
          return [
            html`<tr key=${`line-${i}`} id=${`L-${hunk.id}-${i}`} class=${`line ${l.kind} ${t}`}>
              <td class="mark">
                ${c && notes.has(c.id) && c.lineIdx[0] === i ? html`<span class="fn-mark">${notes.get(c.id)}</span>` : null}
                ${uncited &&
                html`<span class="uncited" title="Changed, but the model tied it to no change"><span class="sr-only">Not attributed to any change</span></span>`}
              </td>
              <td class="no old">${l.oldNo ?? ""}</td>
              <td class="no new">${l.newNo ?? ""}</td>
              <td class="sign" aria-label=${l.kind === "add" ? "added" : l.kind === "del" ? "removed" : "unchanged"}>${l.kind === "add" ? "+" : l.kind === "del" ? "−" : ""}</td>
              <td class="code">
                <code>${visibleUnicode(l.text)}</code>
                ${sigs.map(
                  (s) => html`<span key=${s.id} class=${`chip chip-rule rule-${s.severity}`} title=${`${s.title}: ${s.detail}`}><${Flag} /> ${s.title}</span>`,
                )}
              </td>
            </tr>`,
            ...(endsAt.get(i) ?? []).map(
              (ch) => html`<${NoteRow} key=${`note-${ch.id}`} change=${ch} n=${notes.get(ch.id)} tone=${tone(ch, severity)} verifying=${verifying.includes(ch.id)} />`,
            ),
          ];
        })}
        ${orphans.map((ch) => html`<${NoteRow} key=${`orphan-${ch.id}`} change=${ch} n=${notes.get(ch.id)} tone=${tone(ch, severity)} verifying=${verifying.includes(ch.id)} />`)}
      </tbody>
    </table>
  </div>`;
}

function NoteRow({ change: c, n, tone, verifying }) {
  const st = changeStatus(c);
  return html`<tr class=${`note-row ${tone}`}>
    <td class="mark">${n ? html`<span class="fn-mark">${n}</span>` : null}</td>
    <td colspan="4">
      <div class="note">
        <span class="mono note-id">${c.id}</span>
        <span class="note-what">${c.what}</span>
        <span class="note-chips">
          ${!(st === "explained" && c.claims.length) && !(st === "contradicts" && c.contradicts.length) && html`<span class="chip">${STATUS_LABEL[st]}</span>`}
          ${c.effect !== "none" && html`<span class="chip">${c.effect}</span>`}
          ${st !== "retracted" && c.claims.map((id) => html`<span key=${id} class="chip">covers ${id}</span>`)}
          ${st !== "retracted" && c.contradicts.map((id) => html`<span key=${id} class="chip chip-break">breaks ${id}</span>`)}
          ${c.grounding !== "verified" && html`<span class="chip chip-warn" title=${c.groundingNote ?? ""}>citation ${c.grounding}</span>`}
        </span>
        ${verifying && html`<span class="note-check"><${Spinner} /> Second look in progress…</span>`}
        ${c.selfCheck?.outcome === "confirmed" && html`<${SelfCheckLine} check=${c.selfCheck} />`}
      </div>
    </td>
  </tr>`;
}

const HIDDEN = /[​-‍⁠﻿‪-‮⁦-⁩]/;
const HIDDEN_SPLIT = /([​-‍⁠﻿‪-‮⁦-⁩])/;

/** Makes invisible and bidirectional control characters visible, since they are a known attack vector. */
function visibleUnicode(text) {
  if (!HIDDEN.test(text)) return text || " ";
  return text.split(HIDDEN_SPLIT).map((part, i) =>
    i % 2
      ? html`<span key=${i} class="hidden-char" title="Invisible Unicode character">${`U+${part.codePointAt(0).toString(16).toUpperCase().padStart(4, "0")}`}</span>`
      : part,
  );
}
