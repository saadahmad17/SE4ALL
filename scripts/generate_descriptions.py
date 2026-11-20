#!/usr/bin/env python3
r"""
generate_descriptions.py -- Stage 5a: generate figure descriptions from each
candidate model via OpenRouter. Each model receives ONLY the raw image (no
caption, no mentions) and must produce an accessible description for a blind
or low-vision reader -- this is the actual capability under test.

Usage:
  python3 generate_descriptions.py --sample figures/sample.jsonl \
      --figures-dir figures --out generations.jsonl
"""
import argparse, base64, json, mimetypes, os, sys, time
import requests

API = "https://openrouter.ai/api/v1/chat/completions"
KEY_PATH = os.path.expanduser("~/.openrouter/api_key")

MODELS = [
    ("qwen/qwen3-vl-8b-instruct", "open"),
    ("meta-llama/llama-4-scout", "open"),
    ("google/gemma-3-27b-it", "open"),
    ("mistralai/mistral-small-3.2-24b-instruct", "open"),
    ("openai/gpt-4o", "closed"),
]

PROMPT = (
    "You are writing an accessible description of a figure from a software "
    "engineering research paper, for a blind or low-vision reader who cannot "
    "see the image. Follow WCAG complex-image guidance: state what kind of "
    "figure it is; describe its structure (for a chart: axes, variables, "
    "series; for a diagram: components and relationships/flow); state the "
    "key pattern, trend, or finding it conveys; include specific values only "
    "if essential to understanding. Do not mention colors unless necessary. "
    "Write 3-6 concise sentences. Do not guess at information you cannot see; "
    "if something is illegible, say so rather than inventing it."
)

def already_done(out_path):
    done = set()
    if os.path.exists(out_path):
        for line in open(out_path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                done.add((r["arxiv_id"], r["fig_index"], r["model"]))
            except (json.JSONDecodeError, KeyError):
                pass
    return done

def to_data_uri(path):
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"

def call_model(key, model, image_path, timeout=90, retries=3):
    data_uri = to_data_uri(image_path)
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        }],
        "max_tokens": 400,
    }
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.post(API, headers={"Authorization": f"Bearer {key}"},
                               json=payload, timeout=timeout)
            if r.status_code == 429:
                time.sleep(5.0 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"], None
        except Exception as e:
            last_err = e
            time.sleep(2.0 * (attempt + 1))
    return None, str(last_err)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True)
    ap.add_argument("--figures-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    key = open(KEY_PATH, encoding="utf-8").read().strip()
    rows = [json.loads(l) for l in open(args.sample, encoding="utf-8") if l.strip()]
    done = already_done(args.out)

    jobs = []
    for r in rows:
        img = r["images"][0]  # first image is representative; fine for single-panel figs
        img_path = os.path.join(args.figures_dir, img)
        for model, _ in MODELS:
            if (r["arxiv_id"], r["fig_index"], model) not in done:
                jobs.append((r, img_path, model))

    print(f"[i] {len(rows)} figures x {len(MODELS)} models, {len(done)} already done, "
          f"{len(jobs)} to run", file=sys.stderr)

    with open(args.out, "a", encoding="utf-8") as fout:
        for n, (r, img_path, model) in enumerate(jobs, 1):
            text, err = call_model(key, model, img_path)
            rec = {
                "arxiv_id": r["arxiv_id"], "fig_index": r["fig_index"],
                "figure_type": r["figure_type"], "model": model,
                "description": text, "error": err,
            }
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fout.flush()
            status = "OK" if text else f"ERR: {err}"
            print(f"[{n}/{len(jobs)}] {r['arxiv_id']} fig{r['fig_index']} {model}: {status[:80]}",
                  file=sys.stderr)

    print(f"[done] -> {args.out}", file=sys.stderr)

if __name__ == "__main__":
    main()
