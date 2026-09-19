import json
import pathlib

from typed_judge.batch import Row
from typed_judge.recipes import draft_lint as dl
from typed_judge.verdict import apply

FIX = pathlib.Path(__file__).parent / "fixtures"
RESULTS = json.loads((FIX / "draft_lint_results.json").read_text(encoding="utf-8"))["results"]

# Эталон — пересчёт текущей формулой (hook как int >= 2) по сырым ответам замера 2026-09-17.
# verdict_code в фикстуре — вердикты ДО фикса hook (float 0.67), поэтому эталоном не служит.
GOLDEN = ["light_edit", "ready", "ready", "ready", "ready", "ready", "ready", "ready", "ready", "heavy_edit"]


def rows():
    return [Row(slug, f"k-{slug}", "gemini", dl.answers_from_gemini_row(r)) for slug, r in RESULTS.items()]


def test_golden_ten_verdicts_and_composites():
    v = apply(rows(), dl.combine)
    assert [x.verdict for x in v] == GOLDEN
    for x, (slug, r) in zip(v, RESULTS.items()):
        assert abs(x.score - r["composite"]) < 1e-3, slug


def test_agreement_with_model_is_9_of_10():
    v = apply(rows(), dl.combine)
    agree = sum(x.verdict == r["verdict_model"] for x, r in zip(v, RESULTS.values()))
    assert agree == 9


def test_questions_have_ten_ids_matching_formula():
    assert set(dl.QUESTIONS) == {"hook", "evidence", "symmetry", "hedging", "generic_conclusion",
                                 "tone", "one_idea", "top_defect", "readiness", "better_as_thread"}
    assert set(dl.VARIANTS) == {"factor", "holistic", "factor_en"}
