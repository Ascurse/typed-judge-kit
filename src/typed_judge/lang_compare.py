"""bd typed-judge-kit-5h1: расхождение между EN и RU версиями одного черновика,
по каждому вопросу draft_lint_v3 (не суммарный Hamming — тот уже есть в
contamination.hamming, задача 3jk).

Переиспользует contamination.binarize (дискретизация Choice/Score/Noul) и
Answer.numeric() — своей дискретизации/парсинга не заводит.
"""
from __future__ import annotations

import statistics

from .contamination import binarize
from .questions import Answer, Choice, Question


def dp_by_question(en_reps: list[dict[str, Answer]], ru_reps: list[dict[str, Answer]],
                    questions: dict[str, Question]) -> dict[str, float | None]:
    """Для каждого вопроса — среднее расхождение между языками по всем парам (rep EN, rep RU).

    Noul/Score: |numeric(en) - numeric(ru)| (величина, не бинаризованная — dp в терминах
    вероятности/значения). Choice: доля пар с разной выбранной опцией (0..1) — та же 0..1
    шкала "насколько разошлись языки", хоть и другой природы (частота, а не |Δ|).
    Пара с ошибкой ответа на любой стороне исключается из среднего для этого вопроса
    (как в contamination.hamming — ошибка не должна маскироваться под 0)."""
    out: dict[str, float | None] = {}
    for qid, q in questions.items():
        diffs: list[float] = []
        for a in en_reps:
            for b in ru_reps:
                ea, eb = a[qid], b[qid]
                if ea.error or eb.error:
                    continue
                if isinstance(q, Choice):
                    diffs.append(float(binarize(ea, q) != binarize(eb, q)))
                else:
                    pa, pb = ea.numeric(), eb.numeric()
                    if pa is None or pb is None:
                        continue
                    diffs.append(abs(pa - pb))
        out[qid] = None if not diffs else round(statistics.mean(diffs), 4)
    return out
