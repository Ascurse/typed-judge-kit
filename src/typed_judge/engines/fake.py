"""Детерминированный движок для тестов и офлайн-демо."""
from __future__ import annotations

import hashlib

from . import Result
from ..questions import Answer, Choice, Noul, Question, Score


def state_id(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def _unit(state: str, qid: str) -> float:
    h = hashlib.sha256(f"{state}\x00{qid}".encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


class FakeEngine:
    name = "fake"

    def __init__(self, scripted: dict[str, dict[str, Answer]] | None = None):
        self.scripted = scripted or {}
        self.calls = 0

    def ask(self, state: str, questions: dict[str, Question]) -> Result:
        self.calls += 1
        sid = state_id(state)
        if sid in self.scripted:
            return Result(answers=dict(self.scripted[sid]))
        out: dict[str, Answer] = {}
        for qid, q in questions.items():
            u = _unit(state, qid)
            if isinstance(q, Noul):
                out[qid] = Answer(probability=round(u, 4))
            elif isinstance(q, Score):
                out[qid] = Answer(value=round(u * q.max, 2), confidence=0.9)
            elif isinstance(q, Choice):
                keys = list(q.options)
                out[qid] = Answer(value=keys[int(u * len(keys))], confidence=0.9)
        return Result(answers=out)
