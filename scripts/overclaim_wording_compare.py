"""bd typed-judge-kit-p6g: сдвигает ли «Пример нарушения» распределение overclaim.

Порог OVERCLAIM_THRESHOLD = 0.76 подобран в draft_lint_v2 на формулировке без примера, а v3
задаёт тот же вопрос через _defect() — с дописанным «Пример нарушения: ...». Перенесён был
только число, не замер. Здесь обе формулировки гоняются на одних и тех же 70 фикстурах
stress/fixtures.json; всё остальное в батче идентично (полный набор вопросов v3), различается
ровно одна строка instructions.

Прогон v3-формулировки бесплатен: набор вопросов совпадает с question_calibration.py, cache_key
тот же, ответы берутся из его кэша. Платит только прогон v2-формулировки.

Запуск:
  uv run python scripts/overclaim_wording_compare.py
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from typed_judge import batch
from typed_judge.engines.typesafe import TypeSafeEngine, cost_usd
from typed_judge.question_calibration import kind_row, markdown_kind_table, paired_shift
from typed_judge.recipes.draft_lint_v2 import FLAGS as V2_FLAGS, OVERCLAIM_THRESHOLD
from typed_judge.recipes.draft_lint_v3 import QUESTIONS as V3_QUESTIONS

FIXTURES = pathlib.Path(__file__).parent.parent / "tests/fixtures/stress/fixtures.json"
V3_CACHE = pathlib.Path(
    "/Users/ascurse/Documents/ObsidianSecondBrain/Projects/typed-judge-kit/Outputs/"
    "2026-09-20-question-calibration-v3/cache.jsonl"
)
OUT_DIR = pathlib.Path(
    "/Users/ascurse/Documents/ObsidianSecondBrain/Projects/typed-judge-kit/Outputs/"
    "2026-09-20-overclaim-wording-p6g"
)
V2_CACHE = OUT_DIR / "cache_v2_wording.jsonl"
POSITIVE_KIND, NEGATIVE_KINDS = "overclaim", ("base",)

# Единственное различие между прогонами: instructions вопроса overclaim.
QUESTIONS_V3 = V3_QUESTIONS
QUESTIONS_V2 = {**V3_QUESTIONS, "overclaim": V2_FLAGS["overclaim"]}


def _run(items: dict[str, str], questions, cache: pathlib.Path) -> tuple[dict, float, list[str]]:
    rows = batch.run(TypeSafeEngine(), items, questions, cache)
    errs = [f"{r.item_id}: {r.error}" for r in rows if r.error]
    errs += [f"{r.item_id}/{q}: {a.error}" for r in rows for q, a in r.answers.items() if a.error]
    return {r.item_id: r.answers for r in rows}, cost_usd(sum(r.input_tokens for r in rows)), errs


def _probs_of_kind(answers: dict, fixtures: dict, kind: str) -> list[float]:
    out = []
    for it in fixtures["items"]:
        if it["kind"] != kind:
            continue
        ans = answers.get(it["id"], {}).get("overclaim")
        if ans is not None and not ans.error and ans.probability is not None:
            out.append(ans.probability)
    return out


def main() -> int:
    data = json.loads(FIXTURES.read_text(encoding="utf-8"))
    items = {it["id"]: it["text"] for it in data["items"]}
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    a_v3, cost_v3, errs_v3 = _run(items, QUESTIONS_V3, V3_CACHE)
    a_v2, cost_v2, errs_v2 = _run(items, QUESTIONS_V2, V2_CACHE)
    errs = errs_v3 + errs_v2
    print(f"фикстур: {len(items)}, ошибок: {len(errs)}, стоимость: v3 ${cost_v3:.5f} (кэш) + "
          f"v2-формулировка ${cost_v2:.5f}")
    for e in errs[:20]:
        print("ERROR", e)

    shift = paired_shift(a_v2, a_v3, "overclaim", threshold=OVERCLAIM_THRESHOLD)
    rows = [kind_row(a, data, "overclaim", positive_kind=POSITIVE_KIND, negative_kinds=NEGATIVE_KINDS)
            for a in (a_v2, a_v3)]
    text = (
        f"### Сдвиг overclaim от «Пример нарушения» (порог {OVERCLAIM_THRESHOLD}, "
        f"пары по item_id, delta = p_v3 − p_v2)\n\n"
        "| n пар | mean delta | max abs delta | fire v2-форм. | fire v3-форм. | переходов через порог |\n"
        "|---|---|---|---|---|---|\n"
        f"| {shift.n} | {shift.mean_delta} | {shift.max_abs_delta} | {shift.fire_rate_a} | "
        f"{shift.fire_rate_b} | {shift.n_flips} |\n\n"
        f"### Разделение base/overclaim по каждой формулировке (порог {OVERCLAIM_THRESHOLD})\n\n"
    )
    # markdown_kind_table считает fire по 0.5; для порога 0.76 отдельная строка ниже.
    for label, a in (("v2-формулировка (без примера)", a_v2), ("v3-формулировка (с примером)", a_v3)):
        r = kind_row(a, data, "overclaim", positive_kind=POSITIVE_KIND, negative_kinds=NEGATIVE_KINDS)
        pos = _probs_of_kind(a, data, POSITIVE_KIND)
        neg = [p for k in NEGATIVE_KINDS for p in _probs_of_kind(a, data, k)]
        at_thr = (sum(p >= OVERCLAIM_THRESHOLD for p in pos) / len(pos)
                  - sum(p >= OVERCLAIM_THRESHOLD for p in neg) / len(neg))
        text += (f"**{label}** — separation@0.5 {r.separation}, separation@{OVERCLAIM_THRESHOLD} "
                 f"{round(at_thr, 3)}, mean p: {POSITIVE_KIND} {r.positive_mean_prob} / "
                 f"base {r.negative_mean_prob}, зазор pos {min(pos):.2f}..{max(pos):.2f}, "
                 f"neg {min(neg):.2f}..{max(neg):.2f}\n\n")
    text += markdown_kind_table(rows, POSITIVE_KIND, NEGATIVE_KINDS) + "\n"
    print(text)
    (OUT_DIR / "table.md").write_text(text, encoding="utf-8")
    (OUT_DIR / "cost.json").write_text(
        json.dumps({"cost_usd_v2_wording": cost_v2, "cost_usd_v3_cached": cost_v3,
                    "n_fixtures": len(items)}, indent=1), encoding="utf-8")
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
