#!/usr/bin/env python3
"""results_summary.py -- aggregate judged.jsonl into per-model and per-model-per-type tables."""
import json, collections, statistics

rows = [json.loads(l) for l in open("data/judged.jsonl", encoding="utf-8")]
MODELS = ["qwen/qwen3-vl-8b-instruct", "meta-llama/llama-4-scout", "google/gemma-3-27b-it",
          "mistralai/mistral-small-3.2-24b-instruct", "openai/gpt-4o"]
CRITERIA = ["accuracy", "completeness", "message", "conciseness"]

def agg(subset):
    n = len(subset)
    if n == 0:
        return None
    out = {"n": n}
    for c in CRITERIA:
        out[c] = round(statistics.mean(r[c] for r in subset), 2)
    out["hallucination_rate"] = round(100 * sum(1 for r in subset if r["hallucination"]) / n, 1)
    return out

print("=== Overall per-model ===")
overall = {}
for m in MODELS:
    subset = [r for r in rows if r["model"] == m]
    overall[m] = agg(subset)
    print(f"{m:45s}", overall[m])

print()
print("=== Per-model x per-figure-type (hallucination rate %) ===")
types = ["chart", "diagram", "mixed", "other"]
header = f"{'model':45s}" + "".join(f"{t:>10s}" for t in types) + f"{'overall':>10s}"
print(header)
by_type = {}
for m in MODELS:
    row = []
    for t in types:
        subset = [r for r in rows if r["model"] == m and r["figure_type"] == t]
        a = agg(subset)
        row.append(a["hallucination_rate"] if a else None)
    by_type[m] = row
    print(f"{m:45s}" + "".join(f"{(str(v)+'%') if v is not None else '--':>10s}" for v in row)
          + f"{overall[m]['hallucination_rate']:>9}%")

with open("data/results_overall.json", "w", encoding="utf-8") as f:
    json.dump(overall, f, indent=2)
with open("data/results_by_type.json", "w", encoding="utf-8") as f:
    json.dump({"types": types, "by_model": by_type}, f, indent=2)

print()
print("=== Figure-type counts in judged set ===")
print(dict(collections.Counter(r["figure_type"] for r in rows if r["model"]==MODELS[0])))
