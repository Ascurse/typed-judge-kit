"""Прогон стресс-набора по ЗАКЭШИРОВАННЫМ ответам typesafe:jev-latest (без сети) — bead typed-judge-kit-h37.

Кэш tests/fixtures/stress/cache.jsonl — живой прогон 2026-09-20 (uv run scripts/stress_bench.py), стоимость $0.00303.
Живой сетевой прогон — отдельно, вручную (пропущен маркер network в pyproject не нужен: сеть тут вообще не идёт,
кэш уже полный; при обновлении промпта/API кэш нужно перегенерировать скриптом заново).
"""
import json
import pathlib

import pytest

from typed_judge.batch import read_rows
from typed_judge.recipes import draft_lint_v2 as recipe
from typed_judge.stress import AUTO, auto_status, flip_rate
from typed_judge.verdict import apply

FIX = pathlib.Path(__file__).parent / "fixtures" / "stress"
DATA = json.loads((FIX / "fixtures.json").read_text(encoding="utf-8"))
ROWS = read_rows(FIX / "cache.jsonl")
VERDICTS = apply(ROWS, recipe.combine)
CRITICAL_IDS = {it["id"] for it in DATA["items"] if it["kind"] == "critical"}


def _ru_pairs() -> list[tuple[str, str]]:
    by_pair: dict[str, dict[str, str]] = {}
    for it in DATA["items"]:
        if it["kind"] in ("ru_messy", "ru_clean"):
            by_pair.setdefault(it["pair"], {})[it["kind"]] = it["id"]
    return [(v["ru_messy"], v["ru_clean"]) for v in by_pair.values()]


def test_cache_covers_all_fifty_fixtures_without_engine_errors():
    assert len(ROWS) == 50
    assert all(r.error is None for r in ROWS)
    assert len(CRITICAL_IDS) == 25


def test_flip_rate_on_live_cached_run_is_zero():
    """Золотое значение живого прогона 2026-09-20: ни одна RU-пара не оценена хуже канцелярита-исходника."""
    assert flip_rate(_ru_pairs(), VERDICTS) == 0.0


@pytest.mark.stress
def test_auto_off_gate_on_cached_stress_run():
    """Исполняемое правило DR-62 §3.2: пропуск хотя бы одного критического дефекта → auto off.

    ЧЕСТНЫЙ РЕЗУЛЬТАТ живого прогона 2026-09-20 (typesafe:jev-latest, tests/fixtures/stress/cache.jsonl):
    draft_lint_v2 пропустил 20 из 25 критических фикстур (получили ready вместо не-ready) — инверсии «не»,
    подмены дат/имён/чисел и смысловые абсурды, которые не меняют стиль/риторику текста, рецепт не ловит,
    потому что его вопросы (hook/evidence/tone/overclaim/...) про качество письма, а не про фактическую
    и логическую состоятельность. Это ровно тот tail risk, который DR-62 просит закрывать стресс-бенчем,
    а не статистикой на 14 метках.

    Тест НЕ подогнан под зелёный и НЕ помечен xfail: правило обязано падать, когда есть реальный пропуск.
    Чтобы красный гейт не маскировал остальной набор, он под маркером stress и гоняется явно: pytest -m stress.
    """
    status = auto_status(VERDICTS, CRITICAL_IDS)
    assert status.status == AUTO, f"auto off: пропущены критические фикстуры {status.missed}"
