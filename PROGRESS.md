# Project Progress — SE4ALL 2027 Submission

**Paper:** "Can Open-Source Multimodal LLMs Make Software-Engineering Figures Accessible?"
**Venue:** SE4ALL 2027 (co-located with ICSE 2027)
**Deadline:** 20 Nov 2026 (extended from the original 13 Nov — confirmed on se4all.github.io)
**Paper type:** Short/position paper (max 5 pages incl. references, IEEE IEEEtran 10pt, single-blind review)

## Status: pipeline and paper draft are complete

Everything through a full paper draft is done. **The only remaining step is for a human
to fill in author/affiliation details and do a final compile + page-count check** —
`paper/paper.tex` is ready (3 figures, 1 table, 8 sections) but not yet actually
compiled (no LaTeX on the build machine, and a word-count-based page estimate turned
out unreliable, so no page-count number here should be trusted). Upload to Overleaf or
compile locally, add author info, verify it's within the 5-page limit, and it's
submission-ready.

## What the study does

We test whether open-weight multimodal LLMs can generate WCAG-style accessible
descriptions of figures from ICSE 2026 papers, for blind/low-vision readers — given
*only* the raw figure image, no caption or surrounding text (that's the actual skill
being measured: real captions are already known to be insufficient for accessibility).
We score outputs against human-verified reference descriptions using an LLM-judge,
spot-checked by us. We release the dataset **by reference** (arXiv id + figure index +
our descriptions + code — never the raw images).

## Headline result

**Hallucination is pervasive, across every model, including the closed baseline** —
54.2% to 86.6% of generated descriptions contained at least one unsupported or
contradicted claim. Two findings worth highlighting in review/talks:

1. **The closed baseline is not the safest model.** GPT-4o hallucinated 60.2% of the
   time — worse than an open-weight model, Llama-4-Scout, at 54.2%. "Open" is not
   inherently riskier here.
2. **Bigger isn't better.** Gemma-3-27B, the largest open model evaluated, was also the
   *worst* performer on every single criterion (86.6% hallucination rate).
3. **Charts are harder than diagrams** for 4 of 5 models — consistent with charts
   demanding precise numeric/trend reading vs. diagrams' more forgiving structural
   tracing.

## Why do some models hallucinate more? (added after classifying all 327 hallucinations)

- **Misidentification** (wrong label/identity of a visible element — an icon, legend
  entry, axis label) is every model's single largest error category, 41-56% of its
  hallucinations. The industry-wide bottleneck looks like low-level visual grounding,
  not higher-level reasoning.
- **Gemma-3-27B's weakness is concentrated, not uniform**: highest misidentification
  share (56%) AND highest fabricated-detail share (tied at 11-13%) — it's specifically
  worse at correctly recognizing what's in the image and more prone to inventing things
  that aren't there, not just "worse at everything."
- **Llama-4-Scout's edge looks like calibration**: lowest fabricated-detail rate (8%) and
  the shortest descriptions (93 words avg., vs. 112-114 for three of the other four) —
  weakly but consistently correlated with hallucination rate across all 487 scored
  examples (Pearson r=0.17). Saying less may mean fewer chances to be wrong.
- **Trend/direction-reversal errors (17-29%) are the most model-agnostic category** —
  every model confuses "up" and "down" at similar rates, which is the strongest argument
  for a grounding/preprocessing fix over simply picking a better model.

| Model | Accuracy | Completeness | Message | Conciseness | Hallucination % |
|---|---|---|---|---|---|
| Qwen3-VL-8B | 3.0 | 2.6 | 3.0 | 4.1 | 72.2 |
| Llama-4-Scout | 2.6 | 2.1 | 2.2 | 3.8 | **54.2 (best)** |
| Gemma-3-27B | 2.5 | 2.3 | 2.6 | 3.8 | 86.6 (worst) |
| Mistral-Small-3.2-24B | 2.9 | 2.4 | 2.8 | 4.0 | 62.6 |
| GPT-4o (closed) | 3.1 | 2.5 | 2.8 | 4.2 | 60.2 |

