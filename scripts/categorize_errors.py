#!/usr/bin/env python3
"""
categorize_errors.py -- classify each hallucination_claim in judged.jsonl into
a small fixed taxonomy of error types, to support a "why do some models
hallucinate more" analysis rather than just reporting the rate.
"""
import json, os, sys, time
import requests

API = "https://openrouter.ai/api/v1/chat/completions"
KEY_PATH = os.path.expanduser("~/.openrouter/api_key")
MODEL = "anthropic/claude-sonnet-5"

CATEGORIES = [
    "numeric_magnitude",   # wrong value/percentage/count
    "trend_direction",     # reversed an increase/decrease, or a comparison direction
    "ranking_comparison",  # wrong "which is highest/best/most" claim
    "miscount",             # wrong count of discrete items (nodes, bars, panels)
    "misidentification",   # wrong label/identity of a visible element (icon, legend entry)
    "fabricated_detail",   # invented something not depicted at all
    "other",
]

PROMPT = """Classify this hallucination found in an AI-generated figure description \
into exactly one category from this list: {cats}

Hallucinated claim: {claim}

Output exactly one line: CATEGORY: <one of the categories above>
"""

def already_done(path):
    done = set()
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    r = json.loads(line)
                    done.add((r["arxiv_id"], r["fig_index"], r["model"]))
                except (json.JSONDecodeError, KeyError):
                    pass
    return done

def call(key, claim, retries=3):
    prompt = PROMPT.format(cats=", ".join(CATEGORIES), claim=claim)
    payload = {"model": MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 30}
    for attempt in range(retries):
        try:
            r = requests.post(API, headers={"Authorization": f"Bearer {key}"}, json=payload, timeout=60)
            if r.status_code == 429:
                time.sleep(3.0 * (attempt + 1)); continue
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
            for line in text.splitlines():
                if line.strip().startswith("CATEGORY:"):
                    cat = line.split(":", 1)[1].strip().lower()
                    return cat if cat in CATEGORIES else "other", None
            return "other", None
        except Exception as e:
            last_err = str(e)
            time.sleep(2.0 * (attempt + 1))
    return None, last_err

def main():
    key = open(KEY_PATH, encoding="utf-8").read().strip()
    rows = [json.loads(l) for l in open("data/judged.jsonl", encoding="utf-8")]
    halluc = [r for r in rows if r.get("hallucination") and r.get("hallucination_claim")
              and r["hallucination_claim"].lower() != "none"]
    done = already_done("data/error_categories.jsonl")
    todo = [r for r in halluc if (r["arxiv_id"], r["fig_index"], r["model"]) not in done]
    print(f"[i] {len(halluc)} hallucinations, {len(done)} already categorized, {len(todo)} to do", file=sys.stderr)

    with open("data/error_categories.jsonl", "a", encoding="utf-8") as f:
        for n, r in enumerate(todo, 1):
            cat, err = call(key, r["hallucination_claim"])
            f.write(json.dumps({"arxiv_id": r["arxiv_id"], "fig_index": r["fig_index"],
                                 "model": r["model"], "category": cat, "error": err},
                                ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{n}/{len(todo)}] {r['model']}: {cat or 'ERR'}", file=sys.stderr)

if __name__ == "__main__":
    main()
