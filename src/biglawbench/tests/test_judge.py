"""Unit tests for the rubric scorer with a mocked judge (no network)."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "biglawbench" / "task-template" / "tests"
spec = importlib.util.spec_from_file_location("judge", ROOT / "judge.py")
judge = importlib.util.module_from_spec(spec)
sys.modules["judge"] = judge
spec.loader.exec_module(judge)

RUBRIC = """Affirmative Points:

1. Structure:
        a. Does the response give background? (1 point)
2. Substance:
        a. Does the response state X? (2 points)
        b. Does the response state Y? (1 point)

Negative Points:

1. -1 point for every hallucination
2. -0.5 points for every statement of accurate but extraneous or irrelevant information
"""


def test_parse():
    pos, neg = judge.parse_rubric(RUBRIC)
    assert [p["points"] for p in pos] == [1, 2, 1]
    assert [n["penalty"] for n in neg] == [1, 0.5]


def test_scores():
    pos, neg = judge.parse_rubric(RUBRIC)
    allv = {"criteria": {"p1": True, "p2": True, "p3": True}, "negatives": {"n1": 0, "n2": 0}}
    assert judge.compute_score(pos, neg, allv) == 1.0
    part = {"criteria": {"p1": True, "p2": False, "p3": True}, "negatives": {"n1": 1, "n2": 1}}
    assert judge.compute_score(pos, neg, part) == 0.125  # net 2-1.5=0.5 -> 0.125

def test_partial_and_clamp():
    pos, neg = judge.parse_rubric(RUBRIC)
    v = {"criteria": {"p1": True, "p2": True, "p3": False}, "negatives": {"n1": 1, "n2": 0}}
    assert judge.compute_score(pos, neg, v) == (3 - 1) / 4
    v = {"criteria": {}, "negatives": {"n1": 5}}
    assert judge.compute_score(pos, neg, v) == 0.0


def test_all_real_rubrics(tmp_path=None):
    import glob
    for f in glob.glob("/tmp/blb/datasets/*/tests/rubric.md"):
        pos, neg = judge.parse_rubric(open(f).read())
        assert pos and len(neg) == 2
