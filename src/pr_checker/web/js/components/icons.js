import { html } from "../../vendor/preact-htm.js";

const icon = (paths) => (p = {}) =>
  html`<svg
    width="16"
    height="16"
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    class=${p.class}
  >
    ${paths()}
  </svg>`;

export const Check = icon(() => html`<path d="M3.5 8.5l3 3 6-7" />`);
export const Cross = icon(() => html`<path d="M4 4l8 8M12 4l-8 8" />`);
export const Flag = icon(() => html`<path d="M3.5 14V2.5M3.5 3h8l-1.8 3 1.8 3h-8" />`);
export const Question = icon(() => html`<path d="M6 6a2 2 0 1 1 2.8 1.8c-.5.3-.8.7-.8 1.2v.5M8 12h.01" />`);
export const Strike = icon(() => html`<path d="M2.5 8h11M5 4.5h6M5 11.5h6" />`);
export const Copy = icon(() => html`
  <rect x="5.5" y="5.5" width="8" height="8" rx="1.5" />
  <path d="M10.5 5.5V3.8c0-.7-.6-1.3-1.3-1.3H3.8c-.7 0-1.3.6-1.3 1.3v5.4c0 .7.6 1.3 1.3 1.3h1.7" />
`);
export const Upload = icon(() => html`<path d="M8 10.5V2.5M5 5.5l3-3 3 3M2.5 10.5v2a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-2" />`);
export const Arrow = icon(() => html`<path d="M3 8h10M9 4l4 4-4 4" />`);
export const Chevron = icon(() => html`<path d="M6 4l4 4-4 4" />`);
export const Rule = icon(() => html`<path d="M2.5 4.5h11M2.5 8h7M2.5 11.5h9" />`);
export const Alert = icon(() => html`<path d="M8 2.2l6.2 11H1.8L8 2.2zM8 6.6v3M8 11.8h.01" />`);
export const Info = icon(() => html`
  <circle cx="8" cy="8" r="6" />
  <path d="M8 7.4V11M8 5h.01" />
`);
export const Ring = icon(() => html`<circle cx="8" cy="8" r="4.5" />`);
export const Dash = icon(() => html`<path d="M4.5 8h7" />`);
