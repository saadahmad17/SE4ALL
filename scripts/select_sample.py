#!/usr/bin/env python3
r"""
select_sample.py -- pick the final benchmark sample: a stratified subset of
figures/index_typed.jsonl, preserving the natural chart/diagram/mixed/other
proportions among "GOOD" candidates (latex-sourced, has caption, has image).

Usage:
  python3 select_sample.py --index figures/index_typed.jsonl --n 100 --out figures/sample.jsonl
"""
import argparse, json, random, collections

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.index, encoding="utf-8") if l.strip()]
    good = [r for r in rows if r.get("caption") and r.get("images") and r["source"] == "latex"]

    by_type = collections.defaultdict(list)
    for r in good:
        by_type[r["figure_type"]].append(r)

    rng = random.Random(args.seed)
    for v in by_type.values():
        rng.shuffle(v)

    total = len(good)
    sample = []
    for t, items in by_type.items():
        k = round(args.n * len(items) / total)
        sample.extend(items[:k])

    # top up / trim to exactly n if rounding drifted
    rng.shuffle(sample)
    if len(sample) < args.n:
        remaining = [r for t, items in by_type.items() for r in items[round(args.n*len(items)/total):]]
        rng.shuffle(remaining)
        sample.extend(remaining[:args.n - len(sample)])
    sample = sample[:args.n]

    with open(args.out, "w", encoding="utf-8") as f:
        for r in sample:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"[done] sampled {len(sample)}/{total} good figures -> {args.out}")
    print("       type breakdown:", dict(collections.Counter(r["figure_type"] for r in sample)))

if __name__ == "__main__":
    main()
