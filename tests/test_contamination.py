"""bd typed-judge-kit-3jk: изолированные вызовы (режим В) и Hamming distance для замера контаминации."""
import json

from typed_judge.batch import Row, read_rows
from typed_judge.contamination import binarize, hamming, run_isolated
from typed_judge.engines.fake import FakeEngine
from typed_judge.questions import Answer, Choice, Noul, Score

Q = {
    "hook": Score("хук?", ("нет", "слабый", "рабочий", "сильный")),  # max=3, середина 1.5
    "evidence": Noul("есть факты"),
    "readiness": Choice("куда?", {"ready": None, "light_edit": None, "heavy_edit": None}),
}


# --- binarize ---

def test_binarize_score_threshold_at_midpoint():
    q = Q["hook"]
    assert binarize(Answer(value=1.4), q) == 0
    assert binarize(Answer(value=1.5), q) == 1
    assert binarize(Answer(value=2.0), q) == 1


def test_binarize_noul_threshold_at_half():
    q = Q["evidence"]
    assert binarize(Answer(probability=0.49), q) == 0
    assert binarize(Answer(probability=0.5), q) == 1


def test_binarize_choice_is_raw_option():
    q = Q["readiness"]
    assert binarize(Answer(value="ready"), q) == "ready"
    assert binarize(Answer(value="light_edit"), q) == "light_edit"


def test_binarize_error_answer_is_none():
    assert binarize(Answer(error="нет ответа"), Q["evidence"]) is None


# --- hamming ---

def test_hamming_counts_mismatches_only():
    a = {"hook": Answer(value=2.0), "evidence": Answer(probability=0.9), "readiness": Answer(value="ready")}
    b = {"hook": Answer(value=2.5), "evidence": Answer(probability=0.1), "readiness": Answer(value="light_edit")}
    # hook: 1==1 совпал; evidence: 1 vs 0 разошёлся; readiness: разошёлся
    assert hamming(a, b, Q) == 2


def test_hamming_identical_answers_is_zero():
    a = {"hook": Answer(value=2.0), "evidence": Answer(probability=0.9), "readiness": Answer(value="ready")}
    assert hamming(a, a, Q) == 0


def test_hamming_error_on_either_side_counts_as_mismatch():
    a = {"hook": Answer(value=2.0), "evidence": Answer(error="боль"), "readiness": Answer(value="ready")}
    b = {"hook": Answer(value=2.0), "evidence": Answer(probability=0.9), "readiness": Answer(value="ready")}
    assert hamming(a, b, Q) == 1


# --- run_isolated ---

def test_run_isolated_calls_engine_once_per_question(tmp_path):
    e = FakeEngine()
    rows = run_isolated(e, {"a": "текст а"}, Q, tmp_path / "r.jsonl")
    assert e.calls == len(Q)
    assert len(rows) == 1 and set(rows[0].answers) == set(Q)


def test_run_isolated_each_call_gets_single_question(tmp_path):
    seen = []

    class Recording:
        name = "rec"

        def ask(self, state, questions):
            seen.append(set(questions))
            return FakeEngine().ask(state, questions)

    run_isolated(Recording(), {"a": "текст"}, Q, tmp_path / "r.jsonl")
    assert seen == [{"hook"}, {"evidence"}, {"readiness"}]


def test_run_isolated_uses_cache_on_second_run(tmp_path):
    e = FakeEngine()
    path = tmp_path / "r.jsonl"
    run_isolated(e, {"a": "текст"}, Q, path)
    assert e.calls == len(Q)
    run_isolated(e, {"a": "текст"}, Q, path)
    assert e.calls == len(Q)  # второй прогон не должен звать движок снова
    assert len(read_rows(path)) == 1


def test_run_isolated_one_bad_question_becomes_error_answer_not_row_failure(tmp_path):
    class HalfBroken:
        name = "half"

        def ask(self, state, questions):
            (qid,) = questions
            if qid == "evidence":
                raise RuntimeError("HTTP 500")
            return FakeEngine().ask(state, questions)

    rows = run_isolated(HalfBroken(), {"a": "текст"}, Q, tmp_path / "r.jsonl")
    row = rows[0]
    assert row.error is None  # строка не падает целиком
    assert row.answers["evidence"].error == "HTTP 500"
    assert row.answers["hook"].error is None


def test_run_isolated_sums_tokens_across_calls(tmp_path):
    class Counting:
        name = "counting"

        def ask(self, state, questions):
            r = FakeEngine().ask(state, questions)
            r.input_tokens, r.output_tokens = 100, 10
            return r

    rows = run_isolated(Counting(), {"a": "текст"}, Q, tmp_path / "r.jsonl")
    assert rows[0].input_tokens == 100 * len(Q) and rows[0].output_tokens == 10 * len(Q)
