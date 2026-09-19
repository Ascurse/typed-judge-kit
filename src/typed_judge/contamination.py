"""bd typed-judge-kit-3jk: контаминация батча вопросов (DR-63, раздел «открытые вопросы»).

run_isolated — тот же вопросник, что и batch.run, но каждый вопрос отдельным
вызовом движка (режим В из замера). binarize/hamming — метрика расхождения
между режимами А/Б/В по бинаризованным ответам.
"""
from __future__ import annotations

import pathlib
import time
from dataclasses import replace

from .batch import Row, append_cache, cache_key, read_rows
from .engines import Engine
from .questions import Answer, Choice, Question, Score


def binarize(a: Answer, q: Question) -> str | int | None:
    """Дискретная категория ответа для сравнения между режимами.

    Choice — сама выбранная опция (совпадение опции); Score — порог по середине
    шкалы (anchors); Noul (вероятность 0..1) — тот же принцип, порог 0.5.
    Ошибка ответа не биноризуется — None считается расхождением в hamming().
    """
    if a.error:
        return None
    if isinstance(q, Choice):
        return a.value
    if isinstance(q, Score):
        return int(a.value >= q.max / 2)
    return int(a.probability >= 0.5)  # Noul


def hamming(a: dict[str, Answer], b: dict[str, Answer], questions: dict[str, Question]) -> int:
    """Число вопросов, где бинаризованные ответы разошлись (ошибка на любой стороне — тоже расхождение)."""
    dist = 0
    for qid, q in questions.items():
        ba, bb = binarize(a[qid], q), binarize(b[qid], q)
        if ba is None or bb is None or ba != bb:
            dist += 1
    return dist


def run_isolated(engine: Engine, items: dict[str, str], questions: dict[str, Question],
                  cache_path: pathlib.Path | None) -> list[Row]:
    """Как batch.run, но каждый вопрос — отдельный вызов engine.ask (режим В: без соседних вопросов в контексте)."""
    cached = {r.key: r for r in read_rows(cache_path) if not r.error} if cache_path else {}
    out: list[Row] = []
    new: list[Row] = []
    for item_id, state in items.items():
        key = cache_key(engine.name, state, questions)
        if key in cached:
            out.append(replace(cached[key], item_id=item_id))
            continue
        answers: dict[str, Answer] = {}
        in_tok = out_tok = 0
        latency = 0.0
        for qid, q in questions.items():
            t0 = time.monotonic()
            try:
                res = engine.ask(state, {qid: q})
                answers[qid] = res.answers.get(qid, Answer(error=f"нет ответа на {qid}"))
                in_tok += res.input_tokens
                out_tok += res.output_tokens
                latency += res.latency_s or time.monotonic() - t0
            except Exception as e:  # noqa: BLE001 — сбой одного вопроса не должен ронять всю строку
                answers[qid] = Answer(error=str(e))
                latency += time.monotonic() - t0
        row = Row(item_id, key, engine.name, answers, in_tok, out_tok, latency, None)
        out.append(row)
        if not any(a.error for a in answers.values()):  # как в batch.run: сбой не кэшируется, иначе станет постоянным
            new.append(row)
    append_cache(cache_path, new)
    return out
