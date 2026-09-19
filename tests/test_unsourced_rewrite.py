"""Три варианта переформулировки unsourced (bead typed-judge-kit-08p).

unsourced_v0/unsourced_a — обычные Noul, вероятность приходит от движка как есть.
unsourced_b расщеплён на два вопроса (есть ли проверяемое утверждение / указан ли источник) —
конъюнкция считается в коде (variant_b_probability), а не в промпте, поэтому у неё есть
отдельный тест на голых числах, без сети.
"""
import pytest

from typed_judge.unsourced_rewrite import QUESTIONS, variant_b_probability


def test_variant_b_probability_fires_when_claim_present_and_source_absent():
    assert variant_b_probability(has_claim=1.0, has_source=0.0) == 1.0


def test_variant_b_probability_does_not_fire_when_source_present():
    assert variant_b_probability(has_claim=1.0, has_source=1.0) == 0.0


def test_variant_b_probability_does_not_fire_when_no_claim_at_all():
    """ru_messy-тексты без проверяемых утверждений — дефекта unsourced нет, даже если источника и не могло быть."""
    assert variant_b_probability(has_claim=0.0, has_source=0.0) == 0.0


def test_variant_b_probability_is_product_under_partial_confidence():
    assert variant_b_probability(has_claim=0.8, has_source=0.2) == pytest.approx(0.64)


def test_questions_dict_has_all_four_variant_questions():
    assert set(QUESTIONS) == {
        "unsourced_v0", "unsourced_a", "unsourced_b_has_claim", "unsourced_b_has_source",
    }


def test_unsourced_v0_baseline_is_frozen():
    """Базовая линия замера заморожена копией: в рецепте вопрос уже расщеплён (бид 08p),
    и импорт оттуда молча подменил бы базовую линию — прошлые числа перестали бы значить."""
    from typed_judge.recipes.draft_lint_v3 import QUESTIONS as V3_QUESTIONS

    assert "unsourced" not in V3_QUESTIONS
    assert "без источника и без способа его проверить" in QUESTIONS["unsourced_v0"].instructions
