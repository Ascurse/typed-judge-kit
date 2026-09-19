from typed_judge.questions import Answer, Choice, Noul
from typed_judge.recipes import draft_lint as dl
from typed_judge.recipes import draft_lint_v2 as v2
from typed_judge.recipes import draft_lint_v3 as v3

DEFECT_QUESTIONS = ("hook_weak", "no_evidence", "symmetry", "hedging", "generic_conclusion",
                    "corporate_tone", "topic_sprawl", "overclaim", "has_claim", "loose_end")

# "чистый" набор ответов без единого дефекта — должен остаться ready (аналог READY_BASE в v2).
CLEAN = {
    "hook_weak": Answer(probability=0.1), "no_evidence": Answer(probability=0.1),
    "symmetry": Answer(probability=0.1), "hedging": Answer(probability=0.1),
    "generic_conclusion": Answer(probability=0.1), "corporate_tone": Answer(probability=0.1),
    "topic_sprawl": Answer(probability=0.1), "overclaim": Answer(probability=0.1),
    "has_claim": Answer(probability=0.1), "has_source": Answer(probability=0.9),
    "loose_end": Answer(probability=0.1),
    "top_defect": Answer(value="none"), "readiness": Answer(value="ready"),
    "better_as_thread": Answer(probability=0.1),
}


def with_defect(**flags) -> dict[str, Answer]:
    out = dict(CLEAN)
    for k, p in flags.items():
        out[k] = Answer(probability=p)
    return out


def test_questions_are_binary_noul_for_every_defect_check():
    for qid in DEFECT_QUESTIONS:
        q = v3.QUESTIONS[qid]
        assert isinstance(q, Noul), qid


def test_every_defect_question_names_an_explicit_violation_example():
    for qid in DEFECT_QUESTIONS:
        assert "Пример нарушения" in v3.QUESTIONS[qid].instructions, qid


def test_no_score_questions_left_scale_judgments_are_binarized():
    # rank-1 DR-63: шкалы (Score) заменены бинарными Noul; top_defect/readiness остаются
    # категориальными Choice (это выбор из вариантов, а не шкала одного признака).
    from typed_judge.questions import Score
    assert not any(isinstance(q, Score) for q in v3.QUESTIONS.values())
    assert isinstance(v3.QUESTIONS["top_defect"], Choice)
    assert isinstance(v3.QUESTIONS["readiness"], Choice)


def test_ten_questions_plus_three_v2_flags_all_present():
    assert set(v3.QUESTIONS) == {"hook_weak", "no_evidence", "symmetry", "hedging", "generic_conclusion",
                                 "corporate_tone", "topic_sprawl", "top_defect", "readiness",
                                 "better_as_thread", "overclaim", "has_claim", "has_source",
                                 "loose_end"}


def test_clean_draft_is_ready():
    assert v3.combine(CLEAN)[1] == "ready"


def test_heavily_weighted_defects_alone_can_push_off_ready():
    # веса формулы унаследованы из draft_lint.combine (0.30/0.25/0.20/0.15/0.10/0.12/0.12) —
    # только достаточно тяжёлые в одиночку перебивают порог 0.72, лёгкие (symmetry/hedging/
    # generic_conclusion/topic_sprawl) сами по себе — нет, это тоже поведение draft_lint,
    # не регресс v3 (см. test_many_defects_together_reach_heavy_edit для их совместного эффекта).
    for qid in ("hook_weak", "no_evidence", "corporate_tone"):
        _, verdict = v3.combine(with_defect(**{qid: 0.95}))
        assert verdict != "ready", qid


# Поведение overclaim изменено бидом wnh: в v2 overclaim лишь понижал ready до
# light_edit, теперь критический класс — изолированное вето до heavy_edit, а unsourced входил
# в тот же класс (было: не влияет). Порог тот же, OVERCLAIM_THRESHOLD из v2, не перекалиброван.
def test_overclaim_at_threshold_downgrades_ready_to_light_edit():
    # бид ov0: порог 0.76 калибровался в роли «ready -> light_edit» (draft_lint_v2.combine),
    # последствие heavy_edit, которое поставил wnh, не калибровалось ничем
    assert v3.combine(with_defect(overclaim=v2.OVERCLAIM_THRESHOLD))[1] == "light_edit"
    assert v3.combine(with_defect(overclaim=v2.OVERCLAIM_THRESHOLD - 0.01))[1] == "ready"


def test_loose_end_counts_as_style_defect():
    # бид 08p: unsourced выведен из вето, его место в этом тесте занимать нечему
    assert v3.combine(with_defect(loose_end=0.99))[1] == "light_edit"


def test_many_defects_together_reach_heavy_edit():
    bad = with_defect(hook_weak=0.95, no_evidence=0.95, symmetry=0.95, hedging=0.95,
                       generic_conclusion=0.95, corporate_tone=0.95, topic_sprawl=0.95)
    assert v3.combine(bad)[1] == "heavy_edit"


def test_cot_first_limitation_is_documented_not_faked():
    # DR-63 просит обоснование ДО флага отдельным полем; API TypeSafe/Jev (Noul/Choice/Score)
    # текстовых полей не возвращает вовсе — это должно быть явно задокументировано в рецепте,
    # а не подменено выдуманным полем.
    assert "COT" in dir(v3) or hasattr(v3, "COT_FIRST_LIMITATION")
    assert "не поддерживает" in v3.COT_FIRST_LIMITATION or "не возвращает" in v3.COT_FIRST_LIMITATION


def test_label_positive_matches_convention():
    assert v3.LABEL_POSITIVE == dl.LABEL_POSITIVE == "ready"


# --- бид typed-judge-kit-08p: unsourced расщеплён на has_claim/has_source и выведен из вето ---

def _answers(**flags) -> dict[str, Answer]:
    out = dict(CLEAN)
    for k, p in flags.items():
        out[k] = Answer(probability=p)
    return out


def test_unsourced_split_into_two_questions():
    assert "unsourced" not in v3.QUESTIONS
    assert isinstance(v3.QUESTIONS["has_claim"], Noul)
    assert isinstance(v3.QUESTIONS["has_source"], Noul)


def test_unsourced_probability_is_conjunction_claim_and_no_source():
    # замер 08p: отдельный вопрос «есть утверждение без источника» модель читает как
    # «есть утверждение» (separation -1.00). Конъюнкция двух вопросов даёт 0.65.
    assert v3.unsourced_probability(_answers()) == 0.1 * (1 - 0.9)
    assert v3.unsourced_probability(_answers(has_claim=0.9, has_source=0.05)) == 0.9 * 0.95


def test_unsourced_is_not_in_the_veto():
    # 0.35 ложных срабатываний на отрицательном классе — такому вопросу нельзя отдавать вердикт
    assert "unsourced" not in v3.CRITICAL_DEFECTS
    assert v3.CRITICAL_DEFECTS == ("overclaim",)


def test_sourceless_claim_alone_does_not_change_the_verdict():
    # вопрос считается и отдаётся наружу, но в вердикт не входит, пока нет откалиброванного порога
    strong = _answers(has_claim=0.95, has_source=0.02)
    assert v3.unsourced_probability(strong) > 0.9
    assert v3.combine(strong)[1] == "ready"


def test_overclaim_alone_downgrades_but_never_to_heavy_edit():
    # бид ov0: на 14 метках вето давало 9 heavy_edit при нуле heavy_edit среди меток
    assert v3.combine(_answers(overclaim=0.9))[1] == "light_edit"
