from typed_judge.questions import Answer, Choice, Noul, Score, question_kind


def test_kinds():
    assert question_kind(Choice("q", {"a": None, "b": "объяснение"})) == "choice"
    assert question_kind(Score("q", ("нет", "слабый", "сильный"))) == "score"
    assert question_kind(Noul("q")) == "noul"


def test_score_scale_from_anchors():
    s = Score("q", ("нет", "слабый", "рабочий", "сильный"))
    assert s.max == 3


def test_answer_numeric():
    assert Answer(probability=0.7).numeric() == 0.7
    assert Answer(value=2.0, confidence=0.9).numeric() == 2.0
    assert Answer(value="ready", confidence=0.9).numeric() is None
    assert Answer(value=2.0, error="boom").numeric() is None


def test_answer_roundtrip():
    a = Answer(value="ready", confidence=0.5, raw={"x": 1})
    assert Answer.from_dict(a.to_dict()) == a
