"""Зона сомнения и роутинг в review_required (бид typed-judge-kit-qei). Без сети.

Ширина полосы предрегистрирована в биде до замера (BAND_WIDTH = 0.10 доли шкалы) и здесь
не подбирается. Расстояния нормированы на диапазон своей шкалы: composite 0..1, hook 0..3 —
иначе одна ширина значила бы для них разное.
"""
from typed_judge import routing
from typed_judge.verdict import HUMAN, Verdict


def test_margin_is_distance_normalized_by_the_scale_of_the_axis():
    assert routing.margin(0.74, 0.72) == 0.02
    assert routing.margin(2.07, 2, scale=3) == round(0.07 / 3, 3)


def test_value_far_from_every_boundary_keeps_the_verdict():
    assert routing.route(Verdict("i", 0.90, "ready"), margins={"composite": 0.18}).verdict == "ready"


def test_value_inside_the_band_goes_to_review_and_names_the_axis():
    r = routing.route(Verdict("i", 0.74, "ready"), margins={"composite->0.72": 0.02})
    assert r.verdict == routing.REVIEW_REQUIRED
    assert "composite->0.72" in r.note and r.error is None


def test_band_is_inclusive_at_its_edge_and_open_beyond_it():
    assert routing.route(Verdict("i", 0.77, "ready"),
                         margins={"c": 0.05}).verdict == routing.REVIEW_REQUIRED
    assert routing.route(Verdict("i", 0.78, "ready"), margins={"c": 0.051}).verdict == "ready"


def test_a_gate_on_another_scale_can_trigger_review_on_its_own():
    """Черновик далеко от порога composite, но впритык к гейту evidence >= 0.6."""
    r = routing.route(Verdict("i", 0.88, "light_edit"),
                      margins={"composite->0.72": 0.16, "evidence->0.6": 0.01})
    assert r.verdict == routing.REVIEW_REQUIRED
    assert "evidence" in r.note


def test_missing_score_or_human_verdict_goes_to_review_not_to_a_default():
    assert routing.route(Verdict("i", None, HUMAN, "движок упал"),
                         margins={"c": 0.9}).verdict == routing.REVIEW_REQUIRED


def test_repeat_disagreement_sends_to_review_even_outside_the_band():
    r = routing.route(Verdict("i", 0.95, "ready"), margins={"c": 0.9},
                      repeats=["ready", "light_edit", "ready"])
    assert r.verdict == routing.REVIEW_REQUIRED
    assert "повтор" in r.note


def test_agreeing_repeats_do_not_trigger_review():
    assert routing.route(Verdict("i", 0.95, "ready"), margins={"c": 0.9},
                         repeats=["ready", "ready"]).verdict == "ready"


def test_review_share_counts_only_items_routed_to_review():
    routed = [routing.route(Verdict("a", 0.90, "ready"), margins={"c": 0.18}),
              routing.route(Verdict("b", 0.73, "ready"), margins={"c": 0.01}),
              routing.route(Verdict("c", 0.30, "heavy_edit"), margins={"c": 0.2})]
    assert routing.review_share(routed) == round(1 / 3, 3)
