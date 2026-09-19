import json
import pathlib

from typed_judge.batch import Row
from typed_judge.calibrate import (
    agreement,
    clopper_pearson,
    cohens_kappa,
    confusion,
    fit_thresholds,
    report_text,
    split_holdout,
)
from typed_judge.recipes import draft_lint as dl
from typed_judge.verdict import Verdict, apply

FIX = pathlib.Path(__file__).parent / "fixtures"


def golden_verdicts():
    res = json.loads((FIX / "draft_lint_results.json").read_text(encoding="utf-8"))["results"]
    return apply([Row(s, f"k-{s}", "gemini", dl.answers_from_gemini_row(r)) for s, r in res.items()], dl.combine)


def labels():
    return json.loads((FIX / "draft_lint_labels.json").read_text(encoding="utf-8"))["labels"]


def synth(n: int, k: int, error_at_top: bool = True):
    """n меток с k ошибками (label != "ready"). Ошибки — на верхних по score точках,
    чтобы их нельзя было исключить подъёмом порога (иначе k эффективно снижается до 0)."""
    scores = [float(i) for i in range(1, n + 1)]  # по возрастанию
    labels_ = {}
    for i, s in enumerate(scores):
        is_error = error_at_top and i >= n - k
        labels_[f"i{i}"] = "edit" if is_error else "ready"
    verdicts = [Verdict(f"i{i}", s, "x") for i, s in enumerate(scores)]
    return verdicts, labels_


def test_confusion_counts():
    v, L = golden_verdicts(), labels()
    c = confusion(v, L)
    assert c["ready"]["ready"] == 3 and c["light_edit"]["ready"] == 1


def test_golden_report_below_min_n_certification_impossible():
    # в labels.json 5 меток, но черновик tiny-local-judge в results.json отсутствует → n=4
    v, L = golden_verdicts(), labels()
    assert agreement(v, L) == (3, 4)
    t = fit_thresholds(v, L, positive="ready")
    assert t.n == 4 and t.auto_at is None
    text = report_text(v, L, {}, t)
    assert "3/4" in text and "сертификация невозможна, auto off" in text and "auto выключен" in text


def test_split_holdout_backward_compatible_when_empty():
    L = {"a": "ready", "b": "edit"}
    calib, holdout = split_holdout(L, [])
    assert calib == L and holdout == {}


def test_split_holdout_removes_frozen_ids_from_calibration():
    L = {"a": "ready", "b": "edit", "c": "ready"}
    calib, holdout = split_holdout(L, {"a", "c"})
    assert calib == {"b": "edit"} and holdout == {"a": "ready", "c": "ready"}


def test_crc_n14_k0_auto_off():
    v, L = synth(14, 0)
    t = fit_thresholds(v, L, positive="ready")
    assert t.n == 14 and t.auto_at is None and t.coverage_auto == 0.0


def test_crc_n19_k0_threshold_exists():
    v, L = synth(19, 0)
    t = fit_thresholds(v, L, positive="ready")
    assert t.n == 19 and t.auto_at is not None
    assert t.risk_bound <= 0.05


def test_crc_n39_k1_threshold_exists():
    v, L = synth(39, 1)
    t = fit_thresholds(v, L, positive="ready")
    assert t.n == 39 and t.auto_at is not None
    assert t.risk_bound <= 0.05


def test_crc_n38_k1_auto_off():
    v, L = synth(38, 1)
    t = fit_thresholds(v, L, positive="ready")
    assert t.n == 38 and t.auto_at is None


def test_report_mode_point_between_19_and_50():
    v, L = synth(20, 0)
    t = fit_thresholds(v, L, positive="ready")
    text = report_text(v, L, {}, t)
    assert "ожидаемый риск <= alpha, точечные метрики справочно" in text
    assert "Клоппера" not in text


def test_report_mode_interval_at_50_plus():
    v, L = synth(50, 0)
    t = fit_thresholds(v, L, positive="ready")
    text = report_text(v, L, {}, t)
    assert "Клоппера" in text
    assert "ожидаемый риск <= alpha" not in text


def test_no_labeled_scores_gives_no_threshold():
    v = [Verdict("i0", None, "human", "ошибка")]
    t = fit_thresholds(v, {"i0": "ready"}, positive="ready")
    assert t.n == 0 and t.auto_at is None


def test_cohens_kappa_textbook_example():
    # 20 (yes,yes), 5 (yes,no), 10 (no,yes), 15 (no,no) — po=0.7, pe=0.5, kappa=0.4
    pairs = [("yes", "yes")] * 20 + [("yes", "no")] * 5 + [("no", "yes")] * 10 + [("no", "no")] * 15
    assert abs(cohens_kappa(pairs) - 0.4) < 1e-9


def test_cohens_kappa_perfect_agreement():
    assert cohens_kappa([("a", "a"), ("b", "b"), ("a", "a")]) == 1.0


def test_clopper_pearson_matches_reference_tables():
    lo, hi = clopper_pearson(5, 20)
    assert abs(lo - 0.0866) < 1e-3 and abs(hi - 0.4910) < 1e-3


def test_report_includes_kappa_only_when_pairs_given():
    v, L = synth(20, 0)
    t = fit_thresholds(v, L, positive="ready")
    assert "каппа" not in report_text(v, L, {}, t)
    text_with_pairs = report_text(v, L, {}, t, rater_pairs=[("a", "a"), ("a", "b")])
    assert "каппа" in text_with_pairs


def test_kappa_reliable_wording_gated_below_25_pairs():
    v, L = synth(20, 0)
    t = fit_thresholds(v, L, positive="ready")
    pairs = [("a", "a")] * 10  # n=10 < 25
    text = report_text(v, L, {}, t, rater_pairs=pairs)
    assert "устойчивая согласованность" not in text
    assert "n=10" in text and "< 25" in text


def test_kappa_reliable_wording_allowed_at_25_plus_pairs():
    v, L = synth(20, 0)
    t = fit_thresholds(v, L, positive="ready")
    pairs = [("a", "a")] * 25  # n=25, идеальное согласие
    text = report_text(v, L, {}, t, rater_pairs=pairs)
    assert "устойчивая согласованность" in text


def test_report_marks_holdout_explicitly():
    v, L = synth(20, 0)
    calib, holdout = L, {"h0": "ready", "h1": "edit"}
    hv = v + [Verdict("h0", 5.0, "x"), Verdict("h1", 5.0, "x")]
    t = fit_thresholds(hv, calib, positive="ready")
    text = report_text(hv, calib, holdout, t)
    assert "holdout" in text and "не участвует в подборе порога" in text
