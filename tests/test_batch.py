from typed_judge.batch import cache_key, read_rows, run
from typed_judge.engines.fake import FakeEngine
from typed_judge.questions import Choice, Noul, Score

Q = {f"q{i}": Noul(f"утверждение {i}") for i in range(8)}
Q["hook"] = Score("хук?", ("нет", "слабый", "рабочий", "сильный"))
Q["readiness"] = Choice("куда?", {"ready": None, "light_edit": None, "heavy_edit": None})
ITEMS = {"a": "текст а", "b": "текст б"}


def test_one_call_per_item_for_ten_questions(tmp_path):
    e = FakeEngine()
    rows = run(e, {"a": "текст а"}, Q, tmp_path / "r.jsonl")
    assert e.calls == 1
    assert len(rows) == 1 and len(rows[0].answers) == 10


def test_second_run_makes_zero_calls(tmp_path):
    e = FakeEngine()
    run(e, ITEMS, Q, tmp_path / "r.jsonl")
    assert e.calls == 2
    rows = run(e, ITEMS, Q, tmp_path / "r.jsonl")
    assert e.calls == 2
    assert {r.item_id for r in rows} == {"a", "b"}
    assert len(read_rows(tmp_path / "r.jsonl")) == 2


def test_changed_question_invalidates_cache(tmp_path):
    e = FakeEngine()
    run(e, ITEMS, Q, tmp_path / "r.jsonl")
    q2 = dict(Q, hook=Score("хук (другая формулировка)?", ("нет", "есть")))
    run(e, ITEMS, q2, tmp_path / "r.jsonl")
    assert e.calls == 4
    assert cache_key("fake", "x", Q) != cache_key("fake", "x", q2)


def test_engine_exception_becomes_error_row(tmp_path):
    class Boom:
        name = "boom"
        def ask(self, state, questions):
            raise RuntimeError("HTTP 500")
    rows = run(Boom(), ITEMS, Q, tmp_path / "r.jsonl")
    assert all(r.error == "HTTP 500" and r.answers == {} for r in rows)


def test_no_cache_path_still_runs():
    rows = run(FakeEngine(), ITEMS, Q, None)
    assert len(rows) == 2


class _Flaky:
    name = "flaky"

    def __init__(self):
        self.calls = 0

    def ask(self, state, questions):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("HTTP 500")
        return FakeEngine().ask(state, questions)


def test_error_row_is_not_cached_and_retried(tmp_path):
    e = _Flaky()
    first = run(e, {"a": "текст"}, Q, tmp_path / "r.jsonl")
    assert first[0].error == "HTTP 500"
    second = run(e, {"a": "текст"}, Q, tmp_path / "r.jsonl")
    assert e.calls == 2 and second[0].error is None


def test_cache_hit_keeps_current_item_id(tmp_path):
    e = FakeEngine()
    run(e, {"a": "одинаковый текст"}, Q, tmp_path / "r.jsonl")
    rows = run(e, {"c": "одинаковый текст"}, Q, tmp_path / "r.jsonl")
    assert e.calls == 1 and rows[0].item_id == "c"
