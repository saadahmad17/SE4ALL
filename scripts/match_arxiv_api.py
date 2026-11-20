#!/usr/bin/env python3
r"""
match_arxiv_api.py  -- Stage 1 replacement: match ICSE titles via the arXiv API.

Drop-in alternative to `filter_metadata.py --icse-only` that avoids downloading
the ~5GB Kaggle arXiv metadata snapshot. Rationale: --icse-only only ever keeps
rows matching one of ~321 known ICSE titles, so a full-corpus scan is wasted
work -- a targeted query per title against the arXiv API (export.arxiv.org)
is smaller, faster, and needs no bulk download.

Trade-off: the arXiv API rarely exposes an explicit license (only papers that
opted into a CC license carry one; the rest default to arXiv's standard
perpetual license, same as the snapshot's "internal/none" tier). Since this
project releases by reference (never raw images), license tier doesn't gate
anything -- see CLAUDE.md.

Output: the same selected.jsonl schema filter_metadata.py produces, so
extract_figures.py (Stage 2) runs unchanged.

NETWORK REQUIRED. Resumable: re-running with the same --out skips titles
already matched or already logged as no-match.

Usage:
  python3 match_arxiv_api.py --icse-titles icse2026_titles.txt --out selected.jsonl
"""
import argparse, json, os, re, sys, time
from difflib import SequenceMatcher
import xml.etree.ElementTree as ET

import requests

API = "http://export.arxiv.org/api/query"
UA = "se-figbench-research/0.1 (academic figure-accessibility study)"
ATOM_NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

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

def score_match(icse_title, cand_title):
    a, b = norm(icse_title), norm(cand_title)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) >= 25 and short in long_:
        return 0.97
    return SequenceMatcher(None, a, b).ratio()

def parse_entries(xml_text):
    root = ET.fromstring(xml_text)
    out = []
    for entry in root.findall("a:entry", ATOM_NS):
        id_url = (entry.findtext("a:id", default="", namespaces=ATOM_NS) or "").strip()
        m = re.search(r"arxiv\.org/abs/([^v]+)", id_url)
        if not m:
            continue
        aid = m.group(1)
        title = re.sub(r"\s+", " ", entry.findtext("a:title", default="", namespaces=ATOM_NS) or "").strip()
        published = entry.findtext("a:published", default="", namespaces=ATOM_NS) or ""
        year = int(published[:4]) if published[:4].isdigit() else 0
        cats = sorted({c.get("term") for c in entry.findall("a:category", ATOM_NS) if c.get("term")})
        comment = (entry.findtext("arxiv:comment", default="", namespaces=ATOM_NS) or "").strip()
        license_url = entry.findtext("arxiv:license", default="", namespaces=ATOM_NS) or None
        out.append({
            "id": aid, "title": title, "year": year,
            "categories": " ".join(cats), "comments": comment,
            "license_url": license_url,
        })
    return out

def get_with_retries(session, params, timeout, retries=3):
    last_err = None
    for attempt in range(retries):
        try:
            r = session.get(API, params=params, headers={"User-Agent": UA}, timeout=timeout)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(3.0 * (attempt + 1))
    raise last_err

def query_arxiv(session, title, sleep_between, timeout=30):
    """Try a phrase search on the title; fall back to ANDing key tokens."""
    phrase = re.sub(r'[\"\\]', " ", title).strip()
    attempts = [f'ti:"{phrase}"']
    toks = [w for w in norm(title).split() if len(w) >= 6][:6]
    if toks:
        attempts.append(" AND ".join(f'ti:{w}' for w in toks))
    for i, q in enumerate(attempts):
        params = {"search_query": q, "max_results": 5}
        r = get_with_retries(session, params, timeout)
        entries = parse_entries(r.text)
        if entries:
            return entries
        if i < len(attempts) - 1:
            time.sleep(sleep_between)  # separate request against the rate limit
    return []

def already_done(out_path):
    done = set()
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    done.add(json.loads(line)["icse2026_title"])
                except (json.JSONDecodeError, KeyError):
                    pass
    return done

def already_nomatch(path):
    if os.path.exists(path):
        return {l.strip() for l in open(path, encoding="utf-8") if l.strip()}
    return set()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--icse-titles", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--nomatch-log", default="icse2026_nomatch.txt")
    ap.add_argument("--threshold", type=float, default=0.90)
    ap.add_argument("--sleep", type=float, default=3.0, help="seconds between arXiv API requests")
    ap.add_argument("--limit", type=int, default=None, help="only process the first N remaining titles")
    args = ap.parse_args()

    titles = [l.strip() for l in open(args.icse_titles, encoding="utf-8") if l.strip()]
    skip = already_done(args.out) | already_nomatch(args.nomatch_log)
    todo = [t for t in titles if t not in skip]
    if args.limit:
        todo = todo[:args.limit]
    print(f"[i] {len(titles)} titles, {len(skip)} already resolved, {len(todo)} to query", file=sys.stderr)

    session = requests.Session()
    matched = 0
    tiers = {"redistributable": 0, "conditional": 0, "internal": 0}
    with open(args.out, "a", encoding="utf-8") as fout, \
         open(args.nomatch_log, "a", encoding="utf-8") as fnomatch:
        for n, icse_title in enumerate(todo, 1):
            try:
                candidates = query_arxiv(session, icse_title, args.sleep)
            except (requests.RequestException, ET.ParseError) as e:
                print(f"[{n}/{len(todo)}] REQUEST FAILED: {icse_title[:70]!r} ({e})", file=sys.stderr)
                fnomatch.write(icse_title + "\n")
                fnomatch.flush()
                time.sleep(args.sleep)
                continue

            best, best_score = None, 0.0
            for c in candidates:
                s = score_match(icse_title, c["title"])
                if s > best_score:
                    best, best_score = c, s

            if best and best_score >= args.threshold:
                tier, lic_name = license_tier(best["license_url"])
                venue_hint = bool(re.search(r"\b(ICSE|FSE|ESEC|ASE|ISSTA)\b.{0,12}20(24|25|26)",
                                             best["comments"], re.I))
                fout.write(json.dumps({
                    "id": best["id"], "title": best["title"], "year": best["year"],
                    "categories": best["categories"], "license_url": best["license_url"],
                    "license_name": lic_name, "license_tier": tier,
                    "comments": best["comments"], "venue_hint": venue_hint,
                    "icse2026_title": icse_title, "icse2026_match_score": round(best_score, 3),
                    "source_url": f"https://export.arxiv.org/e-print/{best['id']}",
                    "pdf_url": f"https://arxiv.org/pdf/{best['id']}",
                }, ensure_ascii=False) + "\n")
                fout.flush()
                matched += 1
                tiers[tier] += 1
                print(f"[{n}/{len(todo)}] MATCHED ({best_score:.2f}) {best['id']}: {icse_title[:70]!r}",
                      file=sys.stderr)
            else:
                fnomatch.write(icse_title + "\n")
                fnomatch.flush()
                print(f"[{n}/{len(todo)}] no match (best={best_score:.2f}): {icse_title[:70]!r}",
                      file=sys.stderr)

            time.sleep(args.sleep)

    print(f"[done] matched {matched}/{len(todo)} this run -> {args.out}", file=sys.stderr)
    print(f"       tiers this run: {tiers}", file=sys.stderr)
    print(f"       no-match titles logged -> {args.nomatch_log}", file=sys.stderr)

if __name__ == "__main__":
    main()
