import { useCallback, useEffect, useReducer, useRef } from "../vendor/preact-htm.js";
import { analyze, ApiError, staticScan } from "./api.js";
import { clearReview, loadReview, markRunning, saveReview } from "./persist.js";

// Stage ids: parse | claims | review | verify | report. Stage status: pending | active | done | skipped.
// Unit state: pending | active | done | error.

const freshStages = () => ({
  parse: { status: "pending" },
  claims: { status: "pending" },
  review: { status: "pending" },
  verify: { status: "pending" },
  report: { status: "pending" },
});

/** mode: idle | running | done | error | static. `restored` is true when a finished review was read back from the tab's session storage after a refresh. */
const initial = {
  mode: "idle",
  pr: null,
  parsed: null,
  model: null,
  claims: [],
  changes: [],
  units: {},
  unitErrors: {},
  verifying: [],
  stages: freshStages(),
  report: null,
  error: null,
  startedAt: null,
  elapsedMs: null,
  restored: false,
};

function init() {
  const saved = loadReview();
  return saved && saved.mode === "done" && saved.parsed && saved.report ? { ...saved, restored: true } : initial;
}

function reducer(s, a) {
  switch (a.type) {
    case "reset":
      return initial;
    case "start":
      return { ...initial, mode: "running", pr: a.pr, startedAt: Date.now(), stages: { ...freshStages(), parse: { status: "active", startedAt: Date.now() } } };
    case "static":
      return { ...initial, mode: "static", pr: a.pr, parsed: a.parsed };
    case "fail":
      return { ...s, mode: "error", error: a.message, verifying: [] };
    case "event":
      return applyEvent(s, a.e, a.at);
    default:
      return s;
  }
}

function applyEvent(s, e, at) {
  switch (e.type) {
    case "parsed": {
      const units = {};
      for (const u of e.data.units) if (u.mode === "model") units[u.id] = "pending";
      return { ...s, parsed: e.data, model: e.model, units, stages: { ...s.stages, parse: { ...s.stages.parse, status: "done", endedAt: at } } };
    }
    case "stage": {
      const prev = s.stages[e.stage];
      const next = e.status === "start" ? { status: "active", startedAt: at } : { ...prev, status: "done", endedAt: at };
      const stages = { ...s.stages, [e.stage]: next };
      // The self-check stage only runs when something was flagged.
      if (e.stage === "report" && e.status === "start" && stages.verify.status === "pending") stages.verify = { status: "skipped" };
      return { ...s, stages };
    }
    case "claims":
      return { ...s, claims: e.claims };
    case "unit_start":
      return { ...s, units: { ...s.units, [e.unitId]: "active" } };
    case "unit_result":
      return { ...s, units: { ...s.units, [e.unitId]: "done" }, changes: [...s.changes, ...e.changes] };
    case "unit_error":
      return { ...s, units: { ...s.units, [e.unitId]: "error" }, unitErrors: { ...s.unitErrors, [e.unitId]: e.message } };
    case "verify_start":
      return { ...s, verifying: [...s.verifying, e.changeId] };
    case "verify_result":
      return {
        ...s,
        verifying: s.verifying.filter((id) => id !== e.changeId),
        changes: s.changes.map((c) => (c.id === e.changeId ? e.change : c)),
      };
    case "report":
      return { ...s, report: e.report };
    case "error":
      return { ...s, mode: "error", error: e.message, verifying: [] };
    case "done":
      return { ...s, mode: "done", elapsedMs: e.elapsedMs };
    default:
      return s;
  }
}

export function useAnalysis() {
  const [state, dispatch] = useReducer(reducer, undefined, init);
  const abortRef = useRef(null);

  useEffect(() => {
    markRunning(state.mode === "running");
    if (state.mode === "done" && !state.restored) saveReview(state);
    else if (state.mode !== "done") clearReview();
  }, [state]);

  const run = useCallback(async (pr) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    dispatch({ type: "start", pr });
    let finished = false;
    try {
      await analyze(
        pr,
        (e) => {
          if (e.type === "done" || e.type === "error") finished = true;
          dispatch({ type: "event", e, at: Date.now() });
        },
        ctrl.signal,
      );
      if (!finished && !ctrl.signal.aborted) dispatch({ type: "fail", message: "The server closed the connection before the review finished." });
    } catch (err) {
      if (ctrl.signal.aborted) return;
      dispatch({ type: "fail", message: err instanceof ApiError ? err.message : `Unexpected error: ${err.message}` });
    }
  }, []);

  const runStatic = useCallback(async (pr) => {
    abortRef.current?.abort();
    try {
      dispatch({ type: "static", pr, parsed: await staticScan(pr) });
    } catch (err) {
      dispatch({ type: "fail", message: err.message });
    }
  }, []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    dispatch({ type: "fail", message: "Review cancelled." });
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    dispatch({ type: "reset" });
  }, []);

  return { state, run, runStatic, cancel, reset };
}
