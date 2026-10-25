# PR Checker: design specification

This file is the source of truth for the interface. `src/pr_checker/web/css/tokens.css` implements the values below; `src/pr_checker/web/css/styles.css` implements the components. If code and this file disagree, fix one of them in the same change.

---

## 1. What the product is

PR Checker compares a pull request's **description** with its **diff**. It extracts the claims the author makes, finds each atomic change in the diff, and marks every change that no claim explains or that a claim contradicts. A maintainer uses it as a second reader before approving a PR.

**The user** is an open-source maintainer or reviewer, often triaging a pile of PRs. They read diffs all day. They are skeptical of AI output and want to check it, not trust it.

**The job** is: give it a PR, wait one to three minutes, then see which lines don't match the description, with evidence that can be checked against the diff.

**The workflow** has one path:

1. *Provide* a PR: title, description, diff. By paste, file upload, public GitHub URL, or a bundled example.
2. *Run* the audit. It streams for 20 seconds to a few minutes.
3. *Read the verdict*, then the findings, then the claims ledger.
4. *Check the evidence* in the annotated diff. Every finding links to the lines it cites.
5. *Optionally draft* a review comment to copy. Nothing is posted anywhere.

### What the previous interface got wrong

- The first screen was an explanatory essay ("How it works", three numbered steps, an eval blurb) with the actual input squeezed into a narrow side column. A tool should open on its input.
- The source picker was three tabs, but the title/description/diff form stayed visible under all three, so the tabs controlled nothing visible.
- Every section opened with the same small-caps eyebrow label (`kicker`). It is a formula, not hierarchy.
- The same finding was written out in full three times: the sidebar, the findings list, and the inline diff note.
- Decorative details: a vermilion `[` bracket on the wordmark, a lock icon in the footer, a pseudo-handwritten italic serif for system messages ("Reading the pull request…"), a scanning-line animation over diff hunks.
- A stat strip that mixed meaningful numbers (disclosure, line coverage) with run metadata (model calls) at the same weight.
- The diff was built from `div role="row"` without cells, which is not valid table semantics, and the layout relied on horizontal overflow.
- Typefaces (Instrument Sans, Newsreader italics) were chosen for mood. The page followed the OS theme only and defaulted to a near-black brown in dark mode.
- A refresh discarded the user's typed PR.

---

## 2. Design philosophy

**A review desk, not a dashboard.** The interface should feel like the tools maintainers already use for code review: dense, quiet, text-first, built around the diff. It borrows the legibility of good editorial design (a serif for the one headline that matters, generous line height for prose) and the discipline of developer tools (monospace only for code and identifiers, no ornament).

**Evidence over assertion.** Anything the interface says about a change must be one click from the lines it concerns. Numbers that can't be explained in a tooltip don't get shown.

**Color is reserved for meaning.** The page is neutral. Color appears only for: concern level, covered/not covered, diff additions and deletions, links, and focus. Buttons are not colored to look exciting.

**Dense where the work is, calm everywhere else.** The diff and findings are compact. The compose screen and verdict get room to breathe. No section exists to fill space.

**Honest about state.** Running, queued, failed, withdrawn and skipped are all shown as they are, with text. Findings are marked provisional until the self-check finishes. Nothing is faked to make the screen look finished.

**Light first.** The default is a restrained light theme (paper-like neutral, not white). A dark theme exists and follows `prefers-color-scheme`. Both come from the same tokens. There is no theme switcher: the OS setting is the preference.

---

## 3. Color

All colors are defined once as CSS custom properties in `src/pr_checker/web/css/tokens.css`. No hex value appears in `styles.css` or in a component.

