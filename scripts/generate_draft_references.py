#!/usr/bin/env python3
r"""
generate_draft_references.py -- LLM-assisted DRAFT of the Layer-2 reference
descriptions for the gold set. A strong model gets the image PLUS the
extracted caption/mentions (so it reasons the way a human reading the paper
would), and drafts a short-alt + long-description. These are drafts only --
build_labeling_tool.py pre-fills them into the editable form, and a human
must review/edit/approve every single one before it counts as ground truth.
Do not use this output unreviewed.

Usage:
  python3 generate_draft_references.py --sample figures/sample.jsonl \
      --figures-dir figures --out draft_references.jsonl --n 25
"""
import argparse, base64, collections, json, mimetypes, os, random, sys, time
import requests

API = "https://openrouter.ai/api/v1/chat/completions"
KEY_PATH = os.path.expanduser("~/.openrouter/api_key")
DRAFT_MODEL = "anthropic/claude-sonnet-5"

PROMPT_TMPL = """You are drafting a WCAG-style accessible description of a figure from a \
software engineering research paper, for a blind or low-vision reader. This draft will \
be reviewed and edited by a human before use, but try to get it right.

Rules:
- Use the IMAGE as the primary source for visual/structural facts: what kind of figure \
it is, its axes/variables/series (chart) or components/relationships (diagram), how many \
bars/lines/boxes/nodes there are, overall layout.
- Use the paper's own caption and in-text mentions below ONLY to understand the figure's \
MEANING and significance (what question it answers, what the takeaway is) -- do NOT just \
paraphrase or copy this text; the reader needs to know what the image shows, not a \
restatement of the caption.
- If something in the image is illegible or ambiguous, say so rather than guessing.
- Output exactly two lines, no extra commentary:
SHORT: <~15 word functional alt text>
LONG: <3-6 sentence accessible description>

Paper's caption: {caption}
Paper's in-text mentions of this figure: {mentions}
"""

def stratified_subset(rows, n, seed=42):
    by_type = collections.defaultdict(list)
    for r in rows:
        by_type[r["figure_type"]].append(r)
    rng = random.Random(seed)
    for v in by_type.values():
        rng.shuffle(v)
    total = len(rows)
    picked = []
    for items in by_type.values():
        k = max(1, round(n * len(items) / total))
        picked.extend(items[:k])
    rng.shuffle(picked)
    return picked[:n]

def to_data_uri(path, max_dim=2000):
    """Downscale if either dimension exceeds max_dim -- some vision endpoints
    (seen: Claude via OpenRouter) reject very large images outright with a
    400 rather than resizing server-side, even though others accept them fine."""
    import fitz
    pix = fitz.Pixmap(path)
    if max(pix.width, pix.height) > max_dim:
        scale = max_dim / max(pix.width, pix.height)
        pix = fitz.Pixmap(pix, int(pix.width * scale), int(pix.height * scale))
    b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")
    return f"data:image/png;base64,{b64}"

def already_done(out_path):
    done = set()
    if os.path.exists(out_path):
        for line in open(out_path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                done.add((r["arxiv_id"], r["fig_index"]))
            except (json.JSONDecodeError, KeyError):
                pass
    return done

def call_draft(key, image_path, caption, mentions, timeout=90, retries=3):
    prompt = PROMPT_TMPL.format(caption=caption or "(none extracted)",
                                 mentions=" / ".join(mentions) if mentions else "(none extracted)")
    payload = {
        "model": DRAFT_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": to_data_uri(image_path)}},
            ],
        }],
        "max_tokens": 700,
    }
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.post(API, headers={"Authorization": f"Bearer {key}"}, json=payload, timeout=timeout)
            if r.status_code == 429:
                time.sleep(5.0 * (attempt + 1))
                continue
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
            short, long_ = "", ""
            for line in text.splitlines():
                if line.strip().startswith("SHORT:"):
                    short = line.split(":", 1)[1].strip()
                elif line.strip().startswith("LONG:"):
                    long_ = line.split(":", 1)[1].strip()
            return short, long_, None
        except Exception as e:
            last_err = e
            time.sleep(2.0 * (attempt + 1))
    return "", "", str(last_err)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True)
    ap.add_argument("--figures-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=25)
    args = ap.parse_args()

    key = open(KEY_PATH, encoding="utf-8").read().strip()
    rows = [json.loads(l) for l in open(args.sample, encoding="utf-8") if l.strip()]
    gold = stratified_subset(rows, args.n)
    done = already_done(args.out)
    todo = [r for r in gold if (r["arxiv_id"], r["fig_index"]) not in done]
    print(f"[i] {len(gold)} gold figures, {len(done)} already drafted, {len(todo)} to draft", file=sys.stderr)

    with open(args.out, "a", encoding="utf-8") as fout:
        for i, r in enumerate(todo, 1):
            img_path = os.path.join(args.figures_dir, r["images"][0])
            short, long_, err = call_draft(key, img_path, r.get("caption"), r.get("mentions", []))
            rec = {"arxiv_id": r["arxiv_id"], "fig_index": r["fig_index"],
                   "short_alt_draft": short, "long_description_draft": long_, "error": err}
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fout.flush()
            print(f"[{i}/{len(todo)}] {r['arxiv_id']} fig{r['fig_index']}: "
                  f"{'OK' if not err else 'ERR: ' + err[:60]}", file=sys.stderr)

    print(f"[done] -> {args.out}  (UNREVIEWED DRAFTS -- human must edit/approve each)", file=sys.stderr)

if __name__ == "__main__":
    main()