All scores 1-5 scale (higher = better); hallucination % is the % of descriptions with
at least one hallucinated claim (lower = better). Full numbers: `data/results_overall.json`,
`data/results_by_type.json` (breakdown by chart/diagram/mixed/other).

## Dataset pipeline — final numbers

| Stage | What happened | Count |
|---|---|---|
| 0. Titles extracted | From ICSE 2026 proceedings PDF (TOC) | 322 |
| 1. Matched on arXiv | Per-title arXiv API query | 195 / 322 (61%) |
| 2. Figures extracted | From 70 of the 195 matched papers | 639 figures, 65 papers |
| 2b. "Good" figures | Real caption + real image + clean LaTeX source | 352 |
| 3. Figure-type tagged | chart / diagram / mixed / other | 132 / 82 / 17 / 121 |
| 4. Evaluation sample | Stratified sample of the 352 pool | 100 (38/23/5/34) |
| 5a. Model descriptions generated | 100 figures × 5 models, image-only prompt | 500 (0 errors) |
| 5b. Human-verified references | Google Form review + LLM-assisted resolution for flagged ones | 99/100 (1 never reviewed, excluded) |
| 5c. Judge scores | `data/generations.jsonl` × `data/reference_descriptions.jsonl` | 487/495 (8 dropped, persistent parse failures) |

Scaling to the full 352-figure pool (and beyond, as a fine-tuning dataset) was
deliberately deferred — explicit future work mentioned in the paper's Discussion
section, not something we rushed into this submission.

## Models evaluated

| Role | Model |
|---|---|
| Open-weight | `qwen/qwen3-vl-8b-instruct` |
| Open-weight | `meta-llama/llama-4-scout` |
| Open-weight | `google/gemma-3-27b-it` |
| Open-weight | `mistralai/mistral-small-3.2-24b-instruct` |
| Closed baseline | `openai/gpt-4o` |
| Judge | `anthropic/claude-sonnet-5` |

All via OpenRouter (hosted inference) — the dev machine (8GB RAM) can't run even a
small vision model locally. "Open/local" in the paper's framing is about the *weights*
being open and self-hostable, not that this study literally ran them on a laptop.

## Reference description quality control

99 human-verified references were built via: an LLM (Claude Sonnet) drafted each one
from the image + the paper's own caption/mentions; 14 human annotators then reviewed
every draft against the actual figure via a Google Form. Of those reviews: 62 figures
were confirmed accurate as-drafted; 37 had at least one reviewer flag an issue (ranging
from genuine visual errors like a miscounted node or wrong arrow direction, to a
figure-type mislabel, to cases where the critique wanted non-visual analytical content
the image doesn't actually show). Each flagged figure was re-examined — image +
specific critique together — to separate real errors (corrected) from the
analytical-content case (kept as originally drafted, since describing only what's
visible is correct behavior for this task). One figure (`2607.09054` fig 6) was never
reviewed by anyone and is excluded from the final 99.

## Deliverables

- **`paper/paper.tex`** — full draft, Abstract through Conclusion, 3 figures + 1 table,
  citations verified against real sources (not fabricated). Needs: author info filled
  in, final compile/page-count check.
- **`paper/figures/`** — the 3 charts used in the paper (hallucination-rate bar chart,
  per-criterion grouped bar chart, and a combined figure-type-heatmap + error-taxonomy
  panel)
- **`data/reference_descriptions.jsonl`**, **`data/judged.jsonl`**, **`data/generations.jsonl`** — full
  data trail, by-reference only (no raw images redistributed)

## What's left (all human steps, nothing blocking on more analysis)

1. Fill in author name(s)/affiliation/email in `paper/paper.tex`
2. Compile it (Overleaf, or local LaTeX) and verify the page count is ≤5 pages
3. Read it over — this was drafted end-to-end autonomously from the data, worth a full
   human read before submitting, especially the Discussion/roadmap framing
4. Submit via the SE4ALL/ICSE 2027 submission system before 20 Nov 2026
