#!/usr/bin/env python3
r"""
extract_titles.py  -- Stage 0: pull paper titles from the ICSE proceedings TOC.

Input: the text of the table-of-contents pages (first ~50 pages). Either:
  (a) a .txt you produced with:  pdftotext -f 1 -l 50 proceedings.pdf toc.txt
  (b) the proceedings .pdf directly (needs PyMuPDF; uses --first/--last pages)

TOC entry format handled (dot leaders may decode as ., ·, …, or �):
  <Track name> <n> <Title> .........<PAGE> <Author (Affil.), Author (Affil.), ...>
  <Title> .........<PAGE> <Authors ...>

Output:
  icse2026_titles.txt   one title per line  (feed to filter_metadata.py)
  icse2026_toc.csv      title, page, authors  (for your records)

Review the .txt once before using it; track-name prefixes on the first title of
each session are the only thing the parser can't always strip, and Stage-1
substring matching tolerates them anyway.
"""
import argparse, csv, re, sys

# dot-leader fillers, 3+ in a row (allow spaces between)
LEADER = r"(?:[.·•․‥…�∙⋅‧]\s*){3,}"
ANCHOR = re.compile(LEADER + r"\s*(\d{1,5})")

# session-opener pages carry a bled-through lowercase roman-numeral running
# footer (e.g. "xiv HarnessLLM: ...") right before the real title.
ROMAN_PREFIX = re.compile(r"^([ivxlcdm]+)\s+(?=[A-Z])", re.I)
ROMAN_VALID = re.compile(r"^M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$", re.I)

def get_text(args):
    if args.pdf:
        import fitz
        doc = fitz.open(args.pdf)
        pages = range(args.first - 1, min(args.last, len(doc)))
        return "\n".join(doc[p].get_text() for p in pages)
    with open(args.txt, encoding="utf-8", errors="ignore") as f:
        return f.read()

def clean_title(t: str) -> str:
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", t)  # PDF control chars (e.g. \x08 before dot leaders)
    t = re.sub(r"\s+", " ", t).strip()
    m = ROMAN_PREFIX.match(t)
    if m and ROMAN_VALID.match(m.group(1)):
        t = t[m.end():].strip()
    # strip a leading "<Track words> <number> " prefix: take text after the last
    # standalone 1-3 digit token that sits in the first ~60 chars.
    for m in re.finditer(r"\b(\d{1,3})\b", t[:60]):
        pass
    m = list(re.finditer(r"\b\d{1,3}\b", t[:60]))
    if m:
        last = m[-1]
        tail = t[last.end():].strip()
        # only strip if what remains still looks like a title (has letters)
        if len(tail) > 15 and re.search(r"[A-Za-z]", tail):
            t = tail
    return t.strip(" .-")

def split_authors_title(mid: str):
    """mid = '<authors of prev entry> <title of next entry>'. Authors end at the
    last ')'; everything after is the next title."""
    idx = mid.rfind(")")
    if idx == -1:
        # no affiliation parens; fall back: assume all authors, no next title yet
        return mid.strip(), ""
    return mid[:idx + 1].strip(), mid[idx + 1:].strip()

def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--txt", help="TOC text file (from pdftotext)")
    g.add_argument("--pdf", help="proceedings PDF (needs PyMuPDF)")
    ap.add_argument("--first", type=int, default=1, help="first PDF page (1-based)")
    ap.add_argument("--last", type=int, default=50, help="last PDF page")
    ap.add_argument("--out-titles", default="icse2026_titles.txt")
    ap.add_argument("--out-csv", default="icse2026_toc.csv")
    args = ap.parse_args()

    text = get_text(args)
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)

    # split into [pre, page, mid, page, mid, ...]
    parts = ANCHOR.split(text)
    # parts[0] = first title (maybe with track prefix); then (page, mid) pairs.
    entries = []  # (title, page, authors)
    pending_title = clean_title(parts[0])
    i = 1
    while i < len(parts):
        page = parts[i]
        mid = parts[i + 1] if i + 1 < len(parts) else ""
        authors, next_title = split_authors_title(mid)
        entries.append((pending_title, page, authors))
        pending_title = clean_title(next_title)
        i += 2
    # drop empties / obvious noise
    entries = [(t, p, a) for (t, p, a) in entries if len(t) >= 8]

    with open(args.out_titles, "w", encoding="utf-8") as ft:
        for t, _, _ in entries:
            ft.write(t + "\n")
    with open(args.out_csv, "w", encoding="utf-8", newline="") as fc:
        w = csv.writer(fc)
        w.writerow(["title", "page", "authors"])
        w.writerows(entries)

    print(f"[done] {len(entries)} titles -> {args.out_titles}", file=sys.stderr)
    print("[review] eyeball the first few titles for track-name prefixes:",
          file=sys.stderr)
    for t, p, _ in entries[:5]:
        print(f"   p{p}: {t[:80]}", file=sys.stderr)

if __name__ == "__main__":
    main()
