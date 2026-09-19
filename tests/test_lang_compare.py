"""bd typed-judge-kit-5h1: |dp| по вопросу между языками (EN vs RU) для одного и того же
черновика. Переиспользует contamination.binarize (Choice) и Answer.numeric() (Noul) —
здесь считается новая величина: степень расхождения по каждому вопросу, а не Hamming
по всем вопросам сразу (тот замер уже есть в contamination.hamming, задача 3jk).
"""
from typed_judge.lang_compare import dp_by_question
from typed_judge.questions import Answer, Choice, Noul

Q = {
    "hedging": Noul("вода?"),
    "readiness": Choice("куда?", {"ready": None, "light_edit": None, "heavy_edit": None}),
}


def test_dp_noul_is_mean_absolute_probability_difference_over_all_rep_pairs():
    en_reps = [
        {"hedging": Answer(probability=0.9), "readiness": Answer(value="ready")},
        {"hedging": Answer(probability=0.7), "readiness": Answer(value="ready")},
    ]
    ru_reps = [
        {"hedging": Answer(probability=0.2), "readiness": Answer(value="ready")},
    ]
    out = dp_by_question(en_reps, ru_reps, Q)
    # |0.9-0.2|=0.7, |0.7-0.2|=0.5 -> среднее 0.6
    assert out["hedging"] == 0.6


def test_dp_choice_is_disagreement_rate_over_all_rep_pairs():
    en_reps = [
        {"hedging": Answer(probability=0.1), "readiness": Answer(value="ready")},
        {"hedging": Answer(probability=0.1), "readiness": Answer(value="light_edit")},
    ]
    ru_reps = [
        {"hedging": Answer(probability=0.1), "readiness": Answer(value="ready")},
    ]
    out = dp_by_question(en_reps, ru_reps, Q)
    # (ready vs ready) совпал, (light_edit vs ready) разошёлся -> 1 из 2 пар
    assert out["readiness"] == 0.5


def test_dp_is_zero_for_identical_answers():
    reps = [{"hedging": Answer(probability=0.4), "readiness": Answer(value="ready")}]
    out = dp_by_question(reps, reps, Q)
    assert out["hedging"] == 0.0
    assert out["readiness"] == 0.0


def test_dp_pair_with_error_on_either_side_is_excluded_not_zero():
    en_reps = [{"hedging": Answer(error="сбой"), "readiness": Answer(value="ready")}]
    ru_reps = [{"hedging": Answer(probability=0.5), "readiness": Answer(value="ready")}]
    out = dp_by_question(en_reps, ru_reps, Q)
    assert out["hedging"] is None  # ни одной валидной пары
    assert out["readiness"] == 0.0


def test_dp_is_none_when_no_valid_pairs_at_all():
    out = dp_by_question([], [], Q)
    assert out["hedging"] is None
    assert out["readiness"] is None
