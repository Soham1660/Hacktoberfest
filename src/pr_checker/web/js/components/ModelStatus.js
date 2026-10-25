import { html } from "../../vendor/preact-htm.js";
import { Spinner } from "./ui.js";

export function ModelStatus({ health, onRetry }) {
  if (!health)
    return html`<p class="model-status" role="status"><${Spinner} /> Checking the model…</p>`;
  if (health.ok)
    return html`<p class="model-status" title=${`Served by Ollama at ${health.host}`}>
      <span class="dot ok" aria-hidden="true" />
      <span class="mono">${health.model}</span>
      <span aria-hidden="true">·</span>
      <span>runs locally</span>
    </p>`;
  return html`<p class="model-status" role="status">
    <span class="dot bad" aria-hidden="true" />
    <span>${health.ollama ? `Model ${health.model} is not installed` : "Ollama is not running"}</span>
    <button type="button" class="link-btn" onClick=${onRetry}>Recheck</button>
  </p>`;
}
