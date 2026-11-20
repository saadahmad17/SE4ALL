# CLAUDE.md — project guidance

You are working on a research project. Read this fully, then read the other files
in the repo before doing anything: `README.md`, `extract_titles.py`,
`filter_metadata.py`, `extract_figures.py`. They already exist and are tested on
synthetic data — understand them before changing them.

## PROJECT COMPLETE (updated 2026-11-20) — read this first

**Repo reorganized 2026-11-20.** Everything below this point (including the dated
STATUS history) refers to the OLD flat layout (scripts and data all at repo root).
The repo is now: `scripts/` (all pipeline code), `data/` (every artifact), `paper/`
(self-contained, zip for Overleaf). File paths mentioned in the history below are
historically accurate but need a mental `scripts/` or `data/` prefix to find the file
today — see `README.md` for the current, correct commands for every stage. Also
removed as no-longer-needed: `ICSE2026.pdf` (580MB, fully processed into
`data/icse2026_titles.txt`), `labeling_tool.html` (31MB, superseded by the much
smaller `data/position_mapping.json` it was reduced to), and the two old `filter_*`/
superseded-v1 script and data files (assemble_references v1, flagged_input v1,
resolved_flagged v1) — the "v2" scripts were renamed to drop the suffix since they are
now simply the only version.

The full pipeline ran end-to-end: dataset → 500 model generations → 99 human-verified
references → 487 judge scores → charts → full paper draft, **plus a deeper "why do some
models hallucinate more" analysis added 2026-11-20**: all 327 hallucinated claims were
classified into 6 error types (misidentification, trend/direction reversal, miscount,
fabricated detail, ranking/comparison, numeric magnitude) via `scripts/categorize_errors.py`
→ `data/error_categories.jsonl` / `data/error_category_breakdown.json`. Real findings, not
speculation: misidentification dominates for every model (41-56% of its hallucinations);
Gemma-3-27B (worst overall) has both the highest misidentification share (56%) and
highest fabricated-detail share (11%) — concentrated weakness, not uniform badness;
Llama-4-Scout (best overall) also has the lowest fabricated-detail rate (8%) and writes
the shortest descriptions, consistent with a weak-but-real length/hallucination
correlation (Pearson r=0.17, n=487). This is now Fig.~\ref{fig:erroranalysis} panel (b)
in the paper, merged into one combined figure with the figure-type heatmap (panel a) to
save a float's worth of space against the 5-page limit — 3 figures total now, not 4.

