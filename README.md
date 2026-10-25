# PR Checker

**Finds the changes a pull request makes but doesn't mention.**

PR Checker audits a pull request against its own description. An open-weight model running locally (Qwen3-8B via Ollama) turns the description into atomic claims, reads the diff excerpt by excerpt, and maps every atomic change to the claim that explains it, or marks it as *unmentioned*. Deterministic code checks every citation against the real diff, a second skeptical model pass re-examines each serious flag, and the verdict is computed by code, not by the model.

Built for the MLH Hacktoberfest Hack Day, **Best Open-Source AI Project** challenge.

---

## The problem

Maintainers review pull requests by reading the description first and the diff second. The description sets their expectations, and a change that falls outside those expectations is easy to miss. That's the gap attackers and careless contributors slip through:

- A "pure refactor" that also extends session lifetime from 1 hour to 30 days and drops `httpOnly` from the session cookie.
- A one-word README typo fix that adds a `postinstall` script shipping `process.env` to a base64-hidden host.
- A "CI caching" PR that switches the workflow to `pull_request_target`, checks out the PR author's code, and hands it the npm publish token (a "pwn request").
- During Hacktoberfest, a flood of low-effort PRs that need fast, fair triage.

**Who it's for:** open-source maintainers and reviewers who want a second reader that checks *intent against implementation*, without sending private code to a third-party API.

**Why existing tools fall short:** linters, SAST tools and secret scanners match patterns. They catch `curl | sh`, but they can't know that `60 * 60` → `60 * 60 * 24 * 30` contradicts a PR that promised "no behavior change". That judgment requires reading natural-language intent and code together, which is what a language model is good at.

## What the model does, and what code does

| Step | Done by | What happens |
| --- | --- | --- |
| Parse | code | Unified diff → files, hunks, line numbers ([src/pr_checker/diff.py](src/pr_checker/diff.py)). Files classified (source, test, CI, manifest, lockfile, docs…). |
| Static rules | code | 20 pattern rules (install hooks, runtime base64 decode, `pull_request_target`, untrusted checkout, CI secrets, TLS disabled, bidi/invisible Unicode, credentials…) ([src/pr_checker/signals.py](src/pr_checker/signals.py)). They're the **baseline** and are passed to the model as hints. |
| Excerpts | code | Hunks are windowed into ≤70-line excerpts; whitespace-only hunks, lockfiles and binaries skip the model ([src/pr_checker/units.py](src/pr_checker/units.py)). |
| **Claims** | **model** | Title + description → ≤6 atomic claims, typed `change` or `constraint` ("no behavior change", "only fixes a typo"). |
| **Review** | **model** | Per excerpt: split into atomic changes; for each, cite the lines, describe it, classify its effect, say which claim covers it, which claim it breaks, and how worrying it is. Output is constrained to a JSON schema. |
| Grounding | code | Every cited line number is mapped back to the real diff. Citations of unchanged or non-existent lines are dropped; a finding that can't be grounded is never escalated ([src/pr_checker/grounding.py](src/pr_checker/grounding.py)). |
| Moved code | code | Lines removed in one place and added unchanged in another are detected, like `git diff --color-moved`, including the braces and lightly edited signatures of a moved block ([src/pr_checker/moved.py](src/pr_checker/moved.py)). The model is told which lines moved, and a change made of moved lines can't count as a behavior change. |
| Guards | code | The model reads language; code applies logic. Each claim is tagged with an area (docs, tests, CI, build, dependencies, code) and a claim can only cover changes in files of that area. A promise like "only fixes a typo in the README" is broken by any change outside docs, and a `docs:`, `test:` or `ci:` title adds that promise even if the description doesn't. "No behavior change" is broken by behavior changes to existing files, never by new helpers or tests. A claim about tests needs a change in a test file. Unmentioned behavior and security changes get minimum concern levels the model can't lower. Promises are only enforced when the author's own words make them ("no behavior change", "docs-only"); the model can't invent one. A behavior change the description announces doesn't count against "no other behavior change". Test-file changes are credited to a claim like "adds tests". |
| **Self-check** | **model** | A second, skeptical pass (one batched call per excerpt) agrees or disagrees with the first pass. It re-examines (a) every serious flag, which can be *withdrawn*, and (b) every "covered" change that a static rule fired on or that is security-relevant, which can be *overturned*. Rules and model cross-check each other. |
| Verdict | code | Claims ledger, findings, disclosure ratio, line coverage, risk, and verdict are computed deterministically ([src/pr_checker/score.py](src/pr_checker/score.py)). |

