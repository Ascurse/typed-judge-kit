"""Рецепт: pre-flight линтер черновиков (10 вопросов + формула из decision-graph-lint, замер 2026-09-17)."""
from __future__ import annotations

from ..questions import Answer, Choice, Noul, Question, Score

LABEL_POSITIVE = "ready"
DEFECTS = {k: None for k in ("hook", "evidence", "symmetry", "hedging", "conclusion", "tone", "focus", "none")}
READINESS = {"ready": "публиковать", "light_edit": "лёгкая правка", "heavy_edit": "существенная переработка"}

QUESTIONS: dict[str, Question] = {
    "hook": Score("hook — насколько сильный хук (первая строка/первые слова)?",
                  ("хука нет", "слабый", "рабочий", "сильный (цепляет конкретикой, а не общими словами)")),
    "evidence": Noul("Текст опирается на конкретные факты, числа, детали или ссылки, а не на общие утверждения."),
    "symmetry": Noul("В тексте есть искусственная симметрия «с одной стороны / с другой стороны» без собственного вывода."),
    "hedging": Noul("Есть обтекаемость, вода или канцелярит («важно отметить», «играет ключевую роль», «в современном мире»)."),
    "generic_conclusion": Noul("Финальный вывод общий и подошёл бы почти любому тексту."),
    "tone": Noul("Тон сухой и конкретный, без корпоративной вежливости и мотивационных формул."),
    "one_idea": Noul("Текст держится одной главной мысли и не расползается на несколько тем."),
    "top_defect": Choice("Какой дефект чинить первым?", DEFECTS),
    "readiness": Choice("readiness — куда отправить черновик? Это твоя целостная оценка, не считай её из других ответов.", READINESS),
    "better_as_thread": Noul("Материал лучше зайдёт как тред (серия коротких сообщений), а не как один длинный пост."),
}

QUESTIONS_EN: dict[str, Question] = {
    "hook": Score("hook — how strong is the hook (first line / first words)?",
                  ("no hook", "weak", "working", "strong (specific, not generic)")),
    "evidence": Noul("The text relies on concrete facts, numbers, details or links rather than general claims."),
    "symmetry": Noul("The text has artificial 'on one hand / on the other hand' symmetry without its own conclusion."),
    "hedging": Noul("There is hedging, filler or bureaucratic phrasing."),
    "generic_conclusion": Noul("The final conclusion is generic and would fit almost any text."),
    "tone": Noul("The tone is dry and specific, without corporate politeness or motivational formulas."),
    "one_idea": Noul("The text sticks to one main idea and does not sprawl across topics."),
    "top_defect": Choice("Which defect should be fixed first?", DEFECTS),
    "readiness": Choice("readiness — where does this draft go? Your holistic call, not derived from other answers.",
                        {"ready": "publish", "light_edit": "light edit", "heavy_edit": "major rework"}),
    "better_as_thread": Noul("The material would work better as a thread than as one long post."),
}

VARIANTS: dict[str, dict[str, Question]] = {
    "factor": QUESTIONS,
    "holistic": {"readiness": QUESTIONS["readiness"]},
    "factor_en": QUESTIONS_EN,
}


def combine(a: dict[str, Answer]) -> tuple[float, str]:
    """1:1 с lint_draft.combine — веса и пороги менять здесь, не в промпте."""
    hook_raw = a["hook"].value
    hook = hook_raw / 3
    ev, sym, hd = a["evidence"].probability, a["symmetry"].probability, a["hedging"].probability
    gen, tone, idea = a["generic_conclusion"].probability, a["tone"].probability, a["one_idea"].probability
    strength = 0.30 * hook + 0.25 * ev + 0.20 * tone + 0.15 * idea + 0.10 * (1 - gen)
    composite = strength - 0.12 * sym - 0.12 * hd
    if composite >= 0.72 and hook_raw >= 2 and ev >= 0.6:
        verdict = "ready"
    elif composite < 0.5:
        verdict = "heavy_edit"
    else:
        verdict = "light_edit"
    return round(composite, 3), verdict


def combine_holistic(a: dict[str, Answer]) -> tuple[float, str]:
    r = a["readiness"]
    return float(r.confidence or 0.0), str(r.value)


COMBINES = {"factor": combine, "holistic": combine_holistic, "factor_en": combine}


def answers_from_gemini_row(row: dict) -> dict[str, Answer]:
    """Строка results.json замера 2026-09-17 → нейтральные Answer-ы."""
    out = {"hook": Answer(value=float(row["hook"]), confidence=row.get("confidence")),
           "top_defect": Answer(value=row["top_defect"]),
           "readiness": Answer(value=row["verdict_model"], confidence=row.get("confidence"))}
    for k, p in row["p"].items():
        out[k] = Answer(probability=p)
    return out