### Neutrals

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `--bg` | `#F6F5F2` | `#141413` | Page background |
| `--surface` | `#FFFFFF` | `#1C1C1A` | Panels, inputs, the diff, finding cards |
| `--surface-sunk` | `#EFEEEA` | `#232321` | Table headers, code gutters, hunk headers, disabled fields |
| `--border` | `#DAD8D1` | `#34342F` | Dividers and panel outlines |
| `--control-border` | `#8A877D` | `#7A776E` | Borders of inputs and buttons (3:1 against surface) |
| `--text` | `#1A1A18` | `#ECEBE6` | Primary text, headings, code |
| `--text-2` | `#4A4842` | `#C0BEB5` | Secondary text: descriptions, explanations |
| `--text-3` | `#66635B` | `#9A978E` | Metadata, labels, placeholders, line numbers. Minimum 4.5:1 on every surface it appears on |

### Interactive

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `--link` | `#1D4F9F` | `#8AB4F8` | Text links, focus ring, selected-state outline |
| `--primary` | `#1A1A18` | `#ECEBE6` | Fill of the one primary button on a screen |
| `--on-primary` | `#FFFFFF` | `#141413` | Text on the primary button |

There is no brand accent color. The primary action is the darkest thing on the page; that is enough.

### Semantic

Each semantic color has a text color (`-text`), a tinted background (`-bg`) and a border (`-line`). Text on its own tint must reach 4.5:1; every pair below was checked.

| Meaning | `-text` light / dark | `-bg` light / dark | `-line` light / dark | Where it appears |
| --- | --- | --- | --- | --- |
| High concern, errors (`--danger`) | `#B42318` / `#FF9B8F` | `#FCEBE9` / `#3A1E1B` | `#E8B4AE` / `#6B3A35` | High-concern findings and diff markers, "contradicts", the model-unavailable state, failed steps, error alerts |
| Medium concern, caution (`--warning`) | `#7A4800` / `#EBC06A` | `#FBF0DB` / `#33280F` | `#E3C98E` / `#665021` | Medium-concern findings, partial citations, static-rule warnings |
| Covered, success (`--success`) | `#1E6B3A` / `#7FD097` | `#E7F3EA` / `#16301F` | `#AED3B9` / `#2F5C3D` | Changes the description explains, kept promises, finished steps, model ready |

Low concern uses neutral colors (`--text-2` on `--surface-sunk`). Low is information, not an alarm.

### Diff colors

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `--add-bg` | `#E6F4EA` | `#17301E` | Added line background |
| `--add-gutter` | `#CFE9D7` | `#1F4029` | Line-number cells of added lines |
| `--del-bg` | `#FBE9E7` | `#361C19` | Removed line background |
| `--del-gutter` | `#F4CFCB` | `#4A2622` | Line-number cells of removed lines |

### Rules

- **One color axis per meaning.** Concern level (high/medium/low) is the only thing that colors a finding. *Status* ("Not mentioned", "breaks C4") is a text chip in neutral colors, never a different hue. The only tinted chips are `sensitive path` and rule hits, which are cautions about the file or line, not about the finding.
- **Never color alone.** Every color has a text label, a glyph or a number next to it. A colorblind reader loses nothing.
- Red and amber are for things the reviewer should look at. If the PR is fine, the screen has no red or amber on it.
- Do not add colors. If a new state needs one, reuse a semantic color or use neutrals.

---

## 4. Typography

The IBM Plex family: one superfamily with three members, each with a distinct role. It was designed for technical interfaces, is legible at small sizes in dark and light, and has a monospace that sits well beside its sans. Fonts are self-hosted through Fontsource; nothing loads from a third-party CDN.

| Role | Family | Used for |
| --- | --- | --- |
| Display | IBM Plex Serif 600 | The verdict headline and the PR title in the review header. Nowhere else. |
| UI and body | IBM Plex Sans 400 / 500 / 600 | Everything that is not code or the display roles |
| Code and identifiers | IBM Plex Mono 400 / 500 | Diff lines, file paths, claim and change IDs (`C1`, `U3.1`), model name, line references |

Fallbacks: `ui-sans-serif, system-ui, sans-serif` / `Georgia, serif` / `ui-monospace, "SF Mono", Menlo, monospace`. Font files use `font-display: swap`.

