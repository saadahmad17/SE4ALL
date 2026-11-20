#!/usr/bin/env python3
r"""
build_labeling_tool.py -- generates a self-contained local HTML tool for
authoring the Layer-2 WCAG reference descriptions (the benchmark's ground
truth). Per CLAUDE.md this is meant to be a SMALL gold set, not all sampled
figures -- default --n 25, stratified by figure_type, drawn from the same
sample the models were run on. Images are embedded as base64 data URIs so
the tool has zero dependency on relative file paths / browser file access.

Usage:
  python3 build_labeling_tool.py --sample figures/sample.jsonl --figures-dir figures --out labeling_tool.html --n 25
"""
import argparse, base64, json, mimetypes, os, random, collections

TEMPLATE = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>WCAG Reference Description Labeling</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, system-ui, sans-serif; margin: 0; display: flex; height: 100vh; }
  #sidebar { width: 220px; overflow-y: auto; border-right: 1px solid #8884; padding: 8px; flex-shrink: 0; }
  #sidebar div { padding: 4px 6px; cursor: pointer; border-radius: 4px; font-size: 13px; }
  #sidebar div:hover { background: #8882; }
  #sidebar div.active { background: #4af3; font-weight: 600; }
  #sidebar div.done::before { content: "✓ "; color: #2a8f4a; }
  #main { flex: 1; overflow-y: auto; padding: 20px 28px; max-width: 900px; }
  img { max-width: 100%; max-height: 420px; border: 1px solid #8884; border-radius: 6px; display: block; margin: 10px 0; }
  .meta { font-size: 13px; opacity: 0.75; margin-bottom: 8px; }
  .context { background: #8881; border-radius: 6px; padding: 10px 14px; font-size: 14px; margin: 10px 0; max-height: 160px; overflow-y: auto; }
  .context summary { cursor: pointer; font-weight: 600; }
  label { display: block; font-weight: 600; margin-top: 16px; }
  .hint { font-size: 12px; opacity: 0.7; font-weight: 400; }
  input[type=text], textarea { width: 100%; box-sizing: border-box; font-size: 14px; padding: 8px; border-radius: 6px; border: 1px solid #8886; margin-top: 4px; font-family: inherit; }
  textarea { min-height: 90px; resize: vertical; }
  .row { display: flex; gap: 10px; align-items: center; margin-top: 14px; }
  button { padding: 8px 14px; border-radius: 6px; border: 1px solid #8886; cursor: pointer; font-size: 14px; }
  #progress { font-size: 13px; opacity: 0.8; margin-left: auto; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; background: #4af3; font-size: 12px; margin-left: 8px; }
</style>
</head>
<body>
<div id="sidebar"></div>
<div id="main"></div>
<script>
const FIGURES = __FIGURES_JSON__;
const STORAGE_KEY = "wcag_labels_v2";

function loadLabels() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; } catch(e) { return {}; }
}
function saveLabels(labels) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(labels));
}
function keyOf(f) { return f.arxiv_id + "#" + f.fig_index; }

let labels = loadLabels();
let current = 0;

function renderSidebar() {
  const sb = document.getElementById("sidebar");
  sb.innerHTML = "";
  const doneCount = FIGURES.filter(f => labels[keyOf(f)] && labels[keyOf(f)].reviewed).length;
  const header = document.createElement("div");
  header.style.fontWeight = "700";
  header.style.marginBottom = "6px";
  header.textContent = `${doneCount}/${FIGURES.length} reviewed & approved`;
  sb.appendChild(header);
  FIGURES.forEach((f, i) => {
    const d = document.createElement("div");
    const l = labels[keyOf(f)];
    if (l && l.reviewed) d.className = "done";
    if (i === current) d.className = (d.className || "") + " active";
    d.textContent = `${i+1}. ${f.arxiv_id} fig${f.fig_index} (${f.figure_type})`;
    d.onclick = () => { save(); current = i; render(); };
    sb.appendChild(d);
  });
}

function save() {
  const f = FIGURES[current];
  labels[keyOf(f)] = {
    figure_type: document.getElementById("type_override").value,
    short_alt: document.getElementById("short_alt").value,
    long_description: document.getElementById("long_description").value,
    notes: document.getElementById("notes").value,
    reviewed: document.getElementById("reviewed").checked,
  };
  saveLabels(labels);
}

