#!/usr/bin/env python3
r"""
extract_figures.py  -- Stage 2 of the SE figure-accessibility dataset pipeline.

For each paper in the Stage-1 manifest, fetch the arXiv e-print SOURCE tarball
and extract (figure image, caption, in-text mentions). Falls back to PDF
extraction when there is no usable LaTeX source.

Why source first: the LaTeX gives you the ORIGINAL image files plus \caption{}
and \label/\ref, so you can mine the sentences that reference each figure
("as Fig. 3 shows, X outperforms Y...") -- far better ground truth for an
accessibility description than the terse caption alone.

NETWORK REQUIRED (hits export.arxiv.org). Run this on your own machine.
Be polite: the script sleeps between requests. Respect arXiv's rate limits.

Deps:
  pip install requests PyMuPDF
  # optional, better matching not needed here.
  # For heavy-duty PDF figure+caption boxes, consider Allen AI's pdffigures2
  # (separate Scala tool) and plug its JSON in instead of the PyMuPDF fallback.

Usage:
  python3 extract_figures.py --manifest selected.jsonl --out-dir figures \
      --limit 200 --prefer-tier redistributable

Output layout:
  figures/<arxiv_id>/fig_XX.<ext>          extracted image files
  figures/<arxiv_id>/meta.json             captions + mentions + license
  figures/index.jsonl                      one row per (paper, figure)
"""
import argparse, json, os, re, io, sys, time, tarfile, gzip, shutil

try:
    import requests
except ImportError:
    sys.exit("pip install requests PyMuPDF")

IMG_EXT = (".pdf", ".png", ".jpg", ".jpeg", ".eps", ".ps")
UA = "se-figbench-research/0.1 (academic figure-accessibility study)"

def fetch(url, timeout=60):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    r.raise_for_status()
    return r.content

# ---- caption / mention mining from LaTeX ----------------------------------
CAP_RE = re.compile(r"\\caption\*?\s*\{", re.I)
INCLUDE_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\s*\{([^}]+)\}")
LABEL_RE = re.compile(r"\\label\s*\{([^}]+)\}")

def balanced(s, start):
    """Return the content of a {...} group that starts at s[start]=='{'."""
    depth, i = 0, start
    while i < len(s):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return s[start + 1:i], i + 1
        i += 1
    return s[start + 1:], len(s)

def parse_tex(tex):
    """Yield dicts: {caption, graphics:[...], label} per figure environment."""
    figs = []
    for m in re.finditer(r"\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}", tex,
                         re.S | re.I):
        body = m.group(1)
        graphics = INCLUDE_RE.findall(body)
        cap = None
        cm = CAP_RE.search(body)
        if cm:
            cap, _ = balanced(body, cm.end() - 1)
            cap = re.sub(r"\s+", " ", cap).strip()
        lab = LABEL_RE.search(body)
        figs.append({"caption": cap, "graphics": graphics,
                     "label": lab.group(1) if lab else None})
    return figs

REF_MACRO = r"\\(?:auto|C|c|fig|Fig|full|v)?ref\*?\{%s\}"
SECTION_RE = re.compile(r"\\(?:sub)*section\*?\s*\{([^}]*)\}")

NEWCOMMAND_RE = re.compile(
    r"\\(?:newcommand|renewcommand)\*?\s*\{?\\([a-zA-Z]+)\}?\s*(?:\[[^\]]*\]\s*){0,2}\{",
    re.S)

def resolve_macros(tex):
    """Expand simple zero-argument \\newcommand/\\renewcommand macros (papers
    commonly define their own tool/system name this way, e.g.
    \\newcommand{\\toolname}{ProxyWar}) so captions don't end up with a blank
    where the macro name was stripped."""
    macros = {}
    for m in NEWCOMMAND_RE.finditer(tex):
        name = m.group(1)
        body, _ = balanced(tex, m.end() - 1)
        if "#" in body:  # takes arguments -- too risky to inline blindly
            continue
        macros[name] = body.strip()
    if not macros:
        return tex
    for name in sorted(macros, key=len, reverse=True):  # longest names first
        body = macros[name]
        tex = re.sub(r"\\" + re.escape(name) + r"(?![a-zA-Z])", lambda m, b=body: b, tex)
    return tex