### Scale

| Token | Size / line height | Weight | Tracking | Used for |
| --- | --- | --- | --- | --- |
| `--fs-display` | 28px / 34px (24px / 30px under 640px) | Serif 600 | -0.01em | Verdict headline |
| `--fs-title` | 24px / 30px (22px / 28px under 640px) | Serif 600 | -0.005em | PR title; compose page heading |
| `--fs-heading` | 16px / 24px | Sans 600 | 0 | Section headings (Findings, Claims, Diff) |
| `--fs-body` | 15px / 22px | Sans 400 | 0 | Body text, form values |
| `--fs-small` | 13px / 19px | Sans 400 or 500 | 0 | Secondary text, chips, buttons, labels, table metadata |
| `--fs-code` | 13px / 20px | Mono 400 | 0 | Diff and inline code |
| `--fs-meta` | 12px / 16px | Sans 500 or Mono 400 | 0.01em | Counters, line numbers, timestamps |

Rules:

- There are no uppercase eyebrow labels and no letter-spaced small caps. Sections are introduced by a real heading.
- Body prose never exceeds 72 characters per line (`max-width: 68ch`).
- Numerals in tables, line numbers and timers use tabular figures (`font-variant-numeric: tabular-nums`). Mono ligatures are disabled.
- Italics are used for quotations from the PR description only.

---

## 5. Layout and spacing

### Spacing scale

`--space-1` 4px · `--space-2` 8px · `--space-3` 12px · `--space-4` 16px · `--space-5` 24px · `--space-6` 32px · `--space-7` 48px

Only these values are used for padding, margin and gap. Component-internal optical adjustments of 1 to 7px (icon-to-text gaps, chip padding, aligning a marker to a line box) are allowed; layout-level spacing is not.

### Page frame

- **Maximum width:** 1240px, centered. **Page margins:** 24px from 640px up, 16px below.
- **Header:** 56px, bottom border, no shadow. Wordmark at left, model status at right. It scrolls away with the page.
- **Footer:** one line of plain text on the privacy model, 24px above and below.
- **Section spacing:** 32px between major blocks on a page, 16px between a heading and its content.

### Compose screen (nothing run yet)

Two columns from 1024px up: the PR form (`minmax(0, 1fr)`) and a 320px aside holding the examples list and a three-line explanation of what the audit produces. Nothing else goes in the aside: no statistics, no setup instructions. Below 1024px the aside stacks *above* the form's fields but below the page heading, so the examples are reachable without scrolling past the whole form.

Order inside the form: GitHub import row · Title · Description · Diff (with byte count and upload) · actions.

### Review screen (running, done, or stopped)

- **PR header:** source (mono), PR title (serif), the author's description as a quotation (clamped to four lines with a *Show full description* toggle), and the actions at the right (*Cancel review* while running; *Run again* and *New audit* otherwise). Not sticky.
- **Main column** (`minmax(0, 1fr)`): verdict → draft-comment action → findings → diff.
- **Rail** (320px, sticky, from 1024px up): progress steps while running (collapsed into a `details` once finished), then the claims list. Rail sections are separated by 1px rules, not boxed.
- Under 1024px the rail sits between the verdict and the findings, in one column.

### Corners and borders

- Radii: `--radius-sm` 3px (chips, inline code) · `--radius` 4px (buttons, inputs) · `--radius-lg` 6px (panels, the diff). Nothing larger. No fully round shapes except the 8px status dot and the spinner.
- Panels are a 1px `--border` outline on `--surface`. Dividers inside panels are 1px `--border`.
- **Shadows: none.** Hierarchy comes from borders, spacing and weight. (The focus ring is the only added outline.)

### Control size

Standard control height is **36px**. On coarse pointers (`@media (pointer: coarse)`) controls and tappable rows are at least **44px** high.

---

## 6. Components

All states below are required; a component isn't done until each is implemented.

### Buttons

