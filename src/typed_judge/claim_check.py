"""Claim-vs-evidence: критические утверждения черновика против источника (бид typed-judge-kit-q36).

DR-63 ранг 5: двухшаговая схема «извлечь утверждения -> проверить каждое против источника» ловит
необоснованные тезисы лучше одного целостного вопроса. Шаг 1 здесь детерминированный, а не модельный:
движок (TypeSafe/Jev) не возвращает текст вообще (draft_lint_v3.COT_FIRST_LIMITATION), извлекать
утверждения ему нечем. Отбор по поверхностным признакам критического утверждения — число, дата,
имя собственное не в начале предложения, прямая цитата — то, что DR-63 называет критическим классом.

Шаг 2 — Noul на утверждение, в ДВУХ формулировках сразу: дефектной («противоречит или отсутствует»)
и положительной («подтверждается»). Бид 08p: единый вопрос про источник модель прочитала как вопрос
про наличие утверждения (separation -1.00) — какая из формулировок работает, решает замер, а не вкус.
HOLISTIC_QID — контроль: тот же вопрос целиком по тексту, без разбиения. Если он не хуже, разбиение
не окупилось.

Границы (DR-63): многошаговые выводы и числовые связи («2200 за три месяца» -> «около 25 в день»)
так не ловятся — проверяется соответствие утверждения источнику, а не арифметика между утверждениями.
"""
from __future__ import annotations

import re

from .questions import Answer, Noul, Question

HOLISTIC_QID = "any_unsupported"
DEFAULT_LIMIT = 8

_SENTENCE = re.compile(r"[^.!?]+[.!?]+|\S[^.!?]*$")
# Признаки критического утверждения: цифра, прямая цитата, заглавное слово НЕ в начале предложения.
_DIGIT = re.compile(r"\d")
_QUOTE = re.compile(r"[«\"']")
_INNER_CAPITAL = re.compile(r"(?<=[^.!?])\s[А-ЯЁA-Z][а-яёa-z]")


def extract_claims(text: str, limit: int = DEFAULT_LIMIT) -> list[str]:
    out = []
    for m in _SENTENCE.finditer(text):
        s = m.group().strip()
        if not s:
            continue
        if _DIGIT.search(s) or _QUOTE.search(s) or _INNER_CAPITAL.search(s):
            out.append(s)
        if len(out) == limit:
            break
    return out


def questions_for(claims: list[str]) -> dict[str, Question]:
    qs: dict[str, Question] = {}
    for i, c in enumerate(claims):
        qs[f"claim_{i}_contradicts"] = Noul(
            f"Утверждение черновика «{c}» противоречит источнику или отсутствует в нём. "
            "Пример нарушения: в черновике «обработал 2200 писем», в источнике — 1200, "
            "или про это число в источнике нет ни слова."
        )
        qs[f"claim_{i}_supported"] = Noul(
            f"Утверждение черновика «{c}» прямо подтверждается источником: в источнике есть то же "
            "число, та же дата, то же имя или та же цитата."
        )
    qs[HOLISTIC_QID] = Noul(
        "Хотя бы одно конкретное фактическое утверждение черновика (число, дата, имя, цитата, причинная "
        "связь) противоречит источнику или не подтверждается им. Пример нарушения: в черновике «ошибся "
        "3 раза», в источнике — «ошибся 30 раз»."
    )
    return qs


def state_for(draft: str, source: str) -> str:
    return f"ИСТОЧНИК (чему верить):\n{source}\n\nЧЕРНОВИК (что проверяем):\n{draft}"


def unsupported(answers: dict[str, Answer], n_claims: int, *, threshold: float,
                phrasing: str = "contradicts") -> list[int]:
    """Индексы утверждений, не подтверждённых источником. Ответ с ошибкой — не пропуск и не срабатывание."""
    out = []
    for i in range(n_claims):
        a = answers.get(f"claim_{i}_{phrasing}")
        if a is None or a.error or a.probability is None:
            continue
        fired = a.probability >= threshold if phrasing == "contradicts" else a.probability < threshold
        if fired:
            out.append(i)
    return out


def veto(verdict: str, unsupported: list[int], *, auto_verdict: str = "ready",
         lowered_to: str = "light_edit") -> str:
    """Непокрытое утверждение снимает только auto: ov0 — вето понижает ready, а не ставит heavy_edit."""
    return lowered_to if unsupported and verdict == auto_verdict else verdict
