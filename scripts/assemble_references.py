#!/usr/bin/env python3
"""
assemble_references.py -- final merge of promote_direct.jsonl (unambiguous
human-confirmed) + resolved_flagged.jsonl (LLM-resolved, figure-type
corrected) into reference_descriptions.jsonl. still_missing.jsonl is left out.
Run from the repo root.
"""
import json, collections

drafts = {(json.loads(l)["arxiv_id"], json.loads(l)["fig_index"]): json.loads(l)
          for l in open("data/draft_references.jsonl", encoding="utf-8")}

resolved = {(json.loads(l)["arxiv_id"], json.loads(l)["fig_index"]): json.loads(l)
            for l in open("data/resolved_flagged.jsonl", encoding="utf-8")}

promote = [json.loads(l) for l in open("data/promote_direct.jsonl", encoding="utf-8")]

sample = {(r["arxiv_id"], r["fig_index"]): r
          for r in (json.loads(l) for l in open("data/figures/sample.jsonl", encoding="utf-8"))}

out = []
for p in promote:
    key = (p["arxiv_id"], p["fig_index"])
    d = drafts[key]
    out.append({
        "arxiv_id": key[0], "fig_index": key[1],
        "figure_type": sample[key]["figure_type"],
        "short_alt": d["short_alt_draft"], "long_description": d["long_description_draft"],
        "reviewed": True, "provenance": "human-confirmed-accurate",
        "needs_quick_check": False, "notes": "",
    })

for key, r in resolved.items():
    out.append({
        "arxiv_id": key[0], "fig_index": key[1],
        "figure_type": r["figure_type"],
        "short_alt": r["short_alt"], "long_description": r["long_description"],
        "reviewed": True, "provenance": f"human-flagged -> llm-resolved ({r['verdict']})",
        "needs_quick_check": True, "notes": r["note"],
    })

with open("data/reference_descriptions.jsonl", "w", encoding="utf-8") as f:
    for r in out:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print(f"[done] {len(out)} references -> data/reference_descriptions.jsonl")
print(f"       direct-promote: {sum(1 for r in out if r['provenance']=='human-confirmed-accurate')}")
print(f"       llm-resolved: {sum(1 for r in out if r['needs_quick_check'])}")
print(f"       figure_type breakdown: {dict(collections.Counter(r['figure_type'] for r in out))}")
missing = [json.loads(l) for l in open("data/still_missing.jsonl", encoding="utf-8")]
print(f"       still missing (not in this file): {missing}")