def _clean(s):
    s = re.sub(r"%.*", "", s)                        # tex line comments
    s = s.replace("~", " ")                          # non-breaking space
    # drop \ref-family / \label / \cite together with their braces + arg
    s = re.sub(r"\\(?:auto|C|c|fig|Fig|full|v)?ref\*?\s*\{[^}]*\}", "", s)
    s = re.sub(r"\\(?:label|cite[a-z]*|eqref)\s*\{[^}]*\}", "", s)
    s = re.sub(r"\\[a-zA-Z]+\*?", " ", s)            # drop remaining macros
    s = re.sub(r"\\[,;!> ]", " ", s)                 # LaTeX explicit-space control sequences
    s = re.sub(r"\\([&%$#_{}])", r"\1", s)           # escaped literal symbols -> the symbol itself
    s = s.replace("{", " ").replace("}", " ")
    # tidy dangling "Figure" / "Fig." left with no number
    s = re.sub(r"\b(Figure|Fig\.?)\s+(?=[,.)])", r"\1 ", s)
    return re.sub(r"\s+", " ", s).strip()

def context_for(tex, label):
    """Return (mention_paragraphs, section) explaining the figure.

    A mention paragraph is any paragraph (blank-line separated) that references
    the figure's label via \\ref/\\autoref/\\Cref/\\figref/etc. The section is
    the nearest \\section/\\subsection heading preceding the first mention.
    """
    if not label:
        return [], None
    ref_re = re.compile(REF_MACRO % re.escape(label))
    paras = re.split(r"\n\s*\n", tex)
    mentions, offsets = [], []
    pos = 0
    for p in paras:
        if ref_re.search(p):
            cleaned = _clean(p)
            if len(cleaned) > 20:
                mentions.append(cleaned)
                offsets.append(pos)
        pos += len(p) + 2
    section = None
    if offsets:
        last = None
        for m in SECTION_RE.finditer(tex):
            if m.start() <= offsets[0]:
                last = m.group(1)
            else:
                break
        section = _clean(last) if last else None
    return mentions[:6], section

def read_source(blob):
    """blob may be a tar(.gz), a single gzipped .tex, or raw. Return {name:bytes}."""
    files = {}
    # try tar
    try:
        with tarfile.open(fileobj=io.BytesIO(blob)) as tf:
            for mem in tf.getmembers():
                if mem.isfile():
                    f = tf.extractfile(mem)
                    if f:
                        files[mem.name] = f.read()
        if files:
            return files
    except tarfile.TarError:
        pass
    # try single gzip
    try:
        data = gzip.decompress(blob)
        files["main.tex"] = data
        return files
    except OSError:
        pass
    # raw (maybe a PDF)
    files["__raw__"] = blob
    return files

def rasterize_to_png(path, dpi=200):
    """Render a vector figure (pdf/eps/ps) to PNG for multimodal-model consumption.
    Returns the PNG path, or None if rasterization isn't possible (e.g. no PyMuPDF,
    or a .eps/.ps PyMuPDF can't open without Ghostscript)."""
    try:
        import fitz
    except ImportError:
        return None
    try:
        doc = fitz.open(path)
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0))
        png_path = os.path.splitext(path)[0] + ".png"
        pix.save(png_path)
        return png_path
    except Exception:
        return None

def extract_from_source(aid, out_dir):
    blob = fetch(f"https://export.arxiv.org/e-print/{aid}")
    files = read_source(blob)
    if "__raw__" in files and files["__raw__"][:4] == b"%PDF":
        return None  # signal: no tex source, caller does PDF fallback
    tex_blobs = {n: b for n, b in files.items() if n.lower().endswith(".tex")}
    if not tex_blobs:
        return None
    tex_all = "\n".join(b.decode("utf-8", "ignore") for b in tex_blobs.values())
    tex_all = resolve_macros(tex_all)
    figs = parse_tex(tex_all)
    if not figs:
        return []
    os.makedirs(os.path.join(out_dir, aid), exist_ok=True)
    # index graphics files by basename for lookup
    by_base = {}
    for n, b in files.items():
        by_base[os.path.basename(n).lower()] = (n, b)
    rows = []
    for i, fig in enumerate(figs):
        saved = []
        for j, g in enumerate(fig["graphics"]):
            gb = os.path.basename(g).lower()
            cand = None
            if gb in by_base:
                cand = by_base[gb]
            else:
                for ext in IMG_EXT:
                    if (gb + ext) in by_base:
                        cand = by_base[gb + ext]
                        break
            if cand:
                name, data = cand
                ext = os.path.splitext(name)[1] or ".bin"
                suffix = "" if len(fig["graphics"]) == 1 else f"_{j}"
                dst = os.path.join(out_dir, aid, f"fig_{i:02d}{suffix}{ext}")
                with open(dst, "wb") as fo:
                    fo.write(data)
                png = rasterize_to_png(dst) if ext.lower() in (".pdf", ".eps", ".ps") else None
                saved.append(os.path.relpath(png if png else dst, out_dir))
        mentions, section = context_for(tex_all, fig["label"])
        cap = _clean(fig["caption"]) if fig["caption"] else None
        # consolidated ground-truth context the model's output is compared to
        explanation = " ".join(
            ([f"Caption: {cap}"] if cap else []) +
            ([f"In text: {' '.join(mentions)}"] if mentions else [])
        ).strip()
        rows.append({
            "arxiv_id": aid, "fig_index": i,
            "caption": cap, "label": fig["label"],
            "section": section,
            "mentions": mentions,
            "explanation": explanation,
            "images": saved, "source": "latex",
        })
    return rows

