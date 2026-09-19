from typed_judge.validate import flip_rate, loocv_agreement, permutation_test
from typed_judge.verdict import Verdict

LABELS = {"a": "ready", "b": "light_edit", "c": "heavy_edit", "d": "ready", "e": "light_edit"}
PERFECT = [Verdict(i, 1.0, lab) for i, lab in LABELS.items()]
CHANCE = [Verdict(i, 1.0, "ready") for i in LABELS]  # всегда одно и то же — 2/5 совпадений


def const_factory(verdict: str):
    """combine_fn_factory, игнорирующий обучающую часть (фиксированная формула, Дауэс)."""
    def factory(train_ids):
        return lambda answers: (1.0, verdict)
    return factory


def test_loocv_ignores_training_fold_when_formula_is_fixed():
    # answers не используются самой формулой (она константна) — проверяем, что LOO
    # действительно исключает held-out id из train_ids, а не просто считает по всем сразу.
    seen_train_ids = []

    def factory(train_ids):
        seen_train_ids.append(sorted(train_ids))
        return lambda answers: (1.0, "ready")

    answers = {i: {} for i in LABELS}
    k, n = loocv_agreement(list(LABELS), factory, answers, LABELS, positive="ready")
    assert n == 5
    assert k == sum(lab == "ready" for lab in LABELS.values())
    for held_out, train_ids in zip(LABELS, seen_train_ids):
        assert held_out not in train_ids
        assert len(train_ids) == 4


def test_loocv_matches_plain_agreement_for_fixed_formula():
    # формула без параметров (const_factory игнорирует train_ids) — LOO вырождается
    # в прямую оценку k/n, где k — число меток "ready" (см. calibrate.agreement на CHANCE).
    from typed_judge.calibrate import agreement
    answers = {i: {} for i in LABELS}
    k, n = loocv_agreement(list(LABELS), const_factory("ready"), answers, LABELS, positive="ready")
    plain_k, plain_n = agreement(CHANCE, LABELS)
    assert (k, n) == (plain_k, plain_n)


def test_permutation_test_observed_count_is_exact_agreement():
    observed, p = permutation_test(PERFECT, LABELS, n_perm=500, seed=0)
    assert observed == 5
    assert 0.0 <= p <= 1.0


def test_permutation_test_perfect_agreement_gives_low_p_value():
    observed, p = permutation_test(PERFECT, LABELS, n_perm=2000, seed=0)
    assert p < 0.1


def test_permutation_test_is_deterministic_for_a_fixed_seed():
    r1 = permutation_test(PERFECT, LABELS, n_perm=300, seed=42)
    r2 = permutation_test(PERFECT, LABELS, n_perm=300, seed=42)
    assert r1 == r2


def test_permutation_test_chance_level_gives_high_p_value():
    observed, p = permutation_test(CHANCE, LABELS, n_perm=2000, seed=0)
    assert observed == 2  # "ready" встречается дважды в LABELS
    assert p > 0.3


def test_flip_rate_zero_when_all_repeats_agree():
    reps = [{"a": Verdict("a", 1.0, "ready")}, {"a": Verdict("a", 1.0, "ready")}]
    assert flip_rate(reps) == 0.0


def test_flip_rate_counts_items_with_any_disagreement_across_repeats():
    reps = [
        {"a": Verdict("a", 1.0, "ready"), "b": Verdict("b", 1.0, "light_edit")},
        {"a": Verdict("a", 1.0, "ready"), "b": Verdict("b", 1.0, "heavy_edit")},
        {"a": Verdict("a", 1.0, "ready"), "b": Verdict("b", 1.0, "light_edit")},
    ]
    assert flip_rate(reps) == 0.5  # b разошёлся хотя бы раз, a — нет


def test_flip_rate_empty_reps_is_zero():
    assert flip_rate([]) == 0.0
