// Everything here is best-effort: storage can be full, blocked or disabled, and the app must work without it.
const DRAFT = "pr-checker:draft";
const REVIEW = "pr-checker:review";
const RUNNING = "pr-checker:running";
const MAX_CHARS = 2_500_000;

function read(key) {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function write(key, value) {
  try {
    const raw = JSON.stringify(value);
    if (raw.length > MAX_CHARS) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, raw);
  } catch {
    /* quota or access error: skip */
  }
}

function drop(key) {
  try {
    sessionStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

export const loadDraft = () => read(DRAFT);
export const saveDraft = (d) => (d.title || d.description || d.diff ? write(DRAFT, d) : drop(DRAFT));

export const loadReview = () => read(REVIEW);
export const saveReview = (s) => write(REVIEW, s);
export const clearReview = () => drop(REVIEW);

/** True when the previous page load was refreshed in the middle of a review. Reads and clears the marker. */
export function wasInterrupted() {
  const was = read(RUNNING) === true;
  drop(RUNNING);
  return was;
}
export const markRunning = (on) => (on ? write(RUNNING, true) : drop(RUNNING));
