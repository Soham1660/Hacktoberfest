import { html, useEffect, useRef, useState } from "../../vendor/preact-htm.js";
import { getSample, getSamples, importGitHub } from "../api.js";
import { Arrow, Rule, Upload } from "./icons.js";
import { Notice, Spinner } from "./ui.js";

const MAX_BYTES = 600_000;
const PR_URL = /^https?:\/\/github\.com\/[^/\s]+\/[^/\s]+\/pull\/\d+/i;

const ids = { url: "pr-url", title: "pr-title-input", desc: "pr-desc-input", diff: "pr-diff-input", hint: "pr-action-hint", diffHelp: "pr-diff-help" };

export function Compose({ draft, setDraft, health, error, interrupted, onAudit, onStatic }) {
  const [samples, setSamples] = useState(null);
  const [samplesError, setSamplesError] = useState(null);
  const [url, setUrl] = useState("");
  const [urlError, setUrlError] = useState(null);
  const [importing, setImporting] = useState(false);
  const [loaded, setLoaded] = useState(null);
  const [fileError, setFileError] = useState(null);
  const fileRef = useRef(null);

  useEffect(() => {
    getSamples()
      .then(setSamples)
      .catch((e) => setSamplesError(e.message));
  }, []);

  const loadSample = async (s) => {
    setFileError(null);
    setUrlError(null);
    try {
      setDraft(await getSample(s.id));
      setLoaded(s.id);
    } catch (e) {
      setSamplesError(e.message);
    }
  };

  const doImport = async () => {
    const trimmed = url.trim();
    if (!PR_URL.test(trimmed)) return setUrlError("Enter a pull request URL, like https://github.com/owner/repo/pull/123.");
    setImporting(true);
    setUrlError(null);
    try {
      setDraft(await importGitHub(trimmed));
      setLoaded(null);
      setUrl("");
    } catch (e) {
      setUrlError(e.message);
    } finally {
      setImporting(false);
    }
  };

  const onFile = async (f) => {
    if (!f) return;
    if (f.size > MAX_BYTES) return setFileError(`${f.name} is ${Math.round(f.size / 1000)} KB. The limit is ${MAX_BYTES / 1000} KB.`);
    setFileError(null);
    setDraft({ ...draft, diff: await f.text(), source: f.name });
    setLoaded(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const bytes = new Blob([draft.diff]).size;
  const tooBig = bytes > MAX_BYTES;
  const hasDiff = draft.diff.trim().length > 0;
  const modelReady = health?.ok ?? false;
  const hint = !hasDiff
    ? "Add a diff to start."
    : tooBig
      ? `The diff is over ${MAX_BYTES / 1000} KB. Trim it or split the audit.`
      : health && !modelReady
        ? (health.message ?? "The model isn't available.")
        : null;
  const hasInput = !!(draft.title || draft.description || draft.diff);

  return html`<div class="compose">
    <div class="compose-intro">
      <h1 class="page-title">Audit a pull request against its description</h1>
      <p class="lede">PR Checker reads the description and the diff together, lists the changes the author didn't mention, and links each one to the lines that show it.</p>
    </div>

    <div class="compose-grid">
      <form class="panel form" aria-label="Pull request" onSubmit=${(e) => e.preventDefault()}>
        <div class="import">
          <label for=${ids.url}>Import from GitHub</label>
          <div class="import-row">
            <input
              id=${ids.url}
              type="url"
              value=${url}
              onInput=${(e) => setUrl(e.target.value)}
              onKeyDown=${(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  doImport();
                }
              }}
              placeholder="https://github.com/owner/repo/pull/123"
              spellcheck=${false}
              aria-invalid=${!!urlError}
              aria-describedby=${urlError ? `${ids.url}-err` : undefined}
            />
            <button type="button" class="btn" disabled=${importing || !url.trim()} onClick=${() => doImport()}>
              ${importing ? html`<${Spinner} /> Importing…` : "Import"}
            </button>
          </div>
          ${urlError && html`<p class="field-error" id=${`${ids.url}-err`} role="alert">${urlError}</p>`}
          <p class="help">Public pull requests only. Fills the three fields below.</p>
        </div>

        <div class="field">
          <label for=${ids.title}>Title</label>
          <input id=${ids.title} value=${draft.title} onInput=${(e) => setDraft({ ...draft, title: e.target.value })} placeholder="fix: handle empty config" />
        </div>

        <div class="field">
          <label for=${ids.desc}>Description</label>
          <textarea
            id=${ids.desc}
            rows="5"
            value=${draft.description}
            onInput=${(e) => setDraft({ ...draft, description: e.target.value })}
            placeholder="What the author says this pull request does"
          />
        </div>

        <div class="field">
          <div class="label-row">
            <label for=${ids.diff}>Diff</label>
            <span class=${`meta ${tooBig ? "text-danger" : ""}`}>${bytes ? `${(bytes / 1000).toFixed(1)} KB of ${MAX_BYTES / 1000} KB` : ""}</span>
          </div>
          <textarea
            id=${ids.diff}
            class="code-input"
            rows="9"
            value=${draft.diff}
            onInput=${(e) => setDraft({ ...draft, diff: e.target.value })}
            placeholder=${"diff --git a/src/app.ts b/src/app.ts\n@@ -1,3 +1,3 @@\n…"}
            spellcheck=${false}
            aria-invalid=${tooBig}
            aria-describedby=${ids.diffHelp}
          />
          <p class=${tooBig ? "field-error" : "help"} id=${ids.diffHelp}>
            ${tooBig ? `This diff is over the ${MAX_BYTES / 1000} KB limit.` : "Unified diff, as from git diff or a .diff / .patch file."}
            ${fileError && html`<span class="text-danger"> ${fileError}</span>`}
          </p>
          <div class="row">
            <button type="button" class="link-btn" onClick=${() => fileRef.current?.click()}><${Upload} /> Upload a .diff or .patch file</button>
            ${hasInput &&
            html`<button
              type="button"
              class="link-btn"
              onClick=${() => {
                setDraft({ title: "", description: "", diff: "" });
                setLoaded(null);
              }}
            >
              Clear all
            </button>`}
            <input ref=${fileRef} type="file" accept=".diff,.patch,.txt,text/plain" hidden onChange=${(e) => onFile(e.target.files?.[0])} />
          </div>
        </div>

        ${error && html`<${Notice} kind="danger">${error}<//>`}
        ${interrupted && !error && html`<${Notice} kind="warning">The page was refreshed while a review was running, so it stopped. Your pull request is restored below.<//>`}

        <div class="actions">
          <button type="button" class="btn primary" disabled=${!hasDiff || tooBig || !modelReady} aria-describedby=${hint ? ids.hint : undefined} onClick=${onAudit}>
            Audit pull request <${Arrow} />
          </button>
          <button type="button" class="btn" disabled=${!hasDiff || tooBig} onClick=${onStatic} title="Runs only the pattern rules. No model, no claim checking.">
            <${Rule} /> Static rules only
          </button>
          ${hint && html`<p class="help action-hint" id=${ids.hint}>${hint}</p>`}
        </div>
      </form>

      <aside class="compose-aside" aria-label="Examples and method">
        <section>
          <h2 class="section-title">Examples</h2>
          <p class="help">Diffs generated for this project. Choosing one fills the form.</p>
          ${samplesError && html`<${Notice} kind="danger">${samplesError}<//>`}
          ${!samples && !samplesError && html`<p class="help"><${Spinner} /> Loading examples…</p>`}
          ${samples &&
          html`<ul class="examples">
            ${samples.map((s) => {
              const current = loaded === s.id || (draft.source === s.repo && draft.title === s.title);
              return html`<li key=${s.id}>
                <button type="button" class="example" aria-current=${current ? "true" : undefined} onClick=${() => loadSample(s)}>
                  <span class="example-repo">${s.repo}</span>
                  <span class="example-title">${s.title}</span>
                  <span class="example-hint">${s.hint}</span>
                </button>
              </li>`;
            })}
          </ul>`}
        </section>

        <section>
          <h2 class="section-title">What the audit does</h2>
          <ol class="method">
            <li><b>Claims.</b> The title and description become checkable claims, including promises like “no behavior change”.</li>
            <li><b>Review.</b> Each excerpt of the diff is split into changes. Each change is matched to a claim or marked not mentioned.</li>
            <li><b>Check.</b> Every cited line is verified against the diff. Serious flags get a second pass that can withdraw them.</li>
          </ol>
        </section>
      </aside>
    </div>
  </div>`;
}
