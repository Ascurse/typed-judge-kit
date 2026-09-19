"""draft_lint v3 (бид typed-judge-kit-zin): бинарные вопросы + CoT-first + чистый вход.

DR-63 (ранги 1-2, 7): атомарные бинарные проверки дефектов вместо шкал (CheckEval/BinEval —
у компактных моделей главный прирост согласия даёт именно декомпозиция на yes/no), CoT
до флага, чистая подача state. Замер 3jk (typed-judge-kit-3jk) уже показал, что батчинг всех
вопросов одним вызовом не создаёт авторегрессионной контаминации — батч сохраняется.

Что сделано:
- Score `hook` (0..3) и позитивно сформулированные Noul (`evidence`, `tone`, `one_idea`)
  заменены бинарными дефект-вопросами (`hook_weak`, `no_evidence`, `corporate_tone`,
  `topic_sprawl`) с явным «Пример нарушения» в instructions — CheckEval/BinEval (rank 1).
  `top_defect`/`readiness` остаются Choice: это выбор из категорий, а не шкала одного
  признака, декомпозиция rank-1 к ним не относится.
- Флаги v2 (`overclaim`/`unsourced`/`loose_end`) перенесены как есть по смыслу и порогу
  (OVERCLAIM_THRESHOLD переиспользован из v2, не задан заново — Дауэс: пороги не крутим
  на тех же метках), но тоже получили explicit «Пример нарушения».
- combine() — тот же взвешенный состав, что draft_lint.combine, только на бинарных
  вероятностях-дефектах вместо шкалы/позитивных Noul (см. COT_FIRST_LIMITATION про то,
  почему веса не заменены на единичные — это отдельный бид wnh, не дублируется здесь).

CoT-first (rank 2) — см. COT_FIRST_LIMITATION ниже: TypeSafe/Jev не возвращает текст.
"""
from __future__ import annotations

from ..questions import Answer, Choice, Noul, Question
from .draft_lint import DEFECTS, READINESS
from .draft_lint_v2 import OVERCLAIM_THRESHOLD

LABEL_POSITIVE = "ready"

# TypeSafe System One (Jev) документирован как модель, возвращающая типизированные
# ответы и вероятности "rather than generating text or reasoning explanations"
# (docs.typesafe.ai/concepts/system-one). Ответы Noul/Choice/Score не содержат текстового
# поля вообще: Noul -> {type, noul}, Choice -> {type, choice, probabilities, confidence},
# Score -> {type, score, legend, probabilities, confidence} (docs.typesafe.ai/api.md).
# Вопросы одного батч-вызова к тому же отвечаются параллельно и не видят ответов друг
# друга (docs: "They run in parallel and cannot see one another's answers") — так что
# даже раздельные вопросы в одном вызове не дают последовательности "обоснование -> флаг".
# Буквальный CoT-first (текстовое поле с рассуждением до флага) на этом API не реализуем.
# Ближайшее опорное решение в рамках типизированных примитивов: каждый бинарный вопрос
# формулируется как "критерий -> явный пример нарушения -> правило да только при прямом
# соответствии примеру", а не как расплывчатое ощущение — это не CoT, а структурированный
# критерий (CheckEval-style), и он уже разделяет rank-1/rank-2 в этом рецепте не до конца.
COT_FIRST_LIMITATION = (
    "TypeSafe/Jev API не поддерживает текстовое поле обоснования и не возвращает "
    "рассуждение ни в одном типе ответа (Noul/Choice/Score); вопросы одного вызова "
    "отвечаются параллельно и не видят ответов друг друга. Буквальный CoT-first (rank 2 "
    "DR-63) на этом движке недостижим. Ближайшая опора — явный 'Пример нарушения' в "
    "instructions каждого бинарного вопроса вместо отдельного поля рассуждения."
)


def _defect(instructions: str, example: str) -> Noul:
    return Noul(f"{instructions} Пример нарушения: {example}")


