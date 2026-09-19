from typed_judge.batch import Row
from typed_judge.report import markdown


def _row(engine, tin, tout):
    return Row("a", "k", engine, input_tokens=tin, output_tokens=tout, latency_s=1.0)


def _summary(rows):
    return markdown(rows, []).splitlines()[-1]


def test_cost_gemini_row():
    assert "стоимость: $0.00080" in _summary([_row("gemini:gemini-3.5-flash-lite", 781, 226)])


def test_cost_typesafe_row():
    assert "стоимость: $0.00089" in _summary([_row("typesafe:jev-latest", 21087, 0)])


def test_cost_unknown_engine_is_dash():
    assert "стоимость: -" in _summary([_row("fake", 10, 10)])


def test_cost_dash_if_any_row_unpriced():
    rows = [_row("gemini:gemini-3.5-flash-lite", 781, 226), _row("fake", 10, 10)]
    assert "стоимость: -" in _summary(rows)


def test_cost_sums_unrounded_values():
    rows = [_row("typesafe:jev-latest", 800, 0)] * 1000  # 1000·800·0.042/1e6 = 0.0336; сумма округлённых строк дала бы 0.03
    assert "стоимость: $0.03360" in _summary(rows)


def test_cost_mixed_engines_sum():
    rows = [_row("typesafe:jev-latest", 21087, 0), _row("gemini:gemini-3.5-flash-lite", 781, 226)]
    assert "стоимость: $0.00168" in _summary(rows)  # 0.000885654 + 0.0007993 = 0.001684954


def test_cost_unknown_gemini_model_is_dash():
    assert "стоимость: -" in _summary([_row("gemini:gemini-9", 781, 226)])
