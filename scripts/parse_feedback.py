#!/usr/bin/env python3
"""
parse_feedback.py -- parse the human-review Google Form export, route each of
the 100 figures to either direct promotion (unambiguous "accurate, no issues"
consensus) or the resolve_flagged.py pipeline (any "No" verdict, OR any
comment -- even under an overall "Yes" -- that contains a concrete correction
signal, e.g. a figure-type fix or a specific factual nit). Over-inclusion into
resolution is safe (resolver can just confirm the draft is fine); the risk
being managed is under-inclusion silently losing real feedback that happened
to ride along with a lenient "Yes".

Run from the repo root. Reads data/position_mapping.json (position -> figure
key, derived once from the labeling tool), data/figures/sample.jsonl, and the
raw Google Form export under data/raw_feedback/.
"""
import re, json, openpyxl, collections

SIGNAL_RE = re.compile(
    r"\b(but |however|mistake|doesn't mention|does not mention|misses?\b|"
    r"should be|instead of|pre-set to|changed figure type|incorrect|"
    r"not accurate|not fully accurate|\bwrong\b|told it as|classified.*as)",
    re.I)

def needs_resolution(entries):
    for name, verdict, obs in entries:
        if verdict == "No":
            return True
        if obs and SIGNAL_RE.search(obs):
            return True
    return False

def main():
    mapping = json.load(open("data/position_mapping.json", encoding="utf-8"))
    pos_to_key = {m["position"]: (m["arxiv_id"], m["fig_index"]) for m in mapping}
    sample = {(r["arxiv_id"], r["fig_index"]): r
              for r in (json.loads(l) for l in open("data/figures/sample.jsonl", encoding="utf-8"))}
    drafts = {(r["arxiv_id"], r["fig_index"]): r
              for r in (json.loads(l) for l in open("data/draft_references.jsonl", encoding="utf-8"))}

    wb = openpyxl.load_workbook("data/raw_feedback/human_review_responses.xlsx", data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))[1:]
    numeric = [(int(r[2]), (r[1] or "").strip(), r[3], r[4]) for r in rows if not isinstance(r[2], str)]
    by_num = collections.defaultdict(list)
    for num, name, obs, verdict in numeric:
        by_num[num].append((name, verdict, obs))

    promote, resolve, missing = [], [], []
    for pos in range(1, 101):
        key = pos_to_key[pos]
        entries = by_num.get(pos)
        if not entries:
            missing.append((pos, key))
            continue
        if needs_resolution(entries):
            resolve.append((pos, key, entries))
        else:
            promote.append((pos, key, entries))

    print(f"direct-promote: {len(promote)} | needs resolution: {len(resolve)} | missing: {len(missing)}")
    print("missing:", missing)

    with open("data/flagged_input.jsonl", "w", encoding="utf-8") as f:
        for pos, key, entries in resolve:
            s, d = sample[key], drafts[key]
            critiques = [f"[{name}, verdict={verdict}] {obs}" for name, verdict, obs in entries if obs]
            f.write(json.dumps({
                "arxiv_id": key[0], "fig_index": key[1], "image": s["images"][0],
                "short_alt_draft": d["short_alt_draft"], "long_description_draft": d["long_description_draft"],
                "figure_type": s["figure_type"], "critiques": critiques,
            }, ensure_ascii=False) + "\n")

    with open("data/promote_direct.jsonl", "w", encoding="utf-8") as f:
        for pos, key, entries in promote:
            f.write(json.dumps({"arxiv_id": key[0], "fig_index": key[1]}, ensure_ascii=False) + "\n")

    with open("data/still_missing.jsonl", "w", encoding="utf-8") as f:
        for pos, key in missing:
            f.write(json.dumps({"position": pos, "arxiv_id": key[0], "fig_index": key[1]}, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    main()