QUESTIONS: dict[str, Question] = {
    "hook_weak": _defect(
        "Хук (первая строка/первые слова) отсутствует или слабый — не цепляет ничем конкретным.",
        "«Несколько мыслей о том, как работают LLM» — нет факта, цифры или неожиданного "
        "утверждения в первой строке.",
    ),
    "no_evidence": _defect(
        "Текст держится на общих утверждениях без конкретных фактов, цифр, деталей или ссылок.",
        "«интерес к теме в последнее время сильно вырос» — без цифры, даты или источника.",
    ),
    "symmetry": _defect(
        "В тексте есть искусственная симметрия «с одной стороны / с другой стороны» без собственного вывода.",
        "«с одной стороны, подход удобен, с другой — есть нюансы» — без того, что выбрал бы сам автор.",
    ),
    "hedging": _defect(
        "Есть обтекаемость, вода или канцелярит.",
        "«важно отметить, что...», «играет ключевую роль», «в современном мире».",
    ),
    "generic_conclusion": _defect(
        "Финальный вывод общий и подошёл бы почти любому тексту.",
        "«в итоге важно продолжать экспериментировать и делать выводы».",
    ),
    "corporate_tone": _defect(
        "Тон вежливый, корпоративный или мотивационный, а не сухой и конкретный.",
        "«спасибо, что дочитали, берегите себя и продолжайте расти».",
    ),
    "topic_sprawl": _defect(
        "Текст расползается на несколько несвязанных тем вместо одной главной мысли.",
        "пост начинается с бага в кэше и заканчивается общими рассуждениями о будущем ИИ.",
    ),
    "top_defect": Choice("Какой дефект чинить первым?", DEFECTS),
    "readiness": Choice(
        "readiness — куда отправить черновик? Это твоя целостная оценка, не считай её из других ответов.",
        READINESS,
    ),
    "better_as_thread": Noul(
        "Материал лучше зайдёт как тред (серия коротких сообщений), а не как один длинный пост."
    ),
    "overclaim": _defect(
        "Хотя бы одно утверждение (в заголовке, хуке или выводе) сильнее, чем подтверждают "
        "приведённые в тексте данные или размер выборки.",
        "вывод «метод решает проблему» на замере из одного примера без контроля.",
    ),
    "unsourced": _defect(
        "В тексте есть конкретное фактическое утверждение (число, срок, имя, цитата) без "
        "источника и без способа его проверить.",
        "«за 3 месяца показатель вырос на 40%» без ссылки на замер.",
    ),
    "loose_end": _defect(
        "Текст оставляет недосказанность: упомянутый результат, остаток или обещанное "
        "продолжение, которое читатель ждёт, но не получает.",
        "«об этом — в следующий раз» без когда-либо вышедшего продолжения.",
    ),
}


def combine(a: dict[str, Answer]) -> tuple[float, str]:
    """1:1 по структуре с draft_lint.combine, но на бинарных дефект-вероятностях
    вместо шкалы hook и позитивных evidence/tone/one_idea (инверсия: 1 - p(дефект)).
    Веса и пороги — те же, что в draft_lint/v2 (единичные веса Дауэса — отдельный бид wnh,
    здесь не трогаем: смена архитектуры агрегации не входит в rank 1-2/7)."""
    hook = 1 - a["hook_weak"].probability
    ev = 1 - a["no_evidence"].probability
    sym, hd = a["symmetry"].probability, a["hedging"].probability
    gen = a["generic_conclusion"].probability
    tone = 1 - a["corporate_tone"].probability
    idea = 1 - a["topic_sprawl"].probability
    strength = 0.30 * hook + 0.25 * ev + 0.20 * tone + 0.15 * idea + 0.10 * (1 - gen)
    composite = strength - 0.12 * sym - 0.12 * hd
    if composite >= 0.72 and hook >= 0.6 and ev >= 0.6:
        verdict = "ready"
    elif composite < 0.5:
        verdict = "heavy_edit"
    else:
        verdict = "light_edit"
    if verdict == "ready" and a["overclaim"].probability >= OVERCLAIM_THRESHOLD:
        verdict = "light_edit"
    return round(composite, 3), verdict
