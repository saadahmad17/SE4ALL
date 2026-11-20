#!/usr/bin/env python3
"""make_charts.py -- paper figures from judged.jsonl, using the validated dataviz palette."""
import json, statistics
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

MODEL_LABELS = {
    "qwen/qwen3-vl-8b-instruct": "Qwen3-VL-8B",
    "meta-llama/llama-4-scout": "Llama-4-Scout",
    "google/gemma-3-27b-it": "Gemma-3-27B",
    "mistralai/mistral-small-3.2-24b-instruct": "Mistral-Small-3.2-24B",
    "openai/gpt-4o": "GPT-4o (closed)",
}
MODELS = list(MODEL_LABELS.keys())
# validated categorical slots 1-5 (blue, aqua, yellow, green, violet) -- fixed order, never cycled
COLORS = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7"]
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e0"

plt.rcParams.update({
    "font.size": 10, "text.color": TEXT_PRIMARY, "axes.edgecolor": GRID,
    "axes.labelcolor": TEXT_PRIMARY, "xtick.color": TEXT_SECONDARY, "ytick.color": TEXT_SECONDARY,
    "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": "white",
})

rows = [json.loads(l) for l in open("data/judged.jsonl", encoding="utf-8")]
CRITERIA = ["accuracy", "completeness", "message", "conciseness"]
CRIT_LABELS = ["Accuracy", "Completeness", "Message\nconveyed", "Conciseness"]

def agg(subset, key):
    return statistics.mean(r[key] for r in subset) if subset else None

# ---- Figure 1: grouped bar, 4 Likert criteria x 5 models ----
fig, ax = plt.subplots(figsize=(7, 3.2))
n_crit, n_model = len(CRITERIA), len(MODELS)
bar_w = 0.75 / n_model
x = range(n_crit)
for i, m in enumerate(MODELS):
    subset = [r for r in rows if r["model"] == m]
    vals = [agg(subset, c) for c in CRITERIA]
    xs = [xi + (i - n_model / 2 + 0.5) * bar_w for xi in x]
    bars = ax.bar(xs, vals, width=bar_w * 0.92, color=COLORS[i], label=MODEL_LABELS[m])
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.05, f"{v:.1f}", ha="center", va="bottom",
                 fontsize=6.5, color=TEXT_SECONDARY)
ax.set_xticks(list(x))
ax.set_xticklabels(CRIT_LABELS)
ax.set_ylabel("Mean score (1-5)")
ax.set_ylim(0, 5.6)
ax.yaxis.set_major_locator(mticker.MultipleLocator(1))
ax.grid(axis="y", color=GRID, linewidth=0.7, zorder=0)
ax.set_axisbelow(True)
ax.legend(ncol=3, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, 1.22), frameon=False)
fig.tight_layout()
fig.savefig("paper/figures/scores_by_criterion.png", dpi=220)
plt.close(fig)

# ---- Figure 2: hallucination rate bar chart, sorted descending ----
fig, ax = plt.subplots(figsize=(5.2, 2.6))
halluc = []
for m in MODELS:
    subset = [r for r in rows if r["model"] == m]
    rate = 100 * sum(1 for r in subset if r["hallucination"]) / len(subset)
    halluc.append((m, rate))
halluc.sort(key=lambda t: t[1])
labels = [MODEL_LABELS[m] for m, _ in halluc]
rates = [r for _, r in halluc]
colors_sorted = [COLORS[MODELS.index(m)] for m, _ in halluc]
bars = ax.barh(labels, rates, color=colors_sorted, height=0.6)
for b, v in zip(bars, rates):
    ax.text(v + 1.5, b.get_y() + b.get_height() / 2, f"{v:.1f}%", va="center", fontsize=8, color=TEXT_PRIMARY)
ax.set_xlabel("Hallucination rate (% of descriptions)")
ax.set_xlim(0, 100)
ax.grid(axis="x", color=GRID, linewidth=0.7, zorder=0)
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig("paper/figures/hallucination_rate.png", dpi=220)
plt.close(fig)

