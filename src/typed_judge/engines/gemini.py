"""Адаптер Gemini через structured output. Порт Client из lint_draft.py: пейсинг free-tier, 400 → без thinking."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from . import Result, load_key
from ..questions import Answer, Choice, Noul, Question, Score

PREAMBLE = ("Ниже — state. Ответь на заданные вопросы как отдельные независимые мгновенные суждения о нём. "
            "Верни только значения, без объяснений.")


def build_schema(questions: dict[str, Question]) -> dict:
    props = {}
    for qid, q in questions.items():
        if isinstance(q, Choice):
            props[qid] = {"type": "object",
                          "properties": {"value": {"type": "string", "enum": list(q.options)}, "confidence": {"type": "number"}},
                          "required": ["value", "confidence"]}
        elif isinstance(q, Score):
            props[qid] = {"type": "object", "properties": {"score": {"type": "number"}, "confidence": {"type": "number"}},
                          "required": ["score", "confidence"]}
        else:
            props[qid] = {"type": "object", "properties": {"p": {"type": "number"}}, "required": ["p"]}
    return {"type": "object", "properties": props, "required": list(questions)}


def build_prompt(state: str, questions: dict[str, Question]) -> str:
    lines = []
    for i, (qid, q) in enumerate(questions.items(), 1):
        line = f"{i}. {qid} — {q.instructions}"
        if isinstance(q, Score):
            line += " " + ", ".join(f"{n} = {a}" for n, a in enumerate(q.anchors))
        elif isinstance(q, Choice):
            line += " " + " | ".join(q.options)
        else:
            line += " (вероятность, что утверждение верно)"
        lines.append(line)
    return f"{PREAMBLE}\n\nstate:\n---\n{state}\n---\n\nВопросы:\n" + "\n".join(lines)


def parse_answers(obj: dict, questions: dict[str, Question]) -> dict[str, Answer]:
    out = {}
    for qid, q in questions.items():
        a = obj.get(qid)
        if not isinstance(a, dict):
            out[qid] = Answer(error=f"нет ответа на {qid}", raw={"got": a})
            continue
        try:
            if isinstance(q, Choice):
                out[qid] = Answer(value=str(a["value"]), confidence=a.get("confidence"), raw=a)
            elif isinstance(q, Score):
                out[qid] = Answer(value=float(a["score"]), confidence=a.get("confidence"), raw=a)
            else:
                out[qid] = Answer(probability=float(a["p"]), raw=a)
        except (KeyError, TypeError, ValueError) as e:
            out[qid] = Answer(error=f"не разобран ответ {qid}: {type(e).__name__}: {e}", raw=a)
    return out


class GeminiEngine:
    def __init__(self, key: str | None = None, model: str = "gemini-3.5-flash-lite", min_interval_s: float = 4.5,
                 attempts: int = 5, sleep=time.sleep, urlopen=urllib.request.urlopen, clock=time.monotonic):
        self.key = key or load_key(("GEMINI_API_KEY", "GOOGLE_API_KEY"))
        self.model, self.min_interval_s, self.attempts = model, min_interval_s, attempts
        self.sleep, self.urlopen, self.clock = sleep, urlopen, clock
        self.name = f"gemini:{model}"
        self.thinking = True
        self.last = None

    def ask(self, state: str, questions: dict[str, Question]) -> Result:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        body = {"contents": [{"parts": [{"text": build_prompt(state, questions)}]}],
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                                     "responseSchema": build_schema(questions)}}
        last = "call failed"
        for i in range(self.attempts):
            if self.thinking:
                body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "MINIMAL"}
            else:
                body["generationConfig"].pop("thinkingConfig", None)
            if self.last is not None:
                wait = self.min_interval_s - (self.clock() - self.last)
                if wait > 0:
                    self.sleep(wait)
            req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json", "x-goog-api-key": self.key})
            t0 = time.monotonic()
            try:
                with self.urlopen(req, timeout=120) as r:
                    data = json.load(r)
                self.last = self.clock()
                obj = json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
                u = data.get("usageMetadata", {})
                return Result(parse_answers(obj, questions), u.get("promptTokenCount", 0),
                              u.get("candidatesTokenCount", 0), time.monotonic() - t0)
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}: {e.read().decode()[:300]}"
                if e.code == 400 and self.thinking:
                    self.thinking = False  # повтор без thinking — сразу, пейсинг не трогаем
                    continue
                self.last = self.clock()
                if e.code == 429:
                    self.sleep(25 + 5 * i)
                    continue
                break
            except (KeyError, ValueError, json.JSONDecodeError) as e:
                return Result(error=f"ответ Gemini не разобран: {type(e).__name__}: {e}")
        return Result(error=last)
