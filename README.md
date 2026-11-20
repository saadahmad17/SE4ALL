# SE figure-accessibility benchmark

Can open-source multimodal LLMs generate accessible descriptions of software-engineering
figures for blind/low-vision readers? This repo is the full pipeline: dataset
construction from ICSE 2026 papers on arXiv, a 5-model evaluation (4 open-weight + 1
closed baseline), human-verified reference descriptions, LLM-judge scoring, and the
resulting paper draft. Released **by reference** (arXiv id + figure index + our
descriptions + code — never the raw images), so copyright isn't a blocker regardless
of each source paper's license.

See `CLAUDE.md` for full build history, every bug fixed along the way, and every
scope/design decision with its rationale. See `PROGRESS.md` for a results-focused
summary. This file is the "how to reproduce each stage" reference.

## Layout

```
scripts/   all pipeline code, run from the repo root
data/      every dataset artifact this pipeline produces (and the raw human-review input)
paper/     self-contained — zip this folder and upload to Overleaf
```

## Environment

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install PyMuPDF requests openpyxl matplotlib
```
Secrets expected at `~/.openrouter/api_key` (chmod 600) — needed for Stages 5a/5b/6/7
(OpenRouter-hosted model calls). arXiv stages (0-2) need no auth.

## Stage 0 — titles from the ICSE proceedings

```bash
python3 scripts/extract_titles.py --pdf <proceedings.pdf> --first 1 --last 50 \
  --out-titles data/icse2026_titles.txt --out-csv data/icse2026_toc.csv
```
322 titles extracted. Eyeball the output once — track-name prefixes and page-folio
bleed-through are the known artifacts; Stage 1's matching tolerates minor noise.

## Stage 1 — match to arXiv

```bash
python3 scripts/match_arxiv_api.py --icse-titles data/icse2026_titles.txt \
  --out data/selected.jsonl --nomatch-log data/icse2026_nomatch.txt
```
Per-title arXiv API query (not the full Kaggle snapshot — for ~322 known titles a
targeted query beats downloading/scanning the whole corpus). 195/322 matched (61%).
`scripts/filter_metadata.py` (the original snapshot-based approach) is kept for the
scenario where scope widens to a full cs.SE corpus scan, but is unused here.

## Stage 2 — figure extraction

```bash
python3 scripts/extract_figures.py --manifest data/selected.jsonl --out-dir data/figures \
  --prefer-tier any --limit 70 --pdf-fallback --sleep 5
```
Pulls LaTeX source first (PDF fallback), mines captions + `\ref`-referencing paragraphs,
rasterizes every image to PNG (vector PDF/EPS otherwise rejected by vision APIs). 639
figures from 70 papers → `data/figures/index.jsonl`.

## Stage 3 — figure-type classification

```bash
python3 scripts/classify_figures.py --index data/figures/index.jsonl --out data/figures/index_typed.jsonl
```
Heuristic keyword classifier (chart / diagram / mixed / other — "other" covers
qualitative examples, prompts, code screenshots, common in LLM4SE papers; kept
deliberately, not discarded).

## Stage 4 — evaluation sample

```bash
python3 scripts/select_sample.py --index data/figures/index_typed.jsonl --n 100 --out data/figures/sample.jsonl
```
Stratified sample (seed=42) from the 352 "good" figures (real caption + real image +
clean LaTeX source), matching the pool's natural type proportions.

## Stage 5a — model generation

```bash
python3 scripts/generate_descriptions.py --sample data/figures/sample.jsonl \
  --figures-dir data/figures --out data/generations.jsonl
```
5 models (4 open-weight + GPT-4o baseline), **image only, no caption/context** — this
is deliberate, see CLAUDE.md "deviation #4". 500 generations, 0 errors.

## Stage 5b — human-verified reference descriptions

```bash
# 1. LLM drafts a starting point (image + caption/mentions, mimics how a sighted
#    reader of the paper would understand the figure)
python3 scripts/generate_draft_references.py --sample data/figures/sample.jsonl \
  --figures-dir data/figures --out data/draft_references.jsonl --n 100

# 2. Build the review tool (self-contained HTML, images embedded, ships to reviewers)
python3 scripts/build_labeling_tool.py --sample data/figures/sample.jsonl \
  --figures-dir data/figures --out labeling_tool.html --n 100 --drafts data/draft_references.jsonl
# reviewers use this in a browser; we collected feedback via a Google Form instead of
# the tool's native JSON export -- see data/raw_feedback/

# 3. Route reviewed figures to direct-promote vs. needs-resolution
python3 scripts/parse_feedback.py

# 4. For anything flagged: re-examine image + the specific human critique together,
#    separating genuine visual errors (fixed) from requests for non-visual analytical
#    content (kept as-is -- describing only what's visible is correct for this task)
python3 scripts/resolve_flagged.py --flagged data/flagged_input.jsonl \
  --figures-dir data/figures --out data/resolved_flagged.jsonl

# 5. Merge into the final reference set
python3 scripts/assemble_references.py
```
99/100 human-verified references (1 figure was never reviewed by anyone, excluded).

## Stage 6 — LLM-judge scoring

```bash
python3 scripts/judge_descriptions.py --generations data/generations.jsonl \
  --references data/reference_descriptions.jsonl --figures-dir data/figures --out data/judged.jsonl
```
Judge sees image + human reference + the candidate description, scores 5 criteria
(accuracy, hallucination, completeness, message-conveyed, conciseness). 487/495 scored
cleanly (8 dropped after persistent parse failures on retry).

## Stage 7 — results and error analysis

```bash
python3 scripts/results_summary.py          # per-model / per-figure-type tables
python3 scripts/make_charts.py              # paper/figures/*.png
python3 scripts/categorize_errors.py        # taxonomy of hallucination types -> data/error_categories.jsonl
```

## The paper

`paper/paper.tex` is self-contained (needs only `paper/figures/*.png`, already there) —
zip the `paper/` folder and upload to Overleaf. Still needs: real author/affiliation
info (currently `[FILL IN]` placeholders) and a compile/page-count check (no LaTeX
available in the build environment this was drafted in).

## Copyright, one line

Evaluate on anything; redistribute only CC0/CC-BY/CC-BY-SA images, OR (what we do)
release by reference and ship no images at all.
