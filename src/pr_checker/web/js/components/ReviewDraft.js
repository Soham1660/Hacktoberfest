import { html, useEffect, useRef, useState } from "../../vendor/preact-htm.js";
import { draftComment } from "../api.js";
import { Copy } from "./icons.js";

/** Streams a maintainer review comment drafted from the confirmed findings. Nothing is posted anywhere. */
export function ReviewDraft({ pr, report, changes }) {
  const [text, setText] = useState("");
  const [state, setState] = useState("idle"); // idle | writing | done | error
  const [copied, setCopied] = useState("idle"); // idle | yes | blocked
  const abort = useRef(null);

  useEffect(() => () => abort.current?.abort(), []);

  const start = async () => {
    abort.current?.abort();
    const ctrl = new AbortController();
    abort.current = ctrl;
    setText("");
    setState("writing");
    const byId = new Map(changes.map((c) => [c.id, c]));
    const findings = report.findings
      .filter((f) => f.status !== "retracted" && f.severity !== "low")
      .map((f) => ({
        location: `${f.file}${f.firstLine ? `:${f.firstLine}` : ""}`,
        what: byId.get(f.changeId)?.what ?? f.what,
        why: f.why,
        status: f.status === "contradicts" ? `breaks ${f.contradicts.join(", ")}` : "not mentioned in description",
      }));
    try {
      await draftComment(
        { title: pr.title, claims: report.claims.map((c) => ({ id: c.id, text: c.text, status: c.status })), findings },
        (t) => setText((prev) => prev + t),
        ctrl.signal,
      );
      setState("done");
    } catch (e) {
      if (!ctrl.signal.aborted) {
        setText((prev) => `${prev}\n\n${e.message}`);
        setState("error");
      }
    }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text.trim());
      setCopied("yes");
    } catch {
      setCopied("blocked"); // the browser denied clipboard access; the text stays selectable on screen
    }
    setTimeout(() => setCopied("idle"), 2000);
  };

  if (state === "idle")
    return html`<div class="draft-cta">
      <button type="button" class="btn" onClick=${start}>Draft a review comment</button>
      <span class="help">Nothing is posted.</span>
    </div>`;

  return html`<section class="panel review-draft" aria-labelledby="draft-title">
    <div class="section-head">
      <h2 class="section-title" id="draft-title">Draft review comment</h2>
      <div class="row">
        <button type="button" class="link-btn" onClick=${start} disabled=${state === "writing"}>Redraft</button>
        <button type="button" class="btn small" onClick=${copy} disabled=${!text || state === "writing"}>
          <${Copy} /> ${copied === "yes" ? "Copied" : copied === "blocked" ? "Select and copy" : "Copy"}
        </button>
      </div>
    </div>
    <textarea
      class=${`comment ${state}`}
      aria-label="Review comment"
      aria-live="off"
      value=${text}
      placeholder=${state === "writing" ? "Writing…" : ""}
      onInput=${(e) => setText(e.target.value)}
      readOnly=${state === "writing"}
      rows=${Math.max(4, text.split("\n").length + 1)}
    />
    <p class="help">
      ${state === "writing" ? "Writing from the confirmed findings." : state === "error" ? "The draft stopped early. Redraft to try again." : "Edit it before you post. PR Checker never posts for you."}
    </p>
  </section>`;
}
