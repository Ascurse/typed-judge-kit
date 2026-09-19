import io
import json
import urllib.error

import pytest

from typed_judge.engines.typesafe import API, TypeSafeEngine, cost_usd, to_typesafe
from typed_judge.questions import Choice, Noul, Score

Q = {"hook": Score("хук?", ("нет", "слабый", "рабочий", "сильный")),
     "evidence": Noul("есть факты"),
     "readiness": Choice("куда?", {"ready": "публиковать", "light_edit": None})}

RESP = {"answers": {"hook": {"type": "score", "score": 2.49, "confidence": 0.8},
                    "evidence": {"type": "noul", "noul": 0.93},
                    "readiness": {"type": "choice", "choice": "ready", "confidence": 0.52}},
        "usage": {"input_tokens": 2035, "output_tokens": 258}}


class FakeHTTP:
    def __init__(self, payloads):
        self.payloads, self.requests = list(payloads), []

    def __call__(self, req, timeout=0):
        self.requests.append(json.loads(req.data))
        p = self.payloads.pop(0)
        if isinstance(p, int):
            raise urllib.error.HTTPError(API, p, "err", {}, io.BytesIO(b"rate"))
        return io.BytesIO(json.dumps(p).encode())


def test_request_shape_and_parsing():
    http = FakeHTTP([RESP])
    e = TypeSafeEngine(key="k-1234", urlopen=lambda req, timeout: _ctx(http(req, timeout)), sleep=lambda s: None)
    r = e.ask("текст", Q)
    body = http.requests[0]
    assert body["model"] == "jev-latest" and body["state"] == "текст"
    assert body["questions"] == to_typesafe(Q)
    assert body["questions"]["hook"] == {"type": "score", "instructions": "хук?", "criteria": ["нет", "слабый", "рабочий", "сильный"]}
    assert body["questions"]["evidence"] == {"type": "noul", "instructions": "есть факты"}
    assert r.answers["hook"].value == 2.49 and r.answers["evidence"].probability == 0.93
    assert r.answers["readiness"].value == "ready" and r.answers["readiness"].confidence == 0.52
    assert r.input_tokens == 2035 and e.name == "typesafe:jev-latest"


def test_retry_on_429_then_success():
    http = FakeHTTP([429, RESP])
    slept = []
    e = TypeSafeEngine(key="k-1234", urlopen=lambda req, timeout: _ctx(http(req, timeout)), sleep=slept.append)
    r = e.ask("текст", Q)
    assert r.error is None and slept == [5]


def test_missing_answer_is_error_not_default():
    resp = {"answers": {"hook": RESP["answers"]["hook"]}, "usage": {}}
    http = FakeHTTP([resp])
    e = TypeSafeEngine(key="k-1234", urlopen=lambda req, timeout: _ctx(http(req, timeout)), sleep=lambda s: None)
    r = e.ask("текст", Q)
    assert r.answers["evidence"].error and r.answers["evidence"].probability is None


def test_cost():
    assert cost_usd(21087) == 0.00089


class _ctx:
    def __init__(self, f): self.f = f
    def __enter__(self): return self.f
    def __exit__(self, *a): return False


@pytest.mark.network
def test_live_three_types():
    e = TypeSafeEngine()
    r = e.ask("Короткий текст с числом: за 3 месяца R@5 вырос с 13% до 93%.", Q)
    assert r.answers["hook"].value is not None and r.answers["evidence"].probability is not None
    assert r.answers["readiness"].value in ("ready", "light_edit")
