"""Адаптер TypeSafe System One (Jev). Порт jev_client.py: один POST, ретраи 429/5xx, цена по input-токенам."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from . import Result, load_key
from ..questions import Answer, Choice, Noul, Question, Score

API = "https://api.typesafe.ai/v1/systemone"
PRICE_PER_MTOKEN = 0.042
RETRY_CODES = (429, 500, 502, 503)


def cost_usd(input_tokens: int) -> float:
    return round(input_tokens * PRICE_PER_MTOKEN / 1e6, 5)


def to_typesafe(questions: dict[str, Question]) -> dict:
    out = {}
    for qid, q in questions.items():
        if isinstance(q, Choice):
            out[qid] = {"type": "choice", "instructions": q.instructions, "criteria": q.options}
        elif isinstance(q, Score):
            out[qid] = {"type": "score", "instructions": q.instructions, "criteria": list(q.anchors)}
        else:
            out[qid] = {"type": "noul", "instructions": q.instructions}
    return out


def parse_answers(resp: dict, questions: dict[str, Question]) -> dict[str, Answer]:
    got = resp.get("answers", {})
    out = {}
    for qid, q in questions.items():
        a = got.get(qid)
        if not isinstance(a, dict):
            out[qid] = Answer(error=f"нет ответа на {qid}", raw={"got": a})
            continue
        try:
            if isinstance(q, Choice):
                c = a["choice"]
                if not isinstance(c, str):
                    raise TypeError(f"choice: {c!r}")
                out[qid] = Answer(value=c, confidence=a.get("confidence"), raw=a)
            elif isinstance(q, Score):
                out[qid] = Answer(value=float(a["score"]), confidence=a.get("confidence"), raw=a)
            else:
                out[qid] = Answer(probability=float(a["noul"]), raw=a)
        except (KeyError, TypeError, ValueError) as e:
            out[qid] = Answer(error=f"не разобран ответ {qid}: {type(e).__name__}: {e}", raw=a)
    return out


class TypeSafeEngine:
    def __init__(self, key: str | None = None, model: str = "jev-latest", attempts: int = 4,
                 sleep=time.sleep, urlopen=urllib.request.urlopen):
        self.key = key or load_key(("TYPESAFE_API_KEY",))
        self.model, self.attempts, self.sleep, self.urlopen = model, attempts, sleep, urlopen
        self.name = f"typesafe:{model}"

    def ask(self, state: str, questions: dict[str, Question]) -> Result:
        body = json.dumps({"state": state, "model": self.model, "questions": to_typesafe(questions)}).encode()
        last = "call failed"
        for i in range(self.attempts):
            req = urllib.request.Request(API, data=body, method="POST",
                                         headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
            t0 = time.monotonic()
            try:
                with self.urlopen(req, timeout=120) as r:
                    data = json.load(r)
                u = data.get("usage", {})
                return Result(parse_answers(data, questions), u.get("input_tokens", 0), u.get("output_tokens", 0),
                              time.monotonic() - t0)
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}: {e.read().decode()[:300]}"
                if e.code in RETRY_CODES:
                    self.sleep(5 + 5 * i)
                    continue
                break
            except Exception as e:  # noqa: BLE001 — сеть/таймаут: ретрай с паузой
                last = f"{type(e).__name__}: {e}"
                self.sleep(3 + 3 * i)
        return Result(error=last)