Nothing is a canned response: every annotation on screen comes from a live model call on the diff you supplied, and the UI shows the pipeline's real progress.

## Model

| | |
| --- | --- |
| Model | **Qwen3-8B** (`qwen3:8b` in Ollama: Q4_K_M GGUF, 8.19B parameters, 5.2 GB) |
| Publisher | Qwen team, Alibaba Cloud ([model card](https://huggingface.co/Qwen/Qwen3-8B)) |
| License | **Apache-2.0**, open weights (verified on the Hugging Face model card and the Ollama library page) |
| Mode | Non-thinking (`think: false`), temperature 0, JSON-schema-constrained decoding |
| Runtime | [Ollama](https://github.com/ollama/ollama) (MIT), fully local |

**Open weights vs. open source:** Qwen3's weights are published under Apache-2.0, which permits commercial use, modification and redistribution. The training data and full training pipeline are not published, so it's an *open-weight* model rather than a fully open-source one in the OSI sense. PR Checker itself is MIT-licensed.

**Why this model:** I benchmarked the models available locally on an M4 / 16 GB machine with a real audit prompt. `gemma4:e2b` was ~5× faster but called a 1-hour → 30-day session TTL change "a configuration change, not a behavior change". Qwen3-8B correctly identified it as contradicting the "pure refactor" claim. Correct judgment matters more than speed here, so Qwen3-8B is the default. Any Ollama model with structured-output support can be swapped in via `PR_CHECKER_MODEL`.

## Architecture

```
 Browser (plain JavaScript modules + Preact, no build step; served by the Python app)
   │  POST /api/analyze  ──►  NDJSON event stream (parsed → claims → unit results → self-checks → report)
   ▼
 API server (FastAPI + uvicorn, Python)
   ├─ diff.py / classify.py / units.py      deterministic parsing and excerpting
   ├─ signals.py                            static-rule baseline
   ├─ pipeline.py                           orchestration, bounded concurrency, cancellation
   │     ├─ prompts.py + schema.py          claims · review · self-check · review-comment prompts and output schemas
   │     └─ ollama.py                       /api/chat with JSON-schema `format`, timeouts, one retry
   ├─ grounding.py                          citation verification + line coverage
   ├─ score.py                              verdict, claims ledger, findings, baseline comparison
   └─ github.py                             optional import of public PRs (title, body, .diff)
   ▼
 Ollama (local)  ──  qwen3:8b
```

- No database, queue, or vector store: an audit is a single streamed request, and the server is stateless.
- Model output is untrusted. It's schema-constrained, validated against the same JSON schema, retried once if malformed, grounded against the diff, and post-processed by deterministic guards.
- The PR text and diff are treated as data inside the prompt. Nothing the model outputs is executed.

## Running it

**Requirements:** Python ≥ 3.9, [Ollama](https://ollama.com) ≥ 0.6, about 6 GB of free RAM.

```bash
ollama pull qwen3:8b
```

For faster audits, let Ollama serve several requests at once (PR Checker sends up to 3 in parallel; this gave ~1.4× throughput on an M4):

```bash
OLLAMA_NUM_PARALLEL=3 ollama serve
```

Then:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
python -m pr_checker
```

Open http://localhost:8787. The model status in the top-right turns green when Ollama and the model are ready. One process serves the UI and the API; there is no separate build step. Use `python -m pr_checker --reload` while developing, and `--port` (or `PORT`) to change the port.

### Configuration

Copy `.env.example` to `.env` (read from the working directory) or export variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama server |
| `PR_CHECKER_MODEL` | `qwen3:8b` | Model for review and self-check |
| `PR_CHECKER_CLAIMS_MODEL` | `PR_CHECKER_MODEL` | Model for claim extraction |
| `PR_CHECKER_CONCURRENCY` | `3` | Parallel model calls (match `OLLAMA_NUM_PARALLEL`) |
| `PR_CHECKER_TIMEOUT_MS` | `180000` | Per-call timeout |
| `PORT` | `8787` | Port for the app (UI and API) |
| `GITHUB_TOKEN` | — | Optional; raises the GitHub API limit for URL imports from 60 to 5,000/hour |
| `PR_CHECKER_DEBUG` | — | Log timing and token counts for each model call |

No API keys are required.

### Tests and evaluation

```bash
pip install -e ".[dev]"
pytest                          # unit and API tests: diff parsing, rules, excerpting, grounding, scoring, endpoints
python scripts/eval.py          # live model run over the bundled samples, scored against ground truth
python scripts/eval_real.py     # live model run over real, honest public PRs: checks for false alarms
```

`python scripts/eval.py` runs the real pipeline on each bundled sample and checks whether each **planted** undisclosed change was flagged (severity ≥ medium, surviving self-check), counts false flags, compares against the static rules alone, and checks the verdict. Results are written to `eval/results.json` and shown in the app.

**Latest run** (`eval/results.json`, 2026-10-25, run with the Python pipeline, `qwen3:8b`, M4 / 16 GB, `OLLAMA_NUM_PARALLEL=3`):

| Sample | What's planted | Verdict | Model caught | Rules caught (warn+) | False flags | Flags withdrawn by self-check | Time |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `refactor-session` | 30-day session TTL, `httpOnly` removed, `sameSite` weakened, inside a "pure refactor" | contradicts ✓ | 3/3 | 0/3 | 0 | 3 | 144 s |
| `typo-postinstall` | `postinstall` hook, base64-hidden host, `process.env` exfiltration, in a typo fix | contradicts ✓ | 3/3 | 3/3 | 0 | 0 | 39 s |
| `ci-cache` | `pull_request_target`, untrusted checkout, npm token exposed, in a caching PR | undisclosed ✓ | 2/3 | 3/3 | 0 | 0 | 49 s |
| `dark-mode` | nothing; the description claims tests that aren't in the diff | overclaims ✓ | — | — | 0 | 0 | 63 s |
| `readme-spam` | nothing; a low-effort README edit | trivial ✓ | — | — | 0 | 0 | 20 s |

**Totals:** verdicts correct 5/5 · planted changes flagged by the model **8/9**, by static rules alone 6/9, by either (what the app shows) **9/9** · false flags 0.

The three security changes in the refactor sample are invisible to the static rules at warning level; only the model's reading of "no behavior change" against the diff catches them. The model's one miss (the untrusted checkout in `ci-cache`) is caught by a static rule, which is why both run together. Results vary somewhat between runs: earlier prompt versions scored lower, and on the current prompts the model's results (8/9 caught, 0 false flags, 5/5 verdicts) were identical across the last two full runs. Five hand-built samples are a sanity check, not a benchmark.

**Real pull requests** (`python scripts/eval_real.py`, `eval/real-results.json`). Planted samples measure what PR Checker catches; real PRs measure false alarms. The fixtures are honest, merged PRs from MIT-licensed projects, imported with the app's GitHub importer:

| PR | What it does | Verdict |
| --- | --- | --- |
| [axios/axios#11062](https://github.com/axios/axios/pull/11062) | Moves a duplicated helper into a shared module; announces one small behavior change | Does what it says ✓ |
| [sindresorhus/got#2454](https://github.com/sindresorhus/got/pull/2454) | Bug fix with regression tests | Does what it says ✓ |
| [expressjs/express#7483](https://github.com/expressjs/express/pull/7483) | `docs:` PR that also edits a runtime error message in `lib/` | Contradicts (medium), shown for information |

Before the fixes in this version, both honest PRs were wrongly reported as "Contradicts its own description": the claims model invented promises the authors never made, and a helper moved to a new file looked like deleted code. The express result is a judgment call: the `docs:` title promises documentation only, and the PR changes a string users see at runtime, but the title also says "(lib + example)".

## Demo (about 90 seconds)

1. **The hook.** Open the app. *"Linters catch `curl | sh`. They can't tell you that a pure refactor quietly changed session security."*
2. **The refactor sample** (`northwind/ledger-api`). Choose it in the examples list, then click **Audit pull request**. Point at the pipeline: claims appear first (*"No behavior change"* is extracted as a promise), then excerpts are reviewed live and the progress rail counts them off. (It takes about 3 minutes on a 16 GB M4; for a faster live demo, open with **typo-postinstall**, about 50 s, and show the refactor from a finished run.)
3. **The verdict:** *Contradicts its own description.* Click the session-lifetime finding: the diff scrolls to `SESSION_TTL_SECONDS = 60 * 60 * 24 * 30`, highlighted in red, with the note *breaks C4*. Point at the cookie change (`httpOnly` removed, `sameSite` weakened).
4. **Why AI.** Point at *Static rule warnings: 0* and the line *"serious findings matched no static rule"*. Pattern matching found nothing here.
5. **Honesty.** Open *flags withdrawn on second look*: the model's own false alarms (e.g. removing helpers that were moved) were withdrawn by the second pass, with reasons.
6. **Act on it.** Click **Draft a review comment**. A courteous, specific comment streams in, ready to paste.
7. *(If time allows)* Run **ci-cache** to show the rule-vs-model cross-check overturning a "covered" judgment on `pull_request_target`, or **dark-mode** to show an honest PR whose "includes tests" claim isn't backed by the diff.

Every sample is a real `git diff` generated by [scripts/build_samples.py](scripts/build_samples.py) from the before/after file trees in [samples/](samples/). You can also paste any diff or import a public PR by URL.

## Design

The interface is a review desk, not a dashboard: a neutral light theme (with a dark one that follows the OS setting), IBM Plex Sans for the UI, IBM Plex Mono for code and identifiers, and IBM Plex Serif only for the verdict headline and the PR title. Color is reserved for meaning: concern level (red, amber, gray), covered changes (green), diff additions and deletions, links and focus. There are no gradients, shadows or decorative graphics, and nothing on screen is computed anywhere but from the current run (or `eval/results.json`).

The first screen is the input. A finished review reads top to bottom: verdict, findings, then the annotated diff, with the claims list in a side rail. Every finding links to the lines it cites. Typed input and finished reviews survive a refresh (per tab, in `sessionStorage`).

**Maintaining it**

- [design.md](design.md) is the specification: palette with hex values and usage rules, type scale, spacing, components with every state, motion, responsive and accessibility rules, and a permanent list of forbidden patterns. Read it before changing the UI.
- [src/pr_checker/web/css/tokens.css](src/pr_checker/web/css/tokens.css) is the only place color, type-size, spacing, radius and layout values are defined. Component rules in [styles.css](src/pr_checker/web/css/styles.css) refer to tokens; they never contain hex values. To retheme, change tokens, not components.
- Before merging a UI change, walk the review checklist at the end of `design.md` (tokens only, color means something, every state present, works at 320 / 768 / 1280 px in both themes, keyboard-operable, respects reduced motion, specific copy).
- Check the three viewports and both themes with the browser's device emulation and the `prefers-color-scheme` / `prefers-reduced-motion` switches in dev tools.

## Known limitations

- **Speed.** On an M4 with 16 GB, Qwen3-8B generates ~13 tokens/s. A small PR takes 20–75 s; the 5-file refactor sample takes 2.5–3.5 minutes. A GPU or a larger Apple Silicon machine is much faster.
- **The model can be wrong.** It sometimes stretches a vague claim to cover a change, or flags harmless code. The self-check and rule cross-check reduce this but don't eliminate it. Treat PR Checker as a second reader, not an approval gate.
- **Excerpt-local reasoning.** Each excerpt is reviewed with the PR's claims but without the rest of the repository, so effects that only show up across files can be missed.
- **Scale limits.** Diffs over 600 KB are refused; at most 40 excerpts per PR go to the model (the rest are marked as skipped). Lockfiles and binary files get static checks only.
- **Evaluation is small.** Five hand-built samples and three real PRs are a sanity check, not a benchmark. Model output also varies somewhat from run to run.
- **GitHub import** uses the public REST API (60 requests/hour unauthenticated) and only reads; PR Checker never posts to GitHub.

## Project layout

```
src/pr_checker/            the Python package
  server.py, __main__.py   HTTP API + web UI server, `python -m pr_checker`
  pipeline.py, prompts.py, schema.py, ollama.py, score.py, ...   the audit
  web/                     the UI: plain JavaScript modules (Preact + htm, vendored), css/tokens.css holds every color, size and space value
  data/samples.json        bundled sample PRs (built from samples/)
samples/     before/after file trees and ground truth for each sample PR
design.md    design specification for the UI
scripts/     sample builder, evaluation harness
tests/       unit and API tests (pytest)
eval/        latest evaluation results
inference.py standalone Hugging Face Transformers demo of Qwen3-8B (not used by the app)
```

## License

MIT for this project. Qwen3-8B is © Alibaba Cloud under Apache-2.0. Ollama is MIT.
