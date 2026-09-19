"""draft_lint + три вопроса о точности утверждений (бид typed-judge-kit-iil).

Калибровка 2026-09-20: draft_lint пропускал 6/7 light_edit как ready. Правки владельца там
не про стиль, а про фактуру: заявка сильнее данных, факт без источника, недосказанный хвост.
"""
from __future__ import annotations

from ..questions import Answer, Noul, Question
from .draft_lint import LABEL_POSITIVE, QUESTIONS as BASE_QUESTIONS, combine as base_combine

__all__ = ["LABEL_POSITIVE", "FLAGS", "QUESTIONS", "combine"]

FLAGS: dict[str, Question] = {
    "overclaim": Noul("Хотя бы одно утверждение (в заголовке, хуке или выводе) сильнее, "
                      "чем подтверждают приведённые в тексте данные или размер выборки."),
    "unsourced": Noul("В тексте есть конкретное фактическое утверждение (число, срок, имя, цитата) "
                      "без источника и без способа его проверить."),
    "loose_end": Noul("Текст оставляет недосказанность: упомянутый результат, остаток или обещанное продолжение, "
                      "которое читатель ждёт, но не получает."),
}
QUESTIONS: dict[str, Question] = {**BASE_QUESTIONS, **FLAGS}

# Первый прогон с заранее заданным порогом 0.5 по всем трём флагам перегнул: ready→light 5/6.
# 0.76 подобран на тех же 13 метках (решение владельца 2026-09-20) и зафиксирован до новых меток —
# честная проверка только на постах после 2026-09-20 (бид 6rx).
# unsourced и loose_end метки не разделили; спрашиваются, чтобы копить по ним данные, в вердикт не идут.
OVERCLAIM_THRESHOLD = 0.76


def combine(a: dict[str, Answer]) -> tuple[float, str]:
    score, verdict = base_combine(a)
    if verdict == "ready" and a["overclaim"].probability >= OVERCLAIM_THRESHOLD:
        verdict = "light_edit"
    return score, verdict