# ---- Figure 3 (combined): heatmap (top) + error-type breakdown (bottom) ----
# merged into one figure to save a float's caption/spacing overhead against the
# 5-page short-paper limit -- both panels are "the deeper breakdown", referenced
# together in the same results paragraph, so one figure with two panels reads naturally.
types = ["chart", "diagram", "mixed", "other"]
type_labels = ["Chart", "Diagram", "Mixed", "Other"]
grid = []
for m in MODELS:
    row = []
    for t in types:
        subset = [r for r in rows if r["model"] == m and r["figure_type"] == t]
        row.append(100 * sum(1 for r in subset if r["hallucination"]) / len(subset) if subset else float("nan"))
    grid.append(row)

from matplotlib.colors import LinearSegmentedColormap
blue_ramp = LinearSegmentedColormap.from_list("seq_blue", ["#cde2fb", "#1c5cab"])

breakdown = json.load(open("data/error_category_breakdown.json", encoding="utf-8"))
CATS = ["misidentification", "trend_direction", "miscount", "fabricated_detail",
        "ranking_comparison", "numeric_magnitude", "other"]
CAT_LABELS = ["Misident.", "Trend/dir.\nreversal", "Miscount", "Fabricated\ndetail",
              "Ranking/\ncompare", "Numeric\nmagnitude", "Other"]
CAT_COLORS = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948", "#b9b8b2"]

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(5.2, 5.6), gridspec_kw={"height_ratios": [1, 1.1]})

im = ax1.imshow(grid, cmap=blue_ramp, vmin=0, vmax=100, aspect="auto")
ax1.set_xticks(range(len(types))); ax1.set_xticklabels(type_labels)
ax1.set_yticks(range(len(MODELS))); ax1.set_yticklabels([MODEL_LABELS[m] for m in MODELS], fontsize=8)
for i in range(len(MODELS)):
    for j in range(len(types)):
        v = grid[i][j]
        if v == v:
            ax1.text(j, i, f"{v:.0f}%", ha="center", va="center", fontsize=7.5,
                      color="white" if v > 55 else TEXT_PRIMARY)
ax1.set_xticks([x - 0.5 for x in range(1, len(types))], minor=True)
ax1.set_yticks([y - 0.5 for y in range(1, len(MODELS))], minor=True)
ax1.grid(which="minor", color="white", linewidth=2)
ax1.tick_params(which="minor", bottom=False, left=False)
ax1.set_title("(a) Hallucination rate by figure type", fontsize=9, loc="left")
cbar = fig.colorbar(im, ax=ax1, fraction=0.046, pad=0.04)
cbar.ax.tick_params(labelsize=7)

model_order = sorted(MODELS, key=lambda m: sum(breakdown[m].values()))
labels = [MODEL_LABELS[m] for m in model_order]
lefts = [0] * len(model_order)
for cat, color, catlabel in zip(CATS, CAT_COLORS, CAT_LABELS):
    totals = [sum(breakdown[m].values()) for m in model_order]
    vals = [100 * breakdown[m][cat] / t if t else 0 for m, t in zip(model_order, totals)]
    bars = ax2.barh(labels, vals, left=lefts, color=color, height=0.6, label=catlabel)
    for b, v in zip(bars, vals):
        if v >= 9:
            ax2.text(b.get_x() + v / 2, b.get_y() + b.get_height() / 2, f"{v:.0f}",
                      ha="center", va="center", fontsize=6.5,
                      color="white" if cat in ("misidentification", "fabricated_detail", "ranking_comparison", "numeric_magnitude") else TEXT_PRIMARY)
    lefts = [l + v for l, v in zip(lefts, vals)]
ax2.set_xlim(0, 100)
ax2.set_xlabel("Share of this model's hallucinations (%)", fontsize=8)
ax2.set_title("(b) Error-type breakdown", fontsize=9, loc="left")
ax2.legend(ncol=4, fontsize=5.8, loc="upper center", bbox_to_anchor=(0.5, -0.28), frameon=False)
ax2.tick_params(labelsize=8)

fig.tight_layout()
fig.savefig("paper/figures/error_analysis.png", dpi=220)
plt.close(fig)

print("wrote: scores_by_criterion.png, hallucination_rate.png, error_analysis.png (combined)")
