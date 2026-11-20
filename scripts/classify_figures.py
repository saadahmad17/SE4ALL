#!/usr/bin/env python3
r"""
classify_figures.py  -- Stage 3: heuristic figure-type pass over index.jsonl.

Per CLAUDE.md's scope decision: statistical charts, SE diagrams
(architecture/UML/pipelines), or both? This is a lightweight keyword-based
heuristic over the caption + in-text mentions (no CV model -- not worth the
time against the deadline). It's meant to let you filter/balance the final
sample by type, and should be spot-checked, not trusted blindly.

Usage:
  python3 classify_figures.py --index figures/index.jsonl --out figures/index_typed.jsonl
"""
import argparse, json, re

CHART_TERMS = [
    "accuracy", "f1[- ]?score", "precision", "recall", "boxplot", "box plot",
    "bar chart", "bar graph", "histogram", "distribution", "correlation",
    "scatter ?plot", "trend", "comparison of", "performance of", "results for",
    "rq[123456]", "percentage", "average", "median", "auc", "roc curve",
    "line chart", "line graph", "violin plot", "heatmap", "heat map",
    "confusion matrix", "ablation", "number of \\w+ (across|per|by)",
    "statistics? of", "effect size", "p-value", "error bars?", "y-axis", "x-axis",
]
DIAGRAM_TERMS = [
    "architecture", "pipeline", "workflow", "work ?flow", "framework",
    "overview of (the|our)", "system design", "module", "component",
    "flowchart", "flow diagram", "uml", "sequence diagram", "class diagram",
    "approach overview", "methodology overview", "high-level (view|design)",
    "schematic", "illustration of (the|our)", "steps involved", "phases of",
    "stages? of", "block diagram", "data flow", "control flow",
]

CHART_RE = re.compile(r"\b(" + "|".join(CHART_TERMS) + r")s?\b", re.I)
DIAGRAM_RE = re.compile(r"\b(" + "|".join(DIAGRAM_TERMS) + r")s?\b", re.I)

def classify(text):
    text = text or ""
    c = len(CHART_RE.findall(text))
    d = len(DIAGRAM_RE.findall(text))
    if c == 0 and d == 0:
        return "other", c, d
    if c > 0 and d > 0 and min(c, d) / max(c, d) >= 0.5:
        return "mixed", c, d
    return ("chart", c, d) if c >= d else ("diagram", c, d)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    counts = {}
    with open(args.index, encoding="utf-8") as fin, open(args.out, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            text = " ".join(filter(None, [r.get("caption"), " ".join(r.get("mentions", []))]))
            ftype, c, d = classify(text)
            r["figure_type"] = ftype
            r["type_signals"] = {"chart": c, "diagram": d}
            fout.write(json.dumps(r, ensure_ascii=False) + "\n")
            counts[ftype] = counts.get(ftype, 0) + 1

    print(f"[done] classified {sum(counts.values())} figures -> {args.out}")
    print(f"       breakdown: {counts}")

if __name__ == "__main__":
    main()
