#!/usr/bin/env python3
"""
filter_metadata.py  -- Stage 1: select arXiv papers for the dataset (offline).

Reads the arXiv bulk metadata snapshot (JSON-lines) and selects papers, with
license tiers and ICSE-2026 tagging. Two modes:

  (default)  SE corpus: keep cs.SE papers >= --min-year with a usable license,
             and TAG the ones that match your ICSE titles.
  --icse-only  keep ONLY papers that match an ICSE title (ANY arXiv category,
             any year, all license tiers) -> "ICSE 2026 papers that are on arXiv".

Matching an ICSE title to an arXiv title: exact (normalized) -> substring
(arXiv title contained in the ICSE line, so track-name prefixes don't matter)
-> fuzzy within a token bucket. Fast via a token index.

Snapshot: Kaggle "Cornell-University/arxiv" -> arxiv-metadata-oai-snapshot.json

Usage (ICSE-only, recommended for your workshop paper):
  python3 filter_metadata.py --snapshot arxiv-metadata-oai-snapshot.json \
      --icse-titles icse2026_titles.txt --icse-only --out selected.jsonl
"""
import argparse, json, sys, re
from difflib import SequenceMatcher

REDISTRIBUTABLE = {"publicdomain/zero": "CC0", "licenses/by/": "CC-BY",
                   "licenses/by-sa/": "CC-BY-SA"}
CONDITIONAL = {"licenses/by-nc-sa/": "CC-BY-NC-SA", "licenses/by-nc/": "CC-BY-NC"}

def license_tier(lic):
    lic = (lic or "").lower()
    for k, n in REDISTRIBUTABLE.items():
        if k in lic: return "redistributable", n
    for k, n in CONDITIONAL.items():
        if k in lic: return "conditional", n
    if "nd/" in lic or "nd-" in lic: return "internal", "CC-ND(avoid)"
    if "nonexclusive-distrib" in lic: return "internal", "arXiv-default"
    return "internal", "none/unknown"

def norm(t):
    t = re.sub(r"[^a-z0-9 ]", " ", (t or "").lower())
    return re.sub(r"\s+", " ", t).strip()

def tokens(nt):
    return [w for w in nt.split() if len(w) >= 6]

class IcseIndex:
    """Match an arXiv title against ICSE TOC lines quickly."""
    def __init__(self, lines):
        self.exact = {}
        self.items = []          # (norm_line, original_line)
        self.tok2idx = {}
        self.vocab = set()
        for orig in lines:
            nl = norm(orig)
            if not nl: continue
            self.exact[nl] = orig
            idx = len(self.items)
            self.items.append((nl, orig))
            for w in tokens(nl):
                self.tok2idx.setdefault(w, []).append(idx)
                self.vocab.add(w)

    def match(self, title, threshold=0.90):
        nt = norm(title)
        if not nt:
            return None, 0.0
        if nt in self.exact:
            return self.exact[nt], 1.0
        tks = [w for w in tokens(nt) if w in self.vocab]
        if not tks:
            return None, 0.0
        cand = set()
        for w in tks:
            cand.update(self.tok2idx.get(w, ()))
            if len(cand) > 60:
                break
        best, best_s = None, 0.0
        for i in cand:
            nl, orig = self.items[i]
            # containment (guard: shorter side must be substantial)
            short, long = (nt, nl) if len(nt) <= len(nl) else (nl, nt)
            if len(short) >= 25 and short in long:
                return orig, 0.97
            s = SequenceMatcher(None, nt, nl).ratio()
            if s > best_s:
                best, best_s = orig, s
        return (best, best_s) if best_s >= threshold else (None, best_s)

def year_of(rec):
    m = re.match(r"(\d{4})", rec.get("update_date") or "")
    if m: return int(m.group(1))
    m = re.match(r"(\d{2})(\d{2})\.", rec.get("id", ""))
    return 2000 + int(m.group(1)) if m else 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--icse-titles", default=None)
    ap.add_argument("--icse-only", action="store_true",
                    help="keep ONLY ICSE-matched papers, any category/year/license")
    ap.add_argument("--cats", default="cs.SE")
    ap.add_argument("--min-year", type=int, default=2024)
    ap.add_argument("--include-internal", action="store_true")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if args.icse_only and not args.icse_titles:
        sys.exit("--icse-only needs --icse-titles")

    idx = None
    if args.icse_titles:
        lines = [l.strip() for l in open(args.icse_titles, encoding="utf-8") if l.strip()]
        idx = IcseIndex(lines)
        print(f"[i] indexed {len(lines)} ICSE titles", file=sys.stderr)

    cats = set(c.strip() for c in args.cats.split(","))
    kept = 0; tiers = {"redistributable":0,"conditional":0,"internal":0}; icse_hits = 0
    with open(args.snapshot, encoding="utf-8") as fin, open(args.out,"w",encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line: continue
            try: rec = json.loads(line)
            except json.JSONDecodeError: continue

            icse_title, score = (idx.match(rec.get("title","")) if idx else (None,0.0))

            if args.icse_only:
                if not icse_title:
                    continue
            else:
                if not (set((rec.get("categories") or "").split()) & cats):
                    continue
                if year_of(rec) < args.min_year:
                    continue

            tier, lic_name = license_tier(rec.get("license"))
            if not args.icse_only and tier == "internal" and not args.include_internal:
                continue

            comments = (rec.get("comments") or "").strip()
            venue_hint = bool(re.search(r"\b(ICSE|FSE|ESEC|ASE|ISSTA)\b.{0,12}20(24|25|26)",
                                        comments, re.I))
            fout.write(json.dumps({
                "id": rec.get("id"),
                "title": rec.get("title","").strip(),
                "year": year_of(rec),
                "categories": rec.get("categories"),
                "license_url": rec.get("license"),
                "license_name": lic_name,
                "license_tier": tier,
                "comments": comments,
                "venue_hint": venue_hint,
                "icse2026_title": icse_title,
                "icse2026_match_score": round(score,3),
                "source_url": f"https://export.arxiv.org/e-print/{rec.get('id')}",
                "pdf_url": f"https://arxiv.org/pdf/{rec.get('id')}",
            }, ensure_ascii=False) + "\n")
            kept += 1; tiers[tier] += 1
            if icse_title: icse_hits += 1

    print(f"[done] kept {kept} -> {args.out}", file=sys.stderr)
    print(f"       tiers: {tiers}   ICSE-matched: {icse_hits}", file=sys.stderr)
    if idx and icse_hits < len(idx.items):
        print(f"       note: {len(idx.items)-icse_hits} ICSE titles had NO arXiv "
              f"match (not on arXiv, or title differs) -> excluded by design.",
              file=sys.stderr)

if __name__ == "__main__":
    main()
