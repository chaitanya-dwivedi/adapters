"""Rubric scorer for BigLaw Bench (LLM judge, stdlib only).

Score = (sum of points of satisfied affirmative criteria
         - sum of penalties for judged errors) / total affirmative points,
clamped to [0, 1].
"""

import argparse
import json
import os
import re
import sys
import urllib.request

POS_RE = re.compile(r"\((\d+(?:\.\d+)?)\s*points?\)\s*$", re.I)
NEG_RE = re.compile(r"^\s*(?:\d+\.\s*)?-\s*(\d+(?:\.\d+)?)\s*points?\s+for\s+(?:every|each)\s+(.+?)\s*$", re.I)


def parse_rubric(text: str):
    """Return (positives, negatives). positives: [{id,text,points}], negatives: [{id,text,penalty}]."""
    positives, negatives = [], []
    in_neg = False
    for line in text.splitlines():
        s = line.strip()
        if re.match(r"^negative points", s, re.I):
            in_neg = True
            continue
        if in_neg:
            m = NEG_RE.match(s)
            if m:
                negatives.append({"id": f"n{len(negatives)+1}", "text": m.group(2), "penalty": float(m.group(1))})
            continue
        m = POS_RE.search(s)
        if m:
            body = POS_RE.sub("", s).strip()
            body = re.sub(r"^[a-zA-Z0-9]+\.?\s+(?=[A-Z])", "", body)  # strip "a." / "iv." labels
            positives.append({"id": f"p{len(positives)+1}", "text": body, "points": float(m.group(1))})
    return positives, negatives


def compute_score(positives, negatives, verdict: dict) -> float:
    total = sum(p["points"] for p in positives)
    if total <= 0:
        return 0.0
    met = verdict.get("criteria", {})
    counts = verdict.get("negatives", {})
    net = sum(p["points"] for p in positives if met.get(p["id"]) is True)
    for n in negatives:
        c = counts.get(n["id"], 0)
        try:
            c = max(0.0, float(c))
        except (TypeError, ValueError):
            c = 0.0
        net -= n["penalty"] * c
    return max(0.0, min(1.0, net / total))


def build_prompt(positives, negatives, answer: str) -> str:
    crit = "\n".join(f'{p["id"]}: {p["text"]}' for p in positives)
    neg = "\n".join(f'{n["id"]}: number of {n["text"]}' for n in negatives)
    return (
        "You are a strict grader of legal work product. Grade the RESPONSE against the rubric.\n"
        "For each affirmative criterion, answer true only if the response clearly satisfies it, else false.\n"
        "For each negative item, give the integer count of occurrences in the response "
        "(hallucination = a statement not supported by the source documents or false; "
        "extraneous/irrelevant = accurate but unnecessary or irrelevant to the task).\n"
        'Return ONLY JSON: {"criteria": {"p1": true, ...}, "negatives": {"n1": 0, ...}}\n\n'
        f"AFFIRMATIVE CRITERIA:\n{crit}\n\nNEGATIVE ITEMS:\n{neg}\n\n"
        f"RESPONSE:\n<<<\n{answer}\n>>>\n"
    )


def call_judge(prompt: str) -> dict:
    key = os.environ.get("JUDGE_API_KEY", "")
    base = os.environ.get("JUDGE_BASE_URL", "https://app.ppapi.ai/").rstrip("/")
    model = os.environ.get("JUDGE_MODEL", "gpt-5-2025-08-07")
    if not key:
        raise RuntimeError("JUDGE_API_KEY is not set")
    url = base + "/chat/completions" if base.endswith("/v1") else base + "/v1/chat/completions"
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        content = json.load(r)["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", content, re.S)
    return json.loads(m.group(0))


def main(judge=call_judge) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rubric", required=True)
    ap.add_argument("--answer", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    positives, negatives = parse_rubric(open(a.rubric, encoding="utf-8").read())
    if not os.path.exists(a.answer):
        print("answer file missing", file=sys.stderr)
        open(a.out, "w").write("0\n")
        return 0
    answer = open(a.answer, encoding="utf-8", errors="replace").read()
    if not answer.strip():
        open(a.out, "w").write("0\n")
        return 0
    verdict = None
    for attempt in range(3):
        try:
            verdict = judge(build_prompt(positives, negatives, answer))
            break
        except Exception as e:  # noqa: BLE001
            print(f"judge attempt {attempt+1} failed: {e}", file=sys.stderr)
    if verdict is None:
        print("judge unavailable; no reward written", file=sys.stderr)
        return 1
    score = compute_score(positives, negatives, verdict)
    print(json.dumps({"verdict": verdict, "score": score}))
    open(a.out, "w").write(f"{score:.4f}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
