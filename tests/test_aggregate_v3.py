"""Агрегация v3 (бид typed-judge-kit-wnh): единичные веса + вето критического класса.

Пороги — из предрегистрации (vault measurements/Агрегация v3 единичные веса — предрегистрация
2026-09-20.md), зафиксированы до прогона на метках.
"""
import pytest

from typed_judge.questions import Answer
from typed_judge.recipes import draft_lint_v3 as v3


def answers(**probs) -> dict[str, Answer]:
    """Все вопросы v3 без дефектов; именованные аргументы поднимают вероятность дефекта."""
    out = {qid: Answer(probability=0.0) for qid in v3.STYLE_DEFECTS + v3.CRITICAL_DEFECTS}
    for qid, p in probs.items():
        out[qid] = Answer(probability=p)
    return out


def test_no_defects_is_ready():
    score, verdict = v3.combine(answers())
    assert (score, verdict) == (1.0, "ready")


@pytest.mark.parametrize("n_defects,expected", [(0, "ready"), (1, "light_edit"), (2, "light_edit"),
                                                (3, "heavy_edit"), (8, "heavy_edit")])
def test_verdict_zones_by_defect_count(n_defects, expected):
    a = answers(**{qid: 0.9 for qid in v3.STYLE_DEFECTS[:n_defects]})
    assert v3.combine(a)[1] == expected


def test_score_is_monotone_in_defect_count():
    scores = [v3.combine(answers(**{q: 0.9 for q in v3.STYLE_DEFECTS[:n]}))[0] for n in range(9)]
    assert scores == sorted(scores, reverse=True)
    assert len(set(scores)) == 9


def test_unit_weights_defects_are_interchangeable():
    """Единичные веса: какой именно стилистический дефект сработал — не влияет на вердикт."""
    verdicts = {v3.combine(answers(**{qid: 0.9}))[1] for qid in v3.STYLE_DEFECTS}
    assert verdicts == {"light_edit"}


@pytest.mark.parametrize("qid", ["overclaim"])  # бид 08p: unsourced выведен из вето
def test_critical_vetoes_any_score(qid):
    """critical=1 при любом score → вето (вердикт heavy_edit даже на идеальном стиле)."""
    score, verdict = v3.combine(answers(**{qid: v3.OVERCLAIM_THRESHOLD}))
    assert verdict == "heavy_edit"
    assert score == 1.0, "вето не подменяет score — оно меняет только вердикт"


@pytest.mark.parametrize("qid", ["overclaim"])
def test_critical_below_threshold_does_not_veto(qid):
    assert v3.combine(answers(**{qid: v3.OVERCLAIM_THRESHOLD - 0.01}))[1] == "ready"


def test_critical_not_counted_in_additive_sum():
    """critical=0 → вердикт только от суммы стилистических; критические вопросы в сумму не входят."""
    a = answers(overclaim=0.5, hedging=0.9)
    assert v3.combine(a) == (0.875, "light_edit")


def test_binarization_at_half():
    assert v3.combine(answers(hedging=0.49))[1] == "ready"
    assert v3.combine(answers(hedging=0.5))[1] == "light_edit"


def test_confidence_not_used():
    """Verbalized confidence из формулы убрана (DR-63, ранг 4)."""
    low = answers(hedging=0.9)
    high = {qid: Answer(probability=a.probability, confidence=0.99) for qid, a in low.items()}
    assert v3.combine(low) == v3.combine(high)


def test_classes_cover_all_probability_questions():
    """Ни один Noul-вопрос рецепта не потерян между классами."""
    noul_qids = {qid for qid, q in v3.QUESTIONS.items() if q.__class__.__name__ == "Noul"}
    assert noul_qids - {"better_as_thread"} == (
        set(v3.STYLE_DEFECTS) | set(v3.CRITICAL_DEFECTS) | set(v3.REPORTED_ONLY)
    )
