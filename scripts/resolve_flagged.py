#!/usr/bin/env python3
r"""
resolve_flagged.py -- for figures a human flagged as inaccurate, ask a strong
model to look at the image + the current draft + the human's specific critique,
and decide: is this a genuine visual error (fix it), or is the critique asking
for non-visual/analytical content that isn't actually depicted (keep the
visual-description approach, justify why)? Produces something a human can
confirm quickly rather than writing a correction from scratch.

Usage:
  python3 resolve_flagged.py --flagged flagged_input.jsonl --figures-dir figures --out resolved_flagged.jsonl
flagged_input.jsonl rows: {arxiv_id, fig_index, image, short_alt_draft, long_description_draft, critiques: [str, ...]}
"""
import argparse, base64, json, os, sys, time
import requests

API = "https://openrouter.ai/api/v1/chat/completions"
KEY_PATH = os.path.expanduser("~/.openrouter/api_key")
MODEL = "anthropic/claude-sonnet-5"

PROMPT_TMPL = """A human reviewer flagged the accessible description below as possibly \
inaccurate. Look at the IMAGE and decide which case this is:

(A) GENUINE VISUAL ERROR -- the critique points to something concretely wrong or \
missing that IS visible in the image (wrong count, wrong direction, misread label/icon, \
a specific legible value/trend that was omitted or stated wrong).
(B) NON-VISUAL EXPECTATION -- the critique wants analytical/causal/background narrative \
(the "why", domain context, the paper's argument) that is not actually depicted in the \
image. Describing only what's visible is CORRECT behavior for this task, not a flaw --
the description should not be rewritten to add things the reader can't verify from the \
image itself.

Current short alt text: {short_alt}
Current long description: {long_desc}
Current figure-type label: {figure_type}

Human critique(s) (some reviewers also flagged the figure-type label as wrong -- judge
that independently from the image too, regardless of the content verdict):
{critiques}

Output exactly these lines, no extra commentary:
VERDICT: genuine OR narrative-bias
FIGURE_TYPE: <the correct one of chart, diagram, mixed, other, based on the image -- \
keep the current label if it's already right>
NOTE: <one sentence explaining your call, for a human to quickly double-check>
SHORT: <corrected short alt text if genuine (fixing only what the critique identified), \
otherwise repeat the current one, possibly tightened if the critique found a real small error>
LONG: <corrected long description if genuine, otherwise repeat the current one (you may \
still incorporate any SPECIFIC legible value the critique mentions if it checks out \
against the image, even if you mark this narrative-bias overall)>
"""

def to_data_uri(path, max_dim=2000):
    import fitz
    pix = fitz.Pixmap(path)
    if max(pix.width, pix.height) > max_dim:
        scale = max_dim / max(pix.width, pix.height)
        pix = fitz.Pixmap(pix, int(pix.width * scale), int(pix.height * scale))
    b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")
    return f"data:image/png;base64,{b64}"

def already_done(out_path):
    done = set()
    if os.path.exists(out_path):
        for line in open(out_path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                done.add((r["arxiv_id"], r["fig_index"]))
            except (json.JSONDecodeError, KeyError):
                pass
    return done

def call(key, image_path, short_alt, long_desc, figure_type, critiques, timeout=90, retries=3):
    prompt = PROMPT_TMPL.format(short_alt=short_alt, long_desc=long_desc, figure_type=figure_type,
                                 critiques="\n".join(f"- {c}" for c in critiques))
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": to_data_uri(image_path)}},
        ]}],
        "max_tokens": 1600,
    }
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.post(API, headers={"Authorization": f"Bearer {key}"}, json=payload, timeout=timeout)
            if r.status_code == 429:
                time.sleep(5.0 * (attempt + 1))
                continue
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
            out = {"verdict": "", "figure_type": "", "note": "", "short_alt": "", "long_description": ""}
            cur = None
            for line in text.splitlines():
                s = line.strip()
                if s.startswith("VERDICT:"):
                    out["verdict"] = s.split(":", 1)[1].strip(); cur = None
                elif s.startswith("FIGURE_TYPE:"):
                    out["figure_type"] = s.split(":", 1)[1].strip().lower(); cur = None
                elif s.startswith("NOTE:"):
                    out["note"] = s.split(":", 1)[1].strip(); cur = None
                elif s.startswith("SHORT:"):
                    out["short_alt"] = s.split(":", 1)[1].strip(); cur = "short_alt"
                elif s.startswith("LONG:"):
                    out["long_description"] = s.split(":", 1)[1].strip(); cur = "long_description"
                elif cur:
                    out[cur] += " " + s
            return out, None
        except Exception as e:
            last_err = e
            time.sleep(2.0 * (attempt + 1))
    return None, str(last_err)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flagged", required=True)
    ap.add_argument("--figures-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    key = open(KEY_PATH, encoding="utf-8").read().strip()
    items = [json.loads(l) for l in open(args.flagged, encoding="utf-8") if l.strip()]
    done = already_done(args.out)
    todo = [it for it in items if (it["arxiv_id"], it["fig_index"]) not in done]
    print(f"[i] {len(items)} flagged, {len(done)} already resolved, {len(todo)} to resolve", file=sys.stderr)

    with open(args.out, "a", encoding="utf-8") as fout:
        for n, it in enumerate(todo, 1):
            img_path = os.path.join(args.figures_dir, it["image"])
            result, err = call(key, img_path, it["short_alt_draft"], it["long_description_draft"],
                                it.get("figure_type", "unknown"), it["critiques"])
            rec = {"arxiv_id": it["arxiv_id"], "fig_index": it["fig_index"],
                   "original_critiques": it["critiques"], "error": err, **(result or {})}
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fout.flush()
            print(f"[{n}/{len(todo)}] {it['arxiv_id']} fig{it['fig_index']}: "
                  f"{'ERR' if err else result['verdict']}", file=sys.stderr)

    print(f"[done] -> {args.out}", file=sys.stderr)

if __name__ == "__main__":
    main()