- **Primary** (one per screen: *Audit pull request*): `--primary` fill, `--on-primary` text, 36px, 0 16px, 4px radius, weight 600. Hover: 88% opacity of fill via `color-mix`. Disabled: `--surface-sunk` fill, `--text-3` text, no pointer events, `cursor: not-allowed`. A disabled button is only used where a real restriction exists (no diff, model unavailable), and the reason is printed next to it.
- **Secondary:** `--surface` fill, 1px `--control-border`, `--text`. Hover: `--surface-sunk`.
- **Link button:** `--link` text, underlined on hover and focus. Used for low-emphasis actions (Upload a file, Redraft, Recheck).
- Busy state replaces the label ("Importing…") and shows the spinner; width does not shift.
- Icons are inline SVG at 16px in `currentColor`, always paired with a text label.

### Form controls

- Labels sit above the control, `--fs-small` weight 500, `--text`. Helper text sits below, `--text-3`.
- Inputs and textareas: `--surface` fill, 1px `--control-border`, 4px radius, 36px high (textareas resize vertically only). Placeholder is `--text-3` and is an example, never the only label.
- Focus: border becomes `--link` and a 2px `--link` outline offset by 1px. (All focusable elements share the same ring.)
- Invalid / over-limit: border `--danger-text` and an error message below in the same color with a leading glyph. The message says what limit was exceeded.
- The diff textarea uses the mono font at `--fs-code`.

### Header model status

A status dot (8px) plus text: "qwen3:8b · runs locally" with a success dot when ready; "Ollama is not running" or "Model qwen3:8b is not installed" with a danger dot and a *Recheck* link button when not. The dot is never the only indicator: the words change too. Polls every 8 seconds only while unavailable.

### Example list

A bordered list; each row is a full-width button with the repo (mono, `--text-3`), title (`--fs-body`, weight 500) and one line of context. The loaded example gets `aria-current="true"`, a 3px `--link` left bar and a `--surface-sunk` background. Rows are 56px+ high.

### Alerts (inline notifications)

A single-row panel: glyph, message, optional action (for example *Try again*). Danger / warning / success tints from section 3. `role="alert"` for errors that follow a user action, `role="status"` otherwise. They appear where the problem is (under the field, above the actions, in place of the diff), never as floating toasts. Messages state what happened and what to do next.

### Progress steps

The five pipeline steps are a vertical list: glyph (pending ○, active spinner, done ✓, skipped –, failed ✕), label, detail text ("2 of 3 excerpts"), elapsed time. Active step is weight 600. While reviewing, a row of small squares (one per excerpt) shows pending/active/done/failed using fill *and* shape (done = filled, failed = crossed). On completion the list collapses into `<details>` titled "How this review ran".

### Verdict

A panel with a 4px left edge in the risk color (neutral when risk is low or none). Contents: risk label with glyph ("High risk", "No risk found"), the headline in `--fs-display` serif, a summary paragraph, then a row of three facts (Disclosed, Lines accounted for, Static-rule warnings), each a `dt`, a number and a one-line plain explanation printed under it. Explanations are visible text, not tooltips. A baseline sentence appears only when the model found something no static rule did. While running it reads "Review in progress", names how many changes are provisionally flagged, and has no facts.

### Findings

One bordered panel holding an ordered list; findings are rows separated by 1px rules, not separate cards. Each row: a footnote badge (the same filled badge used beside the code, in the concern color, links to the diff line), concern word (High / Medium / Low) with glyph, one neutral chip (`breaks C4` for contradictions, otherwise the status), the one-sentence description, the reason, the self-check line, and the location button (`src/auth/session.ts:12`). The left edge is 3px in the concern color. Withdrawn findings live in a `details` below, struck through, with the model's reason for withdrawing.

Empty state (finished, nothing flagged): "Every change traces back to a claim in the description." with a link to the claims ledger.

### Claims ledger

