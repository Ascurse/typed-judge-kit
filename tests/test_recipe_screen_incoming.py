import pathlib

from typed_judge.batch import read_rows
from typed_judge.questions import Answer
from typed_judge.recipes import screen_incoming as si
from typed_judge.verdict import apply

FIX = pathlib.Path(__file__).parent / "fixtures"

# Эталон — живой прогон typesafe (jev-latest) 2026-09-20, кэш screen_incoming_run.jsonl.
GOLDEN = {"borderline": "pass", "clean-article": "pass", "forward-injection": "block",
          "hidden-directive": "block", "promo": "skip", "tg-drosophila": "pass"}


def test_golden_verdicts_from_live_typesafe_run():
    rows = read_rows(FIX / "screen_incoming_run.jsonl")
    assert {v.item_id: v.verdict for v in apply(rows, si.combine)} == GOLDEN


def test_questions_ids_match_formula():
    assert set(si.QUESTIONS) == {"injection", "relevance", "noise", "hazard"}


def test_hazard_alone_blocks_and_injection_outranks_noise():
    base = {"injection": Answer(probability=0.1), "relevance": Answer(probability=0.9),
            "noise": Answer(probability=0.1), "hazard": Answer(value=0.0)}
    assert si.combine(base)[1] == "pass"
    assert si.combine({**base, "hazard": Answer(value=2.0)})[1] == "block"
    assert si.combine({**base, "injection": Answer(probability=0.5), "noise": Answer(probability=0.9)})[1] == "block"
    assert si.combine({**base, "relevance": Answer(probability=0.4)})[1] == "review"