**Only remaining step is human: fill in author/affiliation details in `paper/paper.tex`
and do a final compile + page-count check before submitting** (no LaTeX installed on
this machine — couldn't get sudo for a BasicTeX install, so the draft was never actually
compiled; a word-count-based page estimate turned out to be unreliable — one of my own
regexes double-counted/undercounted LaTeX-wrapped text inconsistently between two
checks — so don't trust any page-count number from this session, just compile it).

**Deadline note:** se4all.github.io (fetched 2026-11-20) showed the deadline EXTENDED to
20 Nov 2026 from the original 13 Nov — confirm this is still accurate if you're reading
this later, extension dates can themselves move.

**Final numbers** (full detail in the dated STATUS entries below): 195/322 ICSE titles
matched on arXiv → 639 figures extracted from 70 papers → 352 "good" pool → 100-figure
stratified eval sample → 500 model generations (5 models × 100 figures, 0 errors) → 99
human-verified reference descriptions (62 confirmed as-is, 37 corrected/verified via an
LLM-assisted resolution pass, 1 figure never reviewed and excluded) → 487/495 judge
scores (8 dropped after persistent parse failures). Headline result: hallucination rate
54.2%–86.6% across all 5 models including the closed baseline; an open-weight model
(Llama-4-Scout) beat GPT-4o on hallucination rate; charts were harder than diagrams for
4/5 models. Full numbers in `results_overall.json`, `results_by_type.json`.

**Deliverables:**
- `paper/paper.tex` — full draft, Abstract through Conclusion, needs author info + compile check
- `paper/figures/*.png` — the 3 charts used in the paper (dataviz-skill palette, validated)
- `data/reference_descriptions.jsonl`, `data/judged.jsonl`, `data/generations.jsonl` — full data trail
- `data/error_categories.jsonl`, `data/error_category_breakdown.json` — the error-taxonomy analysis
- `PROGRESS.md` — co-author-facing summary, also updated with final results
- `README.md` — fully rewritten, exact reproduce-each-stage commands for the new `scripts/`/`data/` layout

**If resuming to extend this work** (scaling to the full 352, fine-tuning dataset, more
papers): see "Scope decision" entries below for why this was deliberately NOT done yet,
and do the human-verified-references-alongside-generations pairing properly this time
(don't generate unverified model outputs for figures with no plan to get a reference).

---

## STATUS (updated 2026-11-10, ~evening) — original pipeline-build history, oldest first

**Deadline confirmed firm: 13 Nov 2026 (3 days from this update).** Scope confirmed with
user: ~100 figures, 4-5 open models, short-paper framing. See "Deviations from the
original plan" below — several things changed from the spec further down this file
after discussion with the user; those decisions are final, don't relitigate.

**Pipeline state:**
- Stage 0 (titles): DONE. `icse2026_titles.txt` has 322 clean titles. Fixed 3 real bugs
  in `extract_titles.py` while running on the real PDF (not just synthetic data): (1)
  `ANCHOR` regex required 3-5 digit page numbers, silently swallowing ICSE's pages 1-104
  (which have 1-2 digit page numbers) into one garbage blob — fixed to `\d{1,5}`. (2) PDF
  control chars (`\x08` before dot-leaders) were leaking into titles — now stripped in
  `clean_title()`. (3) Session-opener pages leak a lowercase roman-numeral running-footer
  prefix ("xiv HarnessLLM...") — now stripped via `ROMAN_PREFIX`/`ROMAN_VALID` regexes.
- Stage 1 (arXiv matching): DONE, but **not via `filter_metadata.py`/Kaggle snapshot**.
  New script `match_arxiv_api.py` queries the arXiv API per-title instead (322 small
  lookups vs. downloading+scanning a 5GB snapshot for only ~321 known titles — see
  deviation #1 below). Output: `selected.jsonl` (same schema `extract_figures.py`
  expects, so Stage 2 is unchanged). **195/322 matched (61%)**, well above the ~60
  stop-and-widen threshold. All matched papers show `license_tier: internal` (no
  explicit CC license) — expected and irrelevant since we release by-reference.
  Unmatched titles logged to `icse2026_nomatch.txt` (not chased further, we have surplus).
- Stage 2 (figure extraction): DONE for 70 papers (`figures/index.jsonl`, 639 rows).
  Fixed 3 more real bugs in `extract_figures.py`: (1) multi-panel figures (multiple
  `\includegraphics` in one `figure` env) were silently overwriting each other's saved
  file — fixed with a `_{j}` suffix. (2) custom LaTeX tool-name macros (e.g.
  `\newcommand{\toolname}{ProxyWar}`) were stripped to blank in captions — added
  `resolve_macros()` to expand simple zero-arg macros before parsing. (3) LaTeX explicit-
  space control sequences (`\ `) and escaped symbols (`\&` etc.) left dangling backslashes
  in cleaned text — added handling in `_clean()`. Also added `rasterize_to_png()`: ~97%
  of extracted images are vector PDF/EPS, which no multimodal API accepts, so every
  extracted image is now rendered to PNG at 200 DPI automatically.
  **352 "GOOD" figures** (latex-sourced + has caption + has image) out of 639 total —
  this is the candidate pool.
- Stage 3 (figure-type classification): DONE. `classify_figures.py` — heuristic
  keyword classifier (not a CV model, not worth the time) over caption+mentions.
  Categories: chart / diagram / mixed / **other** (qualitative examples, prompts, code
  screenshots — common in LLM4SE papers, CLAUDE.md's original chart-vs-diagram framing
  didn't anticipate this; user explicitly said to KEEP this category, not discard it).
  Output: `figures/index_typed.jsonl`.
- Sample selection: DONE. `select_sample.py` → `figures/sample.jsonl`, 100 figures,
  stratified to match the natural type proportions of the 352-pool: 38 chart / 23
  diagram / 5 mixed / 34 other. Seed=42, reproducible.
- Stage 5a (model generation): **DONE.** `generate_descriptions.py` called 5 models via
  OpenRouter (4 open: `qwen/qwen3-vl-8b-instruct`, `meta-llama/llama-4-scout`,
  `google/gemma-3-27b-it`, `mistralai/mistral-small-3.2-24b-instruct`; 1 closed baseline:
  `openai/gpt-4o`) on all 100 sample figures. **Models get ONLY the raw image, no
  caption/context** — deliberate, this is the actual capability under test (see
  deviation #4). Output: `generations.jsonl`, **500 rows (100×5), 0 errors, deduped**.
  Ran in two passes (OpenRouter account started with $0 real balance despite the key's
  `limit_usd` showing 100 — that field is a spend ceiling, not funds; see Credentials
  below) — this produced 159 duplicate rows across the two passes (resumability keys off
  rows already present in the output file, and something let ~32 figures' worth slip
  through and get redone; root cause not fully chased, not worth the time). **If you
  ever re-run this and resume from a partial file: dedupe by `(arxiv_id, fig_index,
  model)` afterward, don't assume `already_done()` caught everything.** Also: strip any
  `error`-flagged rows before resuming, or they're wrongly treated as done forever.
- Gold-set reference descriptions (Layer 2 ground truth): IN PROGRESS, needs user action.
  **Scope was widened from an initial 25-figure subset to the FULL 100-figure sample**
  (user's explicit call, after being told the tradeoff: more robust + full judge
  coverage later, vs. more human review time now). So the gold set and the eval sample
  are now the same 100 figures — `build_labeling_tool.py --n 100` covers all of them,
  not a subset (the `stratified_subset()`/`--n` machinery is still there but with
  `--n 100` it just returns everything in `figures/sample.jsonl`). `generate_draft_references.py`
  produces an LLM DRAFT per figure (image + caption/mentions as input — mimics how a
  human would read the paper, see deviation #5) using `anthropic/claude-sonnet-5`, saved
  to `draft_references.jsonl` (resumable, reuses drafts already made for the original 25
  before scoping up). **These drafts are unreviewed and must not be used as ground truth
  as-is.** `build_labeling_tool.py --drafts draft_references.jsonl --n 100` builds
  `labeling_tool.html` — a self-contained local HTML tool (images embedded as base64, no
  file-path dependencies; ~20MB at n=100, that's expected and fine) where the user
  reviews/edits each draft and must tick an explicit "reviewed & approved" checkbox
  before it counts (sidebar progress and JSON export both gate on this flag; storage key
  is `wcag_labels_v2` — bumped once already after a stale-cache bug where old empty
  saves from a pre-draft version of the tool blocked the new drafts from showing; if this
  ever happens again, bump the key again rather than debugging localStorage by hand).
  User may split the 100 figures across multiple people; each exports their own
  `reference_descriptions.jsonl` and they get merged (prefer `reviewed: true` entries,
  keyed on `arxiv_id`+`fig_index`).
  **Waiting on: user (and possibly collaborators) to actually do this labeling — now a
  bigger lift than originally planned (100 figures, not 25), budget time accordingly.**
  All 100 drafts generated cleanly (0 errors after one fix: a very large image,
  8134×4556px, got a 400 from Claude-via-OpenRouter even though all 5 production models
  accepted it fine — added defensive downscaling to max 2000px/side in
  `generate_draft_references.py`'s `to_data_uri()`; consider the same fix in
  `generate_descriptions.py` if it ever hits a similar wall). `labeling_tool.html` is
  31MB now (100 embedded images) — expected, still opens fine as a local file.
- Stage 5b (LLM-judge scoring): rubric FINALIZED (2026-11-11), script NOT YET WRITTEN.
  Will score each row of `generations.jsonl` against the matching human-approved
  reference (`reference_descriptions.jsonl`, only rows with `reviewed: true`) using
  `anthropic/claude-sonnet-5` as judge. Judge gets: the image + the human reference +
  the model's generated description (NOT the caption/mentions — judge should ground in
  the image itself, same as the model under test had to). Five criteria, scored with a
  short rationale per criterion so results are auditable (per CLAUDE.md's "spot-checked
  by the user" rule — don't skip this):
  1. **Factual accuracy** (1-5): do stated values/trends/structure match the figure?
  2. **Hallucination** (binary: present/absent + list the specific hallucinated
     claim(s) if any) — the headline safety metric, report as "% of descriptions with
     >=1 hallucination" per model.
  3. **Completeness** (1-5): does it cover what a BLV reader needs (structure + key
     data + takeaway), or omit important elements?
  4. **Message conveyed** (1-5): does it communicate *why the figure matters* in the
     paper's argument, not just literal visual facts?
  5. **Conciseness** (1-5, or flag too-verbose/too-terse/appropriate): WCAG-appropriate
     brevity without sacrificing the above.
  Deliberately NOT leading with BLEU/ROUGE (per original plan) — surface text-overlap
  metrics penalize valid paraphrases and don't catch hallucination, which is the actual
  failure mode this paper cares about.
- Paper: NOT STARTED.

**Credentials (already set up, don't ask the user to redo this):**
- arXiv API: no auth needed.
- Kaggle: `~/.kaggle/access_token` exists but is UNUSED (we abandoned the snapshot
  approach — see deviation #1). Harmless to leave.
- OpenRouter: key at `~/.openrouter/api_key` (chmod 600). Account has real funds now
  (topped up after an initial confusion where the user thought the key's `limit_usd: 100`
  field meant $100 of real credit — it doesn't, that's just a spend ceiling; actual balance
  is tracked separately via the `/credits` endpoint). Check balance before any large batch:
  `GET https://openrouter.ai/api/v1/credits` with the key as Bearer token.

**Deviations from the original plan below in this file (all discussed and agreed with
the user — don't revert without asking):**
1. Stage 1 uses `match_arxiv_api.py` (arXiv API, per-title query), NOT
   `filter_metadata.py` + the Kaggle snapshot. Reasoning: `--icse-only` mode only ever
   keeps rows matching ~321 known titles, so downloading/scanning the full 5GB arXiv
   corpus is wasted work vs. targeted queries. License info (the only thing the snapshot
   had that the API doesn't reliably give) doesn't matter for our release-by-reference
   strategy anyway. `filter_metadata.py` is still in the repo and still works if ever
   needed (e.g. widening scope to a full cs.SE corpus), just unused for now.
2. Model access is via OpenRouter (hosted inference), not local/offline. User's machine
   is an 8GB M3 Mac — genuinely cannot run even a small quantized VLM reliably alongside
   everything else, let alone 5 models x 100+ figures in the time available. "Open/local"
   in the paper's framing refers to the model weights being open and self-hostable by an
   adopting org (for their own privacy/cost reasons), not that this study literally ran
   them locally. A bonus local-feasibility check (e.g. moondream via Ollama) is optional,
   time-permitting, not a dependency.
3. Figure-type scope: kept "other" (qualitative examples/screenshots), did NOT narrow to
   just chart+diagram as initially recommended. User's call, final.
4. Model evaluation prompt gives ONLY the image, no caption/context — deliberate, this
   is what makes it a real test of vision capability instead of caption-paraphrasing, and
   matches the real accessibility use case (captions alone are already known insufficient).
   A context-included condition is a possible stretch-goal ablation later, not core.
5. Gold-set references are LLM-drafted (image + caption/mentions) then human-reviewed,
   NOT written from scratch, and NOT fully automated either. Fully-automated (LLM
   generates AND LLM judges, no human) was explicitly rejected as circular — it would
   remove the only real accuracy anchor and undermine the hallucination-rate claim the
   whole paper rests on. The human review/approval checkbox in `labeling_tool.html` is
   the line that must not be crossed/automated away.

**Known gotchas for whoever continues this:**
- OpenRouter model catalog changes fast; the 5 model IDs above were verified live against
  `GET /api/v1/models` on 2026-11-10 — if any 404, re-check the catalog rather than
  guessing a new ID from memory.
- `generate_descriptions.py` / `generate_draft_references.py` resumability both key off
  rows already present in the output file INCLUDING failed/errored ones — always strip
  `error`-flagged rows before resuming after a failure, or they'll be silently skipped
  forever.
- Draft generation needed `max_tokens=700` (not 400) to avoid mid-sentence truncation;
  14/25 initial drafts were cut off at 400 and had to be regenerated.
- The project directory is NOT a git repo (per environment info) — there's no commit
  history to lean on for "what changed when"; this STATUS section is the record.
- `README.md` is now slightly STALE — it still describes Stage 1 as the Kaggle-snapshot
  approach (`filter_metadata.py`). That's superseded by deviation #1 above. If this
  STATUS section and `README.md` ever disagree, trust this section, not the README.
- **Not yet done, carried over from the original plan, still outstanding:** confirm the
  actual page limit/format on se4all.github.io (IEEE IEEEtran, 10pt was assumed, never
  verified). Do this before drafting the paper.

## NEXT STEPS, in order

1. ~~Check generation harness finished cleanly.~~ **DONE** — `generations.jsonl` has
   500 rows (100 figures × 5 models), 0 errors, deduped. Nothing to do here.
2. ~~Get the human-reviewed gold set finished.~~ **91/100 DONE** (2026-11-19). The team
   reviewed via a Google Form instead of `labeling_tool.html`'s native export (that's
   fine, just meant the data needed reassembling — see below). `reference_descriptions.jsonl`
   now exists: 91 rows, all `reviewed: true`. Breakdown:
   - 79 figures: unanimous "accurate" verdict from the human reviewers → LLM draft
     promoted directly as final reference.
   - 12 figures: at least one reviewer flagged an issue. Each was resolved by
     re-prompting `anthropic/claude-sonnet-5` with the image + the current draft + the
     human's specific critique (`resolve_flagged.py`), asking it to judge whether the
     critique pointed to a genuine visual error (fix it) or was asking for non-visual
     analytical/background content the image doesn't actually show (keep the
     visual-description approach — this task is about describing what's visible, not
     restating the paper's analytical narrative). Verdict split: 5 genuine (corrected),
     7 narrative-bias (kept, with the model's reasoning logged). **These 12 rows have
     `needs_quick_check: true` in the output — worth a fast human skim before fully
     trusting them, since this was an LLM judging another LLM's critique-response,
     even though spot-checks during development (manually viewing the actual image for
     the trickiest case) confirmed the reasoning was sound.**
   - **9 figures still have NO human review at all** (never touched by anyone): listed
     in `still_missing.jsonl` — positions 49-55, 71, 76 in `labeling_tool.html`'s
     ordering, i.e. `(2601.03621,18) (2602.22764,11) (2602.06875,2) (2604.13693,5)
     (2507.14791,1) (2510.15079,7) (2601.02632,4) (2607.09054,6) (2601.12262,7)`.
     These need a first-pass review same as any other figure (drafts already exist in
     `draft_references.jsonl`) — the remaining real blocker before Stage 5b can run on
     the full 100.
   - Scripts added this pass: `resolve_flagged.py` (the correction-or-justify step) and
     `assemble_references.py` (merges Google Form responses + resolved flags +
     unanimous-yes drafts into `reference_descriptions.jsonl`; re-run this any time the
     underlying inputs change, e.g. after the last 9 get reviewed).
   **Scope decision (2026-11-11, still holds): do NOT scale generation or references
   beyond 100 right now** — generating unverified model outputs for the other 252
   figures with no plan to score them was explicitly considered and rejected as
   low-value busywork. Scaling to the full 352 (and using it for fine-tuning) is
   deferred to a post-submission phase and should be mentioned as future work in the
   paper itself.
3. **Write and run the Stage 5b LLM-judge script** (does not exist yet, this is the
   current critical path). `reference_descriptions.jsonl` has 91/100 rows ready right
   now — can run the judge on those 91 immediately without waiting for the last 9 to
   be reviewed; just re-run once those land. For each row in
   `generations.jsonl`, look up the matching reviewed reference in
   `reference_descriptions.jsonl` by `(arxiv_id, fig_index)` — skip rows with no
   reviewed reference yet. Judge with `anthropic/claude-sonnet-5` via OpenRouter
   (same key/pattern as `generate_descriptions.py`) on: factual accuracy of
   values/trends, hallucination rate (did it claim something not in the image/reference),
   completeness, whether the figure's message is conveyed, conciseness. Save to
   `judged.jsonl`. Per CLAUDE.md's original rule: spot-check a sample of judge scores
   with the user before trusting them fully — don't skip this.
4. **Build results tables**: per-model scores across the 5 criteria, broken down by
   `figure_type` (chart/diagram/mixed/other). This is the paper's results section.
5. **Qualitative error analysis**: pull concrete hallucination examples per model for
   the discussion/roadmap section.
6. **Confirm se4all.github.io's actual page limit/format** (see "outstanding" note
   above) — before, not after, drafting.
7. **Draft the paper**: problem → why open/local matters for accessibility →
   benchmark+protocol → results → roadmap. Cite real prior work (already named in
   "Rules" below: SciCap, ArXivCap/Multimodal ArXiv, SciFIBench, FigurA11y, Williams et
   al. 2022) and position against them — never fabricate a citation or number.

## File & script inventory

| File | Role |
|---|---|
| `extract_titles.py` | Stage 0. ICSE proceedings PDF → `icse2026_titles.txt` (322 titles) |
| `filter_metadata.py` | ORIGINAL Stage 1 (Kaggle snapshot). UNUSED now (deviation #1), kept in case scope ever widens to full cs.SE corpus |
| `match_arxiv_api.py` | ACTUAL Stage 1 used. arXiv API per-title query → `selected.jsonl` (195/322 matched) |
| `extract_figures.py` | Stage 2. Fetches arXiv LaTeX/PDF, extracts figures+captions+mentions, rasterizes to PNG → `figures/index.jsonl` |
| `classify_figures.py` | Stage 3. Heuristic figure-type classifier → `figures/index_typed.jsonl` |
| `select_sample.py` | Stratified 100-figure sample → `figures/sample.jsonl` (the eval set) |
| `generate_descriptions.py` | Stage 5a. Calls the 5 models via OpenRouter, image-only prompt → `generations.jsonl` |
| `generate_draft_references.py` | Drafts gold-set references via Claude Sonnet (image+caption/mentions) → `draft_references.jsonl` (UNREVIEWED) |
| `build_labeling_tool.py` | Generates `labeling_tool.html` (the human-review UI) |
| `labeling_tool.html` | The actual review tool — open in a browser, export → `reference_descriptions.jsonl` |
| `resolve_flagged.py` | For human-flagged figures: re-checks image + critique, fixes genuine errors or justifies keeping the draft → `resolved_flagged.jsonl` |
| `assemble_references.py` | Merges Google Form responses + resolved flags + unanimous-yes drafts → `reference_descriptions.jsonl` (re-run after the last 9 get reviewed) |
| *(not yet written)* | Stage 5b judge script — see NEXT STEPS #3 |

## Environment setup

- Python venv at `.venv` in the project root — **always** `source .venv/bin/activate`
  before running any script here.
- Installed: PyMuPDF (`fitz`), `requests`. Also `kaggle`/`kagglehub` (installed early on,
  turned out unused/non-functional with the newer `KGAT_` token format — harmless, just
  don't rely on them).
- Secrets: `~/.openrouter/api_key` (chmod 600, real funds loaded) and
  `~/.kaggle/access_token` (chmod 600, unused). Never echo these into chat/logs.
- Not a git repo. `ICSE2026.pdf` (607MB) sits at repo root for Stage 0 only; disk is
  tight (~19GB free) — safe to delete that PDF once Stage 0 output is confirmed good,
  if space is needed.

---


## Project
Build a small benchmark and run a study for a workshop paper: **"Can open-source
multimodal LLMs make software-engineering figures accessible?"** The accessibility
angle is the point — the target venue is **SE4ALL 2027** (International Workshop on
Software Engineering and AI for All), co-located with ICSE 2027, which treats
accessibility as a software-engineering problem. A generic "how well do models read
charts" benchmark is OFF-topic; the framing must be about generating descriptions of
SE-paper figures for blind and low-vision (BLV) readers, and whether locally-runnable
open models are good enough to do it (open/local matters for privacy and cost).

Deadline is tight (workshop submission **13 Nov 2026**) and this is a
position/emerging-ideas paper judged on the strength of the idea, not completeness.
Optimize for a lean, defensible result with a clear story, NOT a huge study. Confirm
the page limit/format on se4all.github.io (IEEE IEEEtran, 10pt) before writing.

## Dataset approach (already decided — don't relitigate)
Use ICSE 2026 papers that are available on arXiv. Pipeline:
- **Stage 0** `extract_titles.py` — titles from the ICSE 2026 proceedings PDF (TOC, ~first 50 pages)
- **Stage 1** `filter_metadata.py --icse-only` — match those titles against the arXiv
  metadata snapshot (Kaggle `Cornell-University/arxiv`), tagging licenses
- **Stage 2** `extract_figures.py` — pull figures + captions + in-text `explanation`
  from the arXiv LaTeX source (PDF fallback)

Copyright rule: **release BY REFERENCE** — publish arXiv id + figure index + our own
descriptions + the code, never the raw images. So all license tiers are usable. The
`README.md` has exact commands.

## Inputs to request from the user
- The ICSE 2026 proceedings PDF (for Stage 0).
- The arXiv metadata snapshot JSON (for Stage 1) — large download; if it's not present,
  tell the user and give the download command rather than guessing.

## What to do, with checkpoints (do NOT run everything blind)
1. Run Stages 0–1. **Report** how many of the ~321 ICSE titles matched on arXiv, and the
   license-tier breakdown. If the matched count is thin (say < ~60 papers), STOP and
   propose widening scope (add FSE/ASE 2025–26 or earlier ICSE years) before continuing.
2. Run Stage 2 on a `--limit 10` sample first. Show the user extracted figures +
   `explanation` fields for a quality check. Then scale.
3. **Scope decision — surface it, don't assume:** statistical charts, SE diagrams
   (architecture/UML/pipelines), or both? Add a figure-type pass over `index.jsonl`
   (light classifier/heuristic) so we can filter and report by type.
4. **Ground truth:** the extracted `explanation` (caption + in-text mentions) is good
   context but written for sighted readers. Build a short WCAG complex-image
   reference-description template and tooling to label a small gold set (the user labels;
   you build the tooling).
5. **Evaluation harness:** evaluate 3–4 open-source multimodal LLMs (e.g. a Qwen-VL, an
   InternVL, a LLaVA-family model) plus one closed baseline, generating a description per
   figure. Score on accessibility-relevant criteria: factual accuracy of values/trends,
   **hallucination rate** (key failure mode), completeness, whether the figure's message
   is conveyed, conciseness. Use an LLM-as-judge against the reference + rubric,
   spot-checked by the user. Don't lead with BLEU/ROUGE.
6. **Produce:** `index.jsonl` (the by-reference dataset), the eval scripts, a results
   table per model and per figure-type, and a qualitative error analysis with examples.
   Then draft the paper (problem → why open/local for accessibility → benchmark+protocol
   → results → roadmap).

## Rules
- Prefer the LaTeX source over PDFs for extraction (clean captions + mentions).
- Be polite to arXiv (the script already sleeps between requests); don't hammer it.
- Never fabricate figures, numbers, or citations. Cite real prior work: SciCap,
  ArXivCap / Multimodal ArXiv, SciFIBench, FigurA11y, Williams et al. 2022 (alt text in
  HCI figures). Position against them — our novelty is SE-specific figures +
  accessibility-graded evaluation + open/local models.
- Keep everything reproducible: pin versions, save prompts, log model outputs.
- Ask before any irreversible or large/expensive step; otherwise proceed and report at
  each checkpoint above.

**This closing instruction is now superseded** — both inputs (ICSE2026.pdf, and the
decision to skip the arXiv snapshot entirely) have already been resolved; see the STATUS
and NEXT STEPS sections at the top of this file, which are authoritative over everything
below this point. If you're starting fresh: read STATUS first, then NEXT STEPS, then come
back to the rest of this file only for background on the original design rationale.
