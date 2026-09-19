import json

from typed_judge.batch import Row, cache_key, read_rows, run
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


def test_read_rows_skips_broken_lines_with_warning(tmp_path, capsys):
    good = Row("a", "k1", "fake").to_dict()
    path = tmp_path / "r.jsonl"
    path.write_text("\n".join([json.dumps(good), "{bad", json.dumps({"item_id": "x"}), json.dumps(good)]) + "\n",
                    encoding="utf-8")
    rows = read_rows(path)
    err = capsys.readouterr().err
    assert len(rows) == 2
    assert "строка 2" in err and "строка 3" in err and str(path) in err


def test_read_rows_survives_truncated_utf8_tail(tmp_path, capsys):
    good = json.dumps(Row("a", "k1", "fake").to_dict(), ensure_ascii=False)
    path = tmp_path / "r.jsonl"
    path.write_bytes(good.encode() + b"\n" + b'{"item_id": "\xd0')  # обрыв посреди кириллической буквы
    assert len(read_rows(path)) == 1
    assert "строка 2" in capsys.readouterr().err


def test_read_rows_keeps_line_with_unicode_line_separator(tmp_path, capsys):
    path = tmp_path / "r.jsonl"
    path.write_text(json.dumps(Row("x\u2028y", "k1", "fake").to_dict(), ensure_ascii=False) + "\n", encoding="utf-8")
    rows = read_rows(path)
    assert [r.item_id for r in rows] == ["x\u2028y"] and capsys.readouterr().err == ""


def test_run_appends_on_new_line_after_truncated_tail(tmp_path):
    good = json.dumps(Row("a", "k1", "fake").to_dict(), ensure_ascii=False)
    path = tmp_path / "r.jsonl"
    path.write_text(good + "\n" + good[:20], encoding="utf-8")  # хвост оборван без \n
    run(FakeEngine(), {"b": "новый текст"}, Q, path)
    assert [r.item_id for r in read_rows(path)] == ["a", "b"]
