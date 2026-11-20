#!/usr/bin/env python3
r"""
judge_descriptions.py -- Stage 5b. Scores each model-generated description in
generations.jsonl against the human-verified reference, grounded in the image
itself (same as what the model under test had to work from).

Usage:
  python3 judge_descriptions.py --generations generations.jsonl \
      --references reference_descriptions.jsonl --figures-dir figures --out judged.jsonl
"""
import argparse, base64, json, os, sys, time
import requests

API = "https://openrouter.ai/api/v1/chat/completions"
KEY_PATH = os.path.expanduser("~/.openrouter/api_key")
JUDGE_MODEL = "anthropic/claude-sonnet-5"

PROMPT_TMPL = """You are judging an AI-generated accessible description of a figure from \
a software engineering paper, written for a blind or low-vision reader. Score it against \
the human-verified reference description, grounding your judgment in the IMAGE itself \
(not just whether the wording matches the reference -- valid paraphrases are fine).

HUMAN REFERENCE (short alt + long description):
SHORT: {ref_short}
LONG: {ref_long}

MODEL-GENERATED DESCRIPTION BEING JUDGED:
{candidate}

Score on these five criteria:

1. FACTUAL ACCURACY (1-5): do stated values/trends/structure match the figure and the \
reference? 5 = fully accurate, 1 = mostly wrong.
2. HALLUCINATION (yes/no): does it assert something specific (a value, direction, label, \
relationship) that is NOT supported by the image/reference, i.e. invented or contradicted? \
If yes, state the specific hallucinated claim.
3. COMPLETENESS (1-5): does it cover what a BLV reader needs (structure + key data + \
takeaway), per the reference, or omit important elements? 5 = complete, 1 = major gaps.
4. MESSAGE CONVEYED (1-5): does it communicate why the figure matters / its takeaway, not \
just literal visual facts? 5 = clearly conveys the point, 1 = no sense of why it matters.
5. CONCISENESS (1-5): WCAG-appropriate brevity without sacrificing the above. 5 = \
appropriately concise, 1 = way too verbose or too terse to be useful.

Output exactly these lines, no extra commentary:
ACCURACY: <1-5>
HALLUCINATION: yes OR no
HALLUCINATION_CLAIM: <the specific false claim if yes, else "none">
COMPLETENESS: <1-5>
MESSAGE: <1-5>
CONCISENESS: <1-5>
RATIONALE: <1-2 sentences justifying the scores, for a human to spot-check>
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
                done.add((r["arxiv_id"], r["fig_index"], r["model"]))
            except (json.JSONDecodeError, KeyError):
                pass
    return done

def parse_int(s, default=None):
    try:
        return int("".join(c for c in s if c.isdigit()))
    except (ValueError, TypeError):
        return default

def call_judge(key, image_path, ref, candidate, timeout=90, retries=3):
    prompt = PROMPT_TMPL.format(ref_short=ref["short_alt"], ref_long=ref["long_description"],
                                 candidate=candidate)
    payload = {
        "model": JUDGE_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": to_data_uri(image_path)}},
        ]}],
        "max_tokens": 500,
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
            out = {"accuracy": None, "hallucination": None, "hallucination_claim": "",
                   "completeness": None, "message": None, "conciseness": None, "rationale": ""}
            cur = None
            for line in text.splitlines():
                s = line.strip()
                if s.startswith("ACCURACY:"):
                    out["accuracy"] = parse_int(s.split(":", 1)[1]); cur = None
                elif s.startswith("HALLUCINATION_CLAIM:"):
                    out["hallucination_claim"] = s.split(":", 1)[1].strip(); cur = "hallucination_claim"
                elif s.startswith("HALLUCINATION:"):
                    v = s.split(":", 1)[1].strip().lower()
                    out["hallucination"] = v.startswith("y"); cur = None
                elif s.startswith("COMPLETENESS:"):
                    out["completeness"] = parse_int(s.split(":", 1)[1]); cur = None
                elif s.startswith("MESSAGE:"):
                    out["message"] = parse_int(s.split(":", 1)[1]); cur = None
                elif s.startswith("CONCISENESS:"):
                    out["conciseness"] = parse_int(s.split(":", 1)[1]); cur = None
                elif s.startswith("RATIONALE:"):
                    out["rationale"] = s.split(":", 1)[1].strip(); cur = "rationale"
                elif cur:
                    out[cur] += " " + s
            return out, None
        except Exception as e:
            last_err = e
            time.sleep(2.0 * (attempt + 1))
    return None, str(last_err)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generations", required=True)
    ap.add_argument("--references", required=True)
    ap.add_argument("--figures-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    key = open(KEY_PATH, encoding="utf-8").read().strip()
    gens = [json.loads(l) for l in open(args.generations, encoding="utf-8") if l.strip()]
    refs = {(r["arxiv_id"], r["fig_index"]): r for l in open(args.references, encoding="utf-8")
            for r in [json.loads(l)] if l.strip()}
    sample = {(r["arxiv_id"], r["fig_index"]): r for l in open("data/figures/sample.jsonl", encoding="utf-8")
              for r in [json.loads(l)]}

    scoreable = [g for g in gens if (g["arxiv_id"], g["fig_index"]) in refs and g.get("description")]
    print(f"[i] {len(gens)} generations, {len(scoreable)} have a reviewed reference + non-error description",
          file=sys.stderr)

    done = already_done(args.out)
    todo = [g for g in scoreable if (g["arxiv_id"], g["fig_index"], g["model"]) not in done]
    print(f"[i] {len(done)} already judged, {len(todo)} to judge", file=sys.stderr)

    with open(args.out, "a", encoding="utf-8") as fout:
        for n, g in enumerate(todo, 1):
            key_ = (g["arxiv_id"], g["fig_index"])
            ref = refs[key_]
            img_path = os.path.join(args.figures_dir, sample[key_]["images"][0])
            result, err = call_judge(key, img_path, ref, g["description"])
            rec = {"arxiv_id": g["arxiv_id"], "fig_index": g["fig_index"], "model": g["model"],
                   "figure_type": ref["figure_type"], "error": err, **(result or {})}
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fout.flush()
            print(f"[{n}/{len(todo)}] {g['arxiv_id']} fig{g['fig_index']} {g['model']}: "
                  f"{'ERR' if err else ('HALLUC' if result['hallucination'] else 'ok')}", file=sys.stderr)

    print(f"[done] -> {args.out}", file=sys.stderr)

if __name__ == "__main__":
    main()
