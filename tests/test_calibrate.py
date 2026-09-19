import json
import pathlib

from typed_judge.batch import Row
from typed_judge.calibrate import agreement, confusion, fit_thresholds, report_text
from typed_judge.recipes import draft_lint as dl
from typed_judge.verdict import Verdict, apply

FIX = pathlib.Path(__file__).parent / "fixtures"


def golden_verdicts():
    res = json.loads((FIX / "draft_lint_results.json").read_text(encoding="utf-8"))["results"]
    return apply([Row(s, f"k-{s}", "gemini", dl.answers_from_gemini_row(r)) for s, r in res.items()], dl.combine)


def labels():
    return json.loads((FIX / "draft_lint_labels.json").read_text(encoding="utf-8"))["labels"]


def test_golden_agreement_3_of_4_and_warning():
    # в labels.json 5 меток, но черновик tiny-local-judge в results.json отсутствует → n=4
    v, L = golden_verdicts(), labels()
    assert agreement(v, L) == (3, 4)
    t = fit_thresholds(v, L, positive="ready")
    assert t.n == 4 and t.reliable is False and "n=4" in t.warning and "20" in t.warning
    text = report_text(v, L, t)
    assert "3/4" in text and "ненадёжны" in text


def test_confusion_counts():
    v, L = golden_verdicts(), labels()
    c = confusion(v, L)
    assert c["ready"]["ready"] == 3 and c["light_edit"]["ready"] == 1


def test_fit_thresholds_on_synthetic():
    v = [Verdict(f"i{i}", s, "x") for i, s in enumerate([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99])]
    L = {f"i{i}": ("ready" if i >= 4 else "edit") for i in range(10)}
    L["i4"] = "edit"  # score 0.6 — помеха: с порога 0.6 precision 5/6 < 0.95
    t = fit_thresholds(v, L, positive="ready", p_min=0.95, min_labels=5)
    assert t.auto_at == 0.7 and t.precision_auto == 1.0 and t.coverage_auto == 0.5
    assert t.human_below == 0.7 and t.reliable is True and t.warning is None


def test_no_threshold_reaches_precision():
    v = [Verdict(f"i{i}", s, "x") for i, s in enumerate([0.9, 0.9, 0.9])]
    t = fit_thresholds(v, {"i0": "ready", "i1": "edit", "i2": "edit"}, positive="ready", min_labels=1)
    assert t.auto_at is None and t.precision_auto is None
