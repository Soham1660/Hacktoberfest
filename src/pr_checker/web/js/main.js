import { html, render } from "../vendor/preact-htm.js";
import { App } from "./app.js";

render(html`<${App} />`, document.getElementById("root"));