An ordered list in the rail. Each claim: ID (mono), text, a "promise" chip when it is a constraint such as "no behavior change", then its result with glyph (Found in diff / Kept / Not in diff / Broken) and links to the changes that support it. Pending claims say "Checking…".

### Diff

- File header: a button (`aria-expanded`) with chevron, path (mono), the file's status only when it is not `modified`, category, `sensitive path` flag, and `+N −N`. Lockfiles start collapsed.
- Each hunk is a real `<table>` inside a bordered container. Columns: marker (28px) · old line (44px) · new line (44px) · sign (20px) · code. The old-line column is hidden below 640px.
- Code wraps (`white-space: pre-wrap; overflow-wrap: anywhere`), so there is never horizontal scrolling inside the diff and annotations stay aligned.
- Marker column: the finding's footnote number on its first line; a 3px left bar in the concern color (flagged) or `--success-text` (covered). Lines that were changed but never cited by the model get a small hollow marker with a tooltip, "Not attributed to any change".
- Annotations sit in a full-width row after the last line of each change. Flagged changes show number, one-line description and one neutral chip (`breaks C4` or the status). Covered changes show a one-line summary and `covers C1`, never both "Covered" and "covers". Longer reasoning lives in the findings list, not here.
- Static-rule hits appear on their line as a chip with a flag glyph.
- Invisible and bidirectional Unicode characters are rendered as `U+200B` style tokens in `--warning` colors.
- Navigating from a finding scrolls the line to the center and tints it with `--link` at 30%, fading out over 1.2 seconds.
- A one-sentence legend above the files explains the markers. It is plain text, not a key of colored badges. Anything the screen already shows (restored-from-refresh state, model readiness) is stated once, in the lightest form that works, not as a banner.
- A "Flagged files only" checkbox filters the file list.

### Draft review comment

A secondary button below the verdict: "Draft a review comment". After it is pressed the comment streams into a bordered panel with a mono-free, prose font; *Copy* and *Redraft* are in the panel header. The helper text states that nothing is posted.

### Loading and empty states

- Loading is always tied to work in progress: a spinner beside the words that name the work ("Importing…", "Self-check running…"). No skeleton screens, no fake progress bars.
- Every empty state tells the user the next action: no diff yet → "Paste a diff, upload a file, or pick an example"; no flagged files; no claims.

---

## 7. Motion

Motion communicates a state change or draws the eye to the result of a user action. It is never ambient.

| Where | What | Duration |
| --- | --- | --- |
| Spinner | Rotation, indicates ongoing work | 800ms linear, infinite |
| Hover / focus on controls | Background and border color | 120ms ease-out |
| New findings and notes appearing while streaming | Opacity 0→1 | 160ms |
| "Go to line" highlight | Background tint fades | 1200ms |
| Chevron on a file header | Rotation, 0 to 90° | 120ms |
| Details open/close | None (native) | — |

Not allowed: parallax, scroll-triggered reveals, count-up numbers, pulsing glows, typing effects, shimmer skeletons, sliding panels.

`@media (prefers-reduced-motion: reduce)`: all transitions and animations are set to `none`; the spinner is replaced by a static ring with a text label ("working"); the line highlight stays as a static tint and is removed after 1.3s by script.

---

## 8. Responsive behavior

| Width | Behavior |
| --- | --- |
| **< 640px** (mobile) | Single column, 16px margins. Verdict headline 24px. Facts stack in one column. The old-line column is hidden in the diff and the gutters narrow (30px marker, 36px numbers). The finding's number sits above its text instead of beside it. PR-header actions become a full-width row. Example hints are hidden. All tap targets ≥ 44px. |
| **640–1023px** (tablet) | Single column, 24px margins. Rail content sits between verdict and findings. Examples list above the form. |
| **≥ 1024px** (desktop) | Two columns (main + 320px rail on review; form + 320px aside on compose). Rail is sticky with its own scroll if taller than the viewport. |

Nothing may cause horizontal page scroll at 320px. Long paths and identifiers wrap (`overflow-wrap: anywhere`). No region scrolls horizontally.

