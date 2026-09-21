"""Claim-vs-evidence: критические утверждения черновика против источника (бид typed-judge-kit-q36).

DR-63 ранг 5: двухшаговая схема «извлечь утверждения -> проверить каждое против источника» ловит
необоснованные тезисы лучше одного целостного вопроса. Шаг 1 здесь детерминированный, а не модельный:
движок (TypeSafe/Jev) не возвращает текст вообще (draft_lint_v3.COT_FIRST_LIMITATION), извлекать
утверждения ему нечем. Отбор по поверхностным признакам критического утверждения — число, дата,
имя собственное не в начале предложения, прямая цитата — то, что DR-63 называет критическим классом.

Шаг 2 — Noul на утверждение, в ДВУХ формулировках сразу: дефектной («противоречит или отсутствует»)
и положительной («подтверждается»). Бид 08p: единый вопрос про источник модель прочитала как вопрос
про наличие утверждения (separation -1.00) — какая из формулировок работает, решает замер, а не вкус.
HOLISTIC_QID — контроль: тот же вопрос целиком по тексту, без разбиения.

РЕЗУЛЬТАТ (бид 6qa, по двум независимым замерам): разбиение не окупилось, контроль выиграл.
Синтетика q36 (25 critical + 5 base): целостный вопрос 25/25 при 0/5 ложных, по утверждениям
19/25 дефектной формулировкой и 18/25 положительной (провал на negation_flip — инверсия «не» не
трогает ни числа, ни имена, ни даты, а вопрос на утверждение привязан к их сверке). Реальные пары
черновик/Source material, sqd (10 пар, подсаженных ошибок нет, меряются ложные срабатывания):
целостный 1/10 = 0.100, по утверждениям 20/70 = 0.286.

Поэтому в вердикт входит ТОЛЬКО целостный вопрос: QUESTIONS, fired(), veto(). Путь по утверждениям
(extract_claims/questions_for/unsupported) остаётся исследовательским — им воспроизводятся оба
замера из scripts/claim_check_run.py и scripts/claim_check_drafts.py, и он не влияет ни на один
вердикт. Следствие: DEFAULT_LIMIT=8 (на который упёрлись 8 из 10 реальных черновиков) на вердикты
тоже больше не влияет и не калибруется.

Границы (DR-63): многошаговые выводы и числовые связи («2200 за три месяца» -> «около 25 в день»)
так не ловятся — проверяется соответствие утверждения источнику, а не арифметика между утверждениями.
Вето понижает только ready и не отличает «противоречит источнику» от «источник об этом молчит»:
на реальной паре источник короче черновика и покрывает не всё, отсюда 0.100 ложных.
"""
from __future__ import annotations

import re

from .questions import Answer, Noul, Question

HOLISTIC_QID = "any_unsupported"
HOLISTIC = Noul(
    "Хотя бы одно конкретное фактическое утверждение черновика (число, дата, имя, цитата, причинная "
    "связь) противоречит источнику или не подтверждается им. Пример нарушения: в черновике «ошибся "
    "3 раза», в источнике — «ошибся 30 раз»."
)
# Вопрос вердиктного пути — один. Второй вызов движка на утверждение здесь не окупается (см. докстринг).
QUESTIONS: dict[str, Question] = {HOLISTIC_QID: HOLISTIC}
# Порог обоих замеров (q36, sqd); на 30 точках не калибруется — README Rule.
THRESHOLD = 0.5
# Только для исследовательского пути по утверждениям, в вердикт не входит.
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
    """Исследовательский набор: путь по утверждениям + контроль. Вердикт считается по QUESTIONS."""
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
    qs[HOLISTIC_QID] = HOLISTIC
    return qs


def state_for(draft: str, source: str) -> str:
    return f"ИСТОЧНИК (чему верить):\n{source}\n\nЧЕРНОВИК (что проверяем):\n{draft}"


def unsupported(answers: dict[str, Answer], n_claims: int, *, threshold: float,
                phrasing: str = "contradicts") -> list[int]:
    """Индексы утверждений, не подтверждённых источником (исследовательский путь, вне вердикта).

    Ответ с ошибкой — не пропуск и не срабатывание.
    """
    out = []
    for i in range(n_claims):
        a = answers.get(f"claim_{i}_{phrasing}")
        if a is None or a.error or a.probability is None:
            continue
        fired = a.probability >= threshold if phrasing == "contradicts" else a.probability < threshold
        if fired:
            out.append(i)
    return out


def fired(answers: dict[str, Answer], *, threshold: float = THRESHOLD) -> bool:
    """Сработал ли целостный вопрос. Ошибка движка и пустой ответ — не срабатывание, вердикт не трогаем."""
    a = answers.get(HOLISTIC_QID)
    return bool(a and not a.error and a.probability is not None and a.probability >= threshold)


def veto(verdict: str, fired: bool, *, auto_verdict: str = "ready",
         lowered_to: str = "light_edit") -> str:
    """Непокрытое утверждение снимает только auto: ov0 — вето понижает ready, а не ставит heavy_edit."""
    return lowered_to if fired and verdict == auto_verdict else verdict
