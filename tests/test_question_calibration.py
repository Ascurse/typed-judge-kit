"""Логика расчёта таблицы калибровки бинарных вопросов draft_lint v3 (bead typed-judge-kit-13k).

Без сети — на голых Answer/fixtures-словарях. Разметка истины (см. бид):
- ru_messy/ru_clean пары — прямая истина для стилистических вопросов.
- base/critical пары (общий base_id) — контроль на шум: стиль идентичен, различаются
  только фактом, поэтому расхождение бинаризованного ответа на такой паре — шум.
"""
from typed_judge.question_calibration import binarize, markdown_table, question_table
from typed_judge.questions import Answer


def _fx(*, ru_messy=(), ru_clean=(), base_to_critical=()) -> dict:
    """base_to_critical: список (base_id, [critical_id, ...])."""
    items = [{"id": i, "kind": "ru_messy"} for i in ru_messy]
    items += [{"id": i, "kind": "ru_clean"} for i in ru_clean]
    for base_id, crit_ids in base_to_critical:
        items.append({"id": base_id, "kind": "base"})
        for cid in crit_ids:
            items.append({"id": cid, "kind": "critical", "base_id": base_id})
    return {"items": items}


def test_binarize_matches_combine_threshold_of_point_five():
    assert binarize(0.5) is True
    assert binarize(0.49) is False
    assert binarize(None) is None


def test_question_table_computes_fire_rate_separation_and_means():
    fixtures = _fx(ru_messy=["m1", "m2"], ru_clean=["c1", "c2"])
    answers = {
        "m1": {"hedging": Answer(probability=0.9)},
        "m2": {"hedging": Answer(probability=0.6)},
        "c1": {"hedging": Answer(probability=0.1)},
        "c2": {"hedging": Answer(probability=0.4)},
    }
    rows = question_table(answers, fixtures, ("hedging",))
    r = rows[0]
    assert r.qid == "hedging"
    assert r.n_messy == 2 and r.n_clean == 2
    assert r.messy_fire_rate == 1.0  # оба >= 0.5
    assert r.clean_fire_rate == 0.0  # оба < 0.5
    assert r.separation == 1.0
    assert r.messy_mean_prob == 0.75
    assert r.clean_mean_prob == 0.25


def test_question_table_computes_control_disagreement_over_base_critical_pairs():
    fixtures = _fx(base_to_critical=[("b1", ["b1-x", "b1-y"])])
    answers = {
        "b1": {"hedging": Answer(probability=0.2)},      # не сработал
        "b1-x": {"hedging": Answer(probability=0.8)},    # сработал -> расхождение
        "b1-y": {"hedging": Answer(probability=0.3)},    # не сработал -> согласие
    }
    rows = question_table(answers, fixtures, ("hedging",))
    r = rows[0]
    assert r.n_control_pairs == 2
    assert r.control_disagreement_rate == 0.5


def test_question_table_skips_missing_and_errored_answers():
    fixtures = _fx(ru_messy=["m1", "m2"], base_to_critical=[("b1", ["b1-x"])])
    answers = {
        "m1": {"hedging": Answer(probability=0.9)},
        "m2": {"hedging": Answer(error="нет ответа")},
        "b1": {"hedging": Answer(probability=0.5)},
        # "b1-x" отсутствует вовсе — строка не посчиталась (ошибка движка)
    }
    rows = question_table(answers, fixtures, ("hedging",))
    r = rows[0]
    assert r.n_messy == 1  # ошибка не входит в знаменатель
    assert r.messy_fire_rate == 1.0
    assert r.n_control_pairs == 0
    assert r.control_disagreement_rate is None


def test_question_table_reports_dash_worthy_none_when_group_is_empty():
    fixtures = _fx(ru_clean=["c1"])
    answers = {"c1": {"hedging": Answer(probability=0.1)}}
    rows = question_table(answers, fixtures, ("hedging",))
    r = rows[0]
    assert r.n_messy == 0
    assert r.messy_fire_rate is None
    assert r.messy_mean_prob is None
    assert r.separation is None  # нельзя посчитать разделение без одной из групп


def test_markdown_table_renders_dash_for_missing_values():
    fixtures = _fx()
    rows = question_table({}, fixtures, ("hedging",))
    text = markdown_table(rows)
    assert "hedging" in text
    assert "-" in text
    assert text.startswith("| вопрос |")