function render() {
  const f = FIGURES[current];
  const l = labels[keyOf(f)] || {};
  const img = f.images[0];
  const ctxParts = [];
  if (f.caption) ctxParts.push("<b>Caption:</b> " + f.caption);
  if (f.mentions && f.mentions.length) ctxParts.push("<b>In-text mentions:</b> " + f.mentions.join(" / "));
  const hasDraft = f.draft_short_alt || f.draft_long_description;
  const shortVal = l.short_alt || f.draft_short_alt || "";
  const longVal = l.long_description || f.draft_long_description || "";
  const main = document.getElementById("main");
  main.innerHTML = `
    <div class="meta">${f.arxiv_id} &middot; figure ${f.fig_index} &middot; section: ${f.section || "?"}
      <span class="badge">${f.figure_type}</span></div>
    <img src="${img}">
    <details class="context" open><summary>Extracted context (sighted-reader text -- for reference, don't just paraphrase this)</summary>
      ${ctxParts.join("<br><br>") || "<i>none extracted</i>"}
    </details>
    ${hasDraft ? '<p class="hint" style="color:#c80">⚠ Fields below are pre-filled with an UNREVIEWED LLM draft. Read carefully, correct anything wrong, then tick "reviewed" below.</p>' : ""}
    <label>Figure type override <span class="hint">(fix if the heuristic got it wrong)</span>
      <select id="type_override">
        ${["chart","diagram","mixed","other"].map(t => `<option value="${t}" ${t===(l.figure_type||f.figure_type)?"selected":""}>${t}</option>`).join("")}
      </select>
    </label>
    <label>Short alt text <span class="hint">(~15 words, functional one-liner)</span>
      <input type="text" id="short_alt" value="${shortVal.replace(/"/g,'&quot;')}">
    </label>
    <label>Long description <span class="hint">(3-6 sentences: what kind of figure + structure + key trend/message/takeaway; specific values only if essential; say "illegible" rather than guessing)</span>
      <textarea id="long_description">${longVal}</textarea>
    </label>
    <label>Notes <span class="hint">(optional -- flag anything uncertain/approximate)</span>
      <textarea id="notes">${l.notes||""}</textarea>
    </label>
    <label style="display:flex; align-items:center; gap:8px; font-weight:600;">
      <input type="checkbox" id="reviewed" style="width:auto;" ${l.reviewed ? "checked" : ""}>
      I have read this against the image and approve it as accurate
    </label>
    <div class="row">
      <button onclick="go(-1)">&larr; Prev</button>
      <button onclick="go(1)">Next &rarr;</button>
      <button onclick="exportJSON()">Export JSON</button>
      <span id="progress"></span>
    </div>
  `;
  ["type_override","short_alt","long_description","notes","reviewed"].forEach(id => {
    document.getElementById(id).addEventListener("input", () => { save(); renderSidebar(); });
  });
  renderSidebar();
}

function go(delta) {
  save();
  current = Math.max(0, Math.min(FIGURES.length - 1, current + delta));
  render();
}

function exportJSON() {
  save();
  const unreviewed = FIGURES.filter(f => !(labels[keyOf(f)] && labels[keyOf(f)].reviewed));
  if (unreviewed.length) {
    alert(`${unreviewed.length} figure(s) not yet reviewed/approved -- exporting anyway, but check the "reviewed" box on each before this is final.`);
  }
  const out = FIGURES.map(f => {
    const l = labels[keyOf(f)] || {};
    return { arxiv_id: f.arxiv_id, fig_index: f.fig_index,
             figure_type: l.figure_type || f.figure_type,
             short_alt: l.short_alt || "", long_description: l.long_description || "",
             notes: l.notes || "", reviewed: !!l.reviewed };
  });
  const blob = new Blob([out.map(r => JSON.stringify(r)).join("\n")], {type: "application/jsonl"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "reference_descriptions.jsonl";
  a.click();
}

render();
</script>
</body>
</html>
"""

def to_data_uri(path):
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"

def stratified_subset(rows, n, seed=42):
    by_type = collections.defaultdict(list)
    for r in rows:
        by_type[r["figure_type"]].append(r)
    rng = random.Random(seed)
    for v in by_type.values():
        rng.shuffle(v)
    total = len(rows)
    picked = []
    for items in by_type.values():
        k = max(1, round(n * len(items) / total))
        picked.extend(items[:k])
    rng.shuffle(picked)
    return picked[:n]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True)
    ap.add_argument("--figures-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=25, help="gold-set size (CLAUDE.md: keep this small)")
    ap.add_argument("--drafts", default=None, help="optional draft_references.jsonl to pre-fill (still requires human review)")
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.sample, encoding="utf-8") if l.strip()]
    gold = stratified_subset(rows, args.n)

    drafts = {}
    if args.drafts and os.path.exists(args.drafts):
        for line in open(args.drafts, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            drafts[(d["arxiv_id"], d["fig_index"])] = d

    trimmed = [{
        "arxiv_id": r["arxiv_id"], "fig_index": r["fig_index"], "section": r.get("section"),
        "caption": r.get("caption"), "mentions": r.get("mentions", []),
        "images": [to_data_uri(os.path.join(args.figures_dir, r["images"][0]))],
        "figure_type": r.get("figure_type"),
        "draft_short_alt": drafts.get((r["arxiv_id"], r["fig_index"]), {}).get("short_alt_draft", ""),
        "draft_long_description": drafts.get((r["arxiv_id"], r["fig_index"]), {}).get("long_description_draft", ""),
    } for r in gold]

    html = TEMPLATE.replace("__FIGURES_JSON__", json.dumps(trimmed, ensure_ascii=False))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[done] gold set: {len(trimmed)} figures -> {args.out}")
    import collections as c
    print("       type breakdown:", dict(c.Counter(r["figure_type"] for r in gold)))

if __name__ == "__main__":
    main()
