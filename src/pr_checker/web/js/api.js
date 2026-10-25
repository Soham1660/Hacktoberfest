export class ApiError extends Error {}

async function json(res) {
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(body?.error ?? `Request failed (${res.status})`);
  return body;
}

async function request(path, init) {
  try {
    return await fetch(path, init);
  } catch {
    throw new ApiError("Can't reach the PR Checker server. Is `python -m pr_checker` running?");
  }
}

const post = (path, body, signal) =>
  request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });

export const getHealth = async () => json(await request("/api/health"));
export const getSamples = async () => json(await request("/api/samples"));
export const getSample = async (id) => json(await request(`/api/samples/${encodeURIComponent(id)}`));
export const importGitHub = async (url) => json(await post("/api/github", { url }));
export const staticScan = async (pr) => json(await post("/api/scan", pr));

/** Streams newline-delimited JSON events from the analysis endpoint. */
export async function analyze(pr, onEvent, signal) {
  const res = await post("/api/analyze", pr, signal);
  if (!res.ok) await json(res);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (line) onEvent(JSON.parse(line));
    }
  }
}

/** Streams the drafted review comment as plain text. */
export async function draftComment(body, onText, signal) {
  const res = await post("/api/comment", body, signal);
  if (!res.ok) await json(res);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    onText(decoder.decode(value, { stream: true }));
  }
}