---

## 9. Accessibility

- Semantic landmarks: `header`, `main`, `footer`, `aside`/`nav` where applicable; one `h1` per view; headings do not skip levels. A "Skip to main content" link is the first focusable element on every screen.
- Every control has a visible label or `aria-label`. Required and error states are announced via `aria-invalid` / `aria-describedby`.
- Every interactive element has a visible `:focus-visible` ring: 2px solid `--link`, 2px offset. Never `outline: none` without a replacement.
- Keyboard: all actions are native `button`, `a`, `input`, `summary`. File sections toggle with Enter/Space. No keyboard trap; there are no modal dialogs in this product. If one is ever introduced it must trap focus, close on Escape and return focus to its opener.
- Live regions: the verdict and progress detail use `aria-live="polite"`; errors use `role="alert"`. Streaming diff changes are not announced individually.
- Contrast: body text ≥ 4.5:1, large text and UI borders ≥ 3:1, in both themes. Verified values live in the tables above.
- Color is never the only signal (see section 3).
- Motion respects `prefers-reduced-motion` (section 7).
- Tables carry `<caption class="sr-only">` naming file and hunk; header cells are visually hidden but present.

---

## 10. Persistence and state

- The title, description and diff the user typed survive a refresh (stored in `sessionStorage`, size-capped, failure ignored).
- A finished review is also kept in `sessionStorage` and restored on refresh, with a notice "Restored from this tab after a refresh. Nothing was re-run." A review that was *running* at refresh is not restorable (the stream is gone); the draft is restored on the compose screen with a notice.
- Nothing is stored on a server or sent anywhere beyond the local API and, for GitHub imports, GitHub.

---

## 11. Forbidden patterns

This list is permanent. Reject any change that reintroduces one.

**Visual**
- Gradients of any kind: backgrounds, borders, text, buttons.
- Glow, blur, glassmorphism, drop shadows used for depth.
- Decorative blobs, particles, grids, noise, abstract shapes.
- More than one radius larger than 6px on screen. Cards inside cards inside cards.
- Emojis or Unicode symbols as icons. All icons are the SVGs in `src/pr_checker/web/js/components/icons.js`.
- Colored buttons other than the neutral primary. Colored headings, colored icons for decoration.
- A dark theme "because it's AI". Dark is a user preference served by the OS setting only.

**Content**
- A marketing hero, taglines as headlines, oversized slogans, two big CTAs.
- Rows of identical icon-heading-blurb cards. Repeating one section formula down the page.
- Fake terminals or code used as decoration. Fake testimonials, customer counts, trust badges, logos, unsupported statistics.
- Any number on screen that is not computed from this run or from `eval/results.json`.
- Generic AI copy: "unlock", "supercharge", "revolutionize", "seamless", "powerful", "the future of". Copy is plain, specific and written for a maintainer.
- Charts, activity feeds or widgets with no decision attached to them.
- Large empty regions that exist only to look like a landing page.

**Interaction**
- Auto-typing text, blinking cursors, looping animation that is not a spinner.
- Motion on page load, on scroll, or on hover that isn't a state change.
- A disabled control with no stated reason.
- Toasts for errors the user must act on.

**Code**
- Hex or `oklch()` literals outside `tokens.css`. Pixel spacing outside the scale.
- Inline `style` attributes for design values.
- New component abstractions for something used once.

### Review checklist for any UI change

1. Does it use only tokens? Search the diff for `#` and `px` values not on the scale.
2. Is anything colored that isn't concern, coverage, diff or focus?
3. Does every state exist: default, hover, focus, active, disabled, loading, empty, error?
4. Is it usable at 320px, 768px and 1280px, and in both themes?
5. Can it be operated with the keyboard alone, and does it announce correctly?
6. Does it respect `prefers-reduced-motion`?
7. Does the copy say something specific, or could it appear on any AI product's site?
8. Would a maintainer miss it if it were removed? If not, remove it.