def extract_from_pdf(aid, out_dir):
    try:
        import fitz  # PyMuPDF
    except ImportError:
        sys.exit("pip install PyMuPDF  (needed for PDF fallback)")
    blob = fetch(f"https://arxiv.org/pdf/{aid}")
    os.makedirs(os.path.join(out_dir, aid), exist_ok=True)
    doc = fitz.open(stream=blob, filetype="pdf")
    rows, k = [], 0
    for pno in range(len(doc)):
        page = doc[pno]
        for img in page.get_images(full=True):
            xref = img[0]
            pix = fitz.Pixmap(doc, xref)
            if pix.n - pix.alpha >= 4:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            dst = os.path.join(out_dir, aid, f"fig_{k:02d}.png")
            pix.save(dst)
            rows.append({"arxiv_id": aid, "fig_index": k, "caption": None,
                         "label": None, "mentions": [],
                         "images": [os.path.relpath(dst, out_dir)],
                         "source": "pdf", "page": pno})
            k += 1
    # NOTE: PDF fallback gives images without reliable captions. For caption
    # alignment on PDFs use pdffigures2 instead.
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--prefer-tier", default="redistributable",
                    choices=["redistributable", "conditional", "any"])
    ap.add_argument("--sleep", type=float, default=3.0,
                    help="seconds between arXiv requests (be polite)")
    ap.add_argument("--pdf-fallback", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    papers = [json.loads(l) for l in open(args.manifest, encoding="utf-8") if l.strip()]

    def ok_tier(p):
        if args.prefer_tier == "any":
            return True
        if args.prefer_tier == "redistributable":
            return p["license_tier"] == "redistributable"
        return p["license_tier"] in ("redistributable", "conditional")

    papers = [p for p in papers if ok_tier(p)]
    # prioritise 2026 + ICSE/venue-tagged
    papers.sort(key=lambda p: (p["year"] == 2026,
                               bool(p.get("icse2026_title")) or p.get("venue_hint"),
                               p["year"]), reverse=True)
    papers = papers[:args.limit]

    idx_path = os.path.join(args.out_dir, "index.jsonl")
    n_fig = 0
    with open(idx_path, "w", encoding="utf-8") as idx:
        for n, p in enumerate(papers, 1):
            aid = p["id"]
            print(f"[{n}/{len(papers)}] {aid}  {p['license_name']}  "
                  f"{'ICSE' if p.get('icse2026_title') else ''}", file=sys.stderr)
            rows = None
            try:
                rows = extract_from_source(aid, args.out_dir)
            except Exception as e:
                print(f"    source failed: {e}", file=sys.stderr)
            if rows is None and args.pdf_fallback:
                try:
                    rows = extract_from_pdf(aid, args.out_dir)
                except Exception as e:
                    print(f"    pdf failed: {e}", file=sys.stderr)
            rows = rows or []
            meta = {**p, "n_figures": len(rows)}
            if rows:
                with open(os.path.join(args.out_dir, aid, "meta.json"),
                          "w", encoding="utf-8") as mf:
                    json.dump(meta, mf, ensure_ascii=False, indent=2)
            for r in rows:
                r["license_name"] = p["license_name"]
                r["license_tier"] = p["license_tier"]
                r["icse2026"] = bool(p.get("icse2026_title"))
                idx.write(json.dumps(r, ensure_ascii=False) + "\n")
                n_fig += 1
            time.sleep(args.sleep)
    print(f"[done] {n_fig} figures from {len(papers)} papers -> {idx_path}",
          file=sys.stderr)

if __name__ == "__main__":
    main()
