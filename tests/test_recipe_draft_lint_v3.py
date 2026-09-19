from typed_judge.questions import Answer, Choice, Noul
from typed_judge.recipes import draft_lint as dl
from typed_judge.recipes import draft_lint_v2 as v2
from typed_judge.recipes import draft_lint_v3 as v3

DEFECT_QUESTIONS = ("hook_weak", "no_evidence", "symmetry", "hedging", "generic_conclusion",
                    "corporate_tone", "topic_sprawl", "overclaim", "unsourced", "loose_end")

# "чистый" набор ответов без единого дефекта — должен остаться ready (аналог READY_BASE в v2).
CLEAN = {
    "hook_weak": Answer(probability=0.1), "no_evidence": Answer(probability=0.1),
    "symmetry": Answer(probability=0.1), "hedging": Answer(probability=0.1),
    "generic_conclusion": Answer(probability=0.1), "corporate_tone": Answer(probability=0.1),
    "topic_sprawl": Answer(probability=0.1), "overclaim": Answer(probability=0.1),
    "unsourced": Answer(probability=0.1), "loose_end": Answer(probability=0.1),
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
                                 "better_as_thread", "overclaim", "unsourced", "loose_end"}


def test_clean_draft_is_ready():
    assert v3.combine(CLEAN)[1] == "ready"


def test_heavily_weighted_defects_alone_can_push_off_ready():
    # веса формулы унаследованы из draft_lint.combine (0.30/0.25/0.20/0.15/0.10/0.12/0.12) —
    # только достаточно тяжёлые в одиночку перебивают порог 0.72, лёгкие (symmetry/hedging/
    # generic_conclusion/topic_sprawl) сами по себе — нет, это тоже поведение draft_lint,
    # не регресс v3 (см. test_many_defects_together_reach_heavy_edit для их совместного эффекта).
    for qid in ("hook_weak", "no_evidence", "corporate_tone"):
        score, verdict = v3.combine(with_defect(**{qid: 0.95}))
        assert verdict != "ready", qid


def test_overclaim_at_threshold_demotes_ready_to_light_edit():
    assert v3.combine(with_defect(overclaim=v2.OVERCLAIM_THRESHOLD))[1] == "light_edit"
    assert v3.combine(with_defect(overclaim=v2.OVERCLAIM_THRESHOLD - 0.01))[1] == "ready"


def test_unsourced_and_loose_end_do_not_affect_verdict():
    assert v3.combine(with_defect(unsourced=0.99, loose_end=0.99))[1] == "ready"


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
