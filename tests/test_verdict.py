from typed_judge.batch import Row
from typed_judge.questions import Answer
from typed_judge.verdict import HUMAN, apply


def combine(a):
    s = 0.5 * a["ev"].probability + 0.5 * a["hook"].value / 3
    return round(s, 3), "ready" if s >= 0.7 else "light_edit"


def test_apply_calls_user_formula():
    rows = [Row("a", "k1", "fake", {"ev": Answer(probability=0.9), "hook": Answer(value=3.0)}),
            Row("b", "k2", "fake", {"ev": Answer(probability=0.2), "hook": Answer(value=1.0)})]
    v = apply(rows, combine)
    assert [(x.item_id, x.verdict) for x in v] == [("a", "ready"), ("b", "light_edit")]
    assert v[0].score == 0.95


def test_error_row_and_missing_answer_go_to_human():
    rows = [Row("a", "k1", "fake", {}, error="HTTP 500"),
            Row("b", "k2", "fake", {"ev": Answer(probability=0.9)}),          # нет hook
            Row("c", "k3", "fake", {"ev": Answer(error="parse"), "hook": Answer(value=1.0)})]
    v = apply(rows, combine)
    assert [x.verdict for x in v] == [HUMAN, HUMAN, HUMAN]
    assert v[0].error == "HTTP 500" and "hook" in v[1].error and v[2].error


def test_none_value_in_present_answer_goes_to_human():
    from typed_judge.batch import Row
    from typed_judge.questions import Answer
    row = Row("n", "k", "fake", {"hook": Answer(value=None)})
    v = apply([row], lambda a: (a["hook"].value / 3, "ready"))
    assert v[0].verdict == HUMAN and "TypeError" in v[0].error
