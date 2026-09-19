"""Двухшаговый claim-vs-evidence (бид typed-judge-kit-q36): извлечение утверждений + проверка против источника.

Без сети — на голых строках и Answer. Шаг 1 детерминированный (движок не возвращает текст,
см. draft_lint_v3.COT_FIRST_LIMITATION), поэтому его можно проверять здесь целиком.
"""
from typed_judge import claim_check
from typed_judge.questions import Answer


def test_extract_claims_keeps_sentences_with_numbers_dates_names_or_quotes():
    text = ("Я поставил агента разбирать входящие. За три месяца он обработал 2200 писем. "
            "Дмитрий Волков сверил лог вручную. Это удобно и приятно.")
    claims = claim_check.extract_claims(text)
    assert claims == ["За три месяца он обработал 2200 писем.", "Дмитрий Волков сверил лог вручную."]


def test_extract_claims_ignores_capitalized_word_that_only_starts_a_sentence():
    assert claim_check.extract_claims("Агент работает хорошо. Всё стабильно.") == []


def test_extract_claims_caps_the_number_of_claims():
    text = " ".join(f"Факт номер {i} подтверждён." for i in range(20))
    assert len(claim_check.extract_claims(text, limit=5)) == 5


def test_questions_for_makes_two_phrasings_per_claim_plus_holistic_control():
    qs = claim_check.questions_for(["Обработал 2200 писем."])
    assert set(qs) == {"claim_0_contradicts", "claim_0_supported", claim_check.HOLISTIC_QID}
    assert "2200" in qs["claim_0_contradicts"].instructions
    assert "2200" in qs["claim_0_supported"].instructions


def test_state_puts_source_before_draft_and_labels_both():
    state = claim_check.state_for(draft="черновик", source="заметка")
    assert state.index("заметка") < state.index("черновик")
    assert "ИСТОЧНИК" in state and "ЧЕРНОВИК" in state


def test_unsupported_by_contradiction_phrasing_fires_above_threshold():
    answers = {"claim_0_contradicts": Answer(probability=0.9), "claim_1_contradicts": Answer(probability=0.2)}
    assert claim_check.unsupported(answers, n_claims=2, threshold=0.5) == [0]


def test_unsupported_by_support_phrasing_fires_below_threshold():
    answers = {"claim_0_supported": Answer(probability=0.1), "claim_1_supported": Answer(probability=0.8)}
    assert claim_check.unsupported(answers, n_claims=2, threshold=0.5, phrasing="supported") == [0]


def test_unsupported_skips_errored_or_missing_answers():
    answers = {"claim_0_contradicts": Answer(error="boom"), "claim_1_contradicts": Answer(probability=0.99)}
    assert claim_check.unsupported(answers, n_claims=3, threshold=0.5) == [1]


def test_veto_lowers_ready_but_leaves_other_verdicts_alone():
    assert claim_check.veto("ready", unsupported=[0]) == "light_edit"
    assert claim_check.veto("ready", unsupported=[]) == "ready"
    assert claim_check.veto("heavy_edit", unsupported=[0]) == "heavy_edit"


# --- гейт на закэшированном живом прогоне (uv run python scripts/claim_check_run.py) ---

import json
import pathlib

import pytest

from typed_judge.batch import read_rows
from typed_judge.recipes import draft_lint_v3
from typed_judge.stress import AUTO, auto_status
from typed_judge.verdict import Verdict

_FIX = pathlib.Path(__file__).parent / "fixtures" / "stress"
_DATA = json.loads((_FIX / "fixtures.json").read_text(encoding="utf-8"))
_ROWS = {r.item_id: r for r in read_rows(_FIX / "claim_check_cache.jsonl")}
_CRITICAL = {it["id"] for it in _DATA["items"] if it["kind"] == "critical"}
_BASE = {it["id"] for it in _DATA["items"] if it["kind"] == "base"}


def _holistic_fired(item_id: str) -> bool:
    a = _ROWS[item_id].answers[claim_check.HOLISTIC_QID]
    return not a.error and a.probability is not None and a.probability >= 0.5


def _verdicts_after_claim_check() -> list[Verdict]:
    """Судья-по-стилю отдал бы ready всем: на критических фикстурах меняется факт, а не стиль."""
    out = []
    for item_id in sorted(_CRITICAL | _BASE):
        v = claim_check.veto("ready", unsupported=[0] if _holistic_fired(item_id) else [])
        out.append(Verdict(item_id, 0.9, v))
    return out


def test_claim_check_cache_covers_every_critical_and_base_fixture():
    assert _CRITICAL | _BASE <= set(_ROWS)
    assert all(r.error is None for r in _ROWS.values())


@pytest.mark.stress
def test_v3_with_claim_check_closes_the_auto_off_gate_of_h37():
    """Гейт текущего конвейера (бид q36): draft_lint_v3 + шаг claim-vs-evidence.

    Сам v3 пропускает 19 из 25 критических фикстур (живой прогон 2026-09-20,
    tests/fixtures/stress/v3_cache.jsonl) — его вопросы про качество письма, а не про факты.
    Шаг claim-vs-evidence против парного base-источника закрывает все 19 и не трогает base.
    """
    v3_rows = {r.item_id: r for r in read_rows(_FIX / "v3_cache.jsonl")}
    verdicts = []
    for item_id, row in sorted(v3_rows.items()):
        score, verdict = draft_lint_v3.combine(row.answers)
        if item_id in _ROWS:
            verdict = claim_check.veto(verdict, [0] if _holistic_fired(item_id) else [])
        verdicts.append(Verdict(item_id, score, verdict))
    status = auto_status(verdicts, _CRITICAL)
    assert status.status == AUTO, f"auto off: пропущены {status.missed}"


@pytest.mark.stress
def test_claim_check_step_alone_catches_every_critical_fixture():
    """Бид q36. draft_lint_v2 пропускал 20/25 критических (см. test_stress_bench). Целостный вопрос
    claim-vs-evidence против парного base-источника ловит 25/25 при нуле ложных на base —
    живой прогон 2026-09-20, $0.00218, tests/fixtures/stress/claim_check_cache.jsonl.
    """
    status = auto_status(_verdicts_after_claim_check(), _CRITICAL)
    assert status.status == AUTO, f"auto off: пропущены {status.missed}"


def test_claim_check_does_not_veto_clean_base_fixtures():
    assert [v.item_id for v in _verdicts_after_claim_check()
            if v.item_id in _BASE and v.verdict != "ready"] == []
