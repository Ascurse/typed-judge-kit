import io
import json
import urllib.error

import pytest

from typed_judge.engines.gemini import GeminiEngine, build_prompt, build_schema, cost_usd
from typed_judge.questions import Choice, Noul, Score

Q = {"hook": Score("хук?", ("нет", "слабый", "рабочий", "сильный")),
     "evidence": Noul("есть факты"),
     "readiness": Choice("куда?", {"ready": "публиковать", "light_edit": None})}


def gemini_payload(obj):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(obj)}]}}],
            "usageMetadata": {"promptTokenCount": 781, "candidatesTokenCount": 226}}


class FakeHTTP:
    def __init__(self, payloads):
        self.payloads, self.requests = list(payloads), []

    def __call__(self, req, timeout=0):
        self.requests.append(json.loads(req.data))
        p = self.payloads.pop(0)
        if isinstance(p, int):
            raise urllib.error.HTTPError("u", p, "err", {}, io.BytesIO(b"x"))
        return _ctx(io.BytesIO(json.dumps(p).encode()))


class _ctx:
    def __init__(self, f): self.f = f
    def __enter__(self): return self.f
    def __exit__(self, *a): return False


def engine(http, slept=None, clock=None):
    return GeminiEngine(key="g-1234", urlopen=http, sleep=(slept.append if slept is not None else lambda s: None),
                        clock=clock or (lambda: 1000.0))


def test_schema_and_prompt():
    s = build_schema(Q)
    assert s["properties"]["readiness"]["properties"]["value"]["enum"] == ["ready", "light_edit"]
    assert s["properties"]["hook"]["required"] == ["score", "confidence"]
    assert s["properties"]["evidence"]["required"] == ["p"]
    p = build_prompt("ТЕКСТ", Q)
    assert "state:\n---\nТЕКСТ\n---" in p and "0 = нет" in p and "ready | light_edit" in p


def test_parse_and_usage():
    http = FakeHTTP([gemini_payload({"hook": {"score": 2, "confidence": 0.93}, "evidence": {"p": 0.4},
                                     "readiness": {"value": "ready", "confidence": 0.93}})])
    r = engine(http).ask("ТЕКСТ", Q)
    assert r.answers["hook"].value == 2.0 and r.answers["evidence"].probability == 0.4
    assert r.answers["readiness"].value == "ready" and r.input_tokens == 781
    body = http.requests[0]
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "MINIMAL"}


def test_400_drops_thinking_and_retries_without_sleep():
    http = FakeHTTP([400, gemini_payload({"hook": {"score": 1, "confidence": 0.5}, "evidence": {"p": 0.1},
                                          "readiness": {"value": "light_edit", "confidence": 0.5}})])
    slept = []
    r = engine(http, slept).ask("ТЕКСТ", Q)
    assert r.error is None and slept == []
    assert "thinkingConfig" not in http.requests[1]["generationConfig"]


def test_no_sleep_after_last_429():
    http = FakeHTTP([429, 429])
    slept = []
    e = GeminiEngine(key="g-1234", attempts=2, urlopen=http, sleep=slept.append, clock=lambda: 1000.0)
    r = e.ask("ТЕКСТ", Q)
    assert r.error is not None and slept == [25, 4.5]  # 4.5 — пейсинг перед 2-й попыткой; паузы 30 после последней 429 нет


def test_pacing_between_calls():
    http = FakeHTTP([gemini_payload({"hook": {"score": 1, "confidence": 0.5}, "evidence": {"p": 0.1},
                                     "readiness": {"value": "ready", "confidence": 0.5}})] * 2)
    slept, t = [], [1000.0]
    e = engine(http, slept, clock=lambda: t[0])
    e.ask("a", Q)
    t[0] += 1.0
    e.ask("b", Q)
    assert len(slept) == 1 and abs(slept[0] - 3.5) < 1e-6


def test_empty_candidates_becomes_error_not_exception():
    http = FakeHTTP([{"candidates": [], "usageMetadata": {}}])
    r = engine(http).ask("ТЕКСТ", Q)
    assert r.error is not None and "не разобран" in r.error


def test_null_choice_value_is_rejected():
    http = FakeHTTP([gemini_payload({"hook": {"score": 1, "confidence": 0.5}, "evidence": {"p": 0.1},
                                     "readiness": {"value": None, "confidence": 0.5}})])
    r = engine(http).ask("ТЕКСТ", Q)
    assert r.answers["readiness"].error is not None and r.answers["readiness"].value is None


@pytest.mark.network
def test_live_three_types():
    r = GeminiEngine().ask("Короткий текст с числом: за 3 месяца R@5 вырос с 13% до 93%.", Q)
    assert r.answers["hook"].value is not None and r.answers["evidence"].probability is not None


def test_cost_by_hand_calculated_price():
    assert cost_usd("gemini-3.5-flash-lite", 781, 226) == pytest.approx(0.0007993)


def test_cost_unknown_model_is_none():
    assert cost_usd("gemini-unknown", 781, 226) is None
