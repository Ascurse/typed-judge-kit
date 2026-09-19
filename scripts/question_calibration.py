"""bd typed-judge-kit-13k: калибровка порогов бинарных вопросов draft_lint v3 на стресс-наборе h37.

10 бинарных вопросов (8 STYLE_DEFECTS + 2 CRITICAL_DEFECTS из draft_lint_v3.py) прогоняются
на всех 50 фикстурах tests/fixtures/stress/fixtures.json, вероятности читаются напрямую
(не через combine()/вердикт) и сводятся в таблицу typed_judge.question_calibration.

Метки 14 черновиков (labels.json) НЕ участвуют — они holdout по условию бида. Кэш — отдельный
от stress_bench.py (тот гоняет draft_lint_v2 с другим набором вопросов, другой cache_key).

Запуск:
  uv run python scripts/question_calibration.py --smoke   # 4 фикстуры, оценка стоимости полного прогона
  uv run python scripts/question_calibration.py --full    # все 50; останавливается, если оценка по smoke > $1
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from typed_judge import batch
from typed_judge.engines.typesafe import TypeSafeEngine, cost_usd
from typed_judge.question_calibration import (
    markdown_table,
    question_table,
)
from typed_judge.recipes.draft_lint_v3 import (
    CRITICAL_DEFECTS,
    QUESTIONS,
    STYLE_DEFECTS,
)

FIXTURES = pathlib.Path(__file__).parent.parent / "tests/fixtures/stress/fixtures.json"
OUT_DIR = pathlib.Path(
    "/Users/ascurse/Documents/ObsidianSecondBrain/Projects/typed-judge-kit/Outputs/2026-09-20-question-calibration-v3"
)
CACHE = OUT_DIR / "cache.jsonl"
SMOKE_SUMMARY = OUT_DIR / "smoke_summary.json"
BUDGET_USD = 1.0
QUESTION_IDS = STYLE_DEFECTS + CRITICAL_DEFECTS  # 8 + 2 = 10, порядок отчёта

# По одному представителю каждой группы фикстур (ru_messy/ru_clean/base/critical) —
# smoke только оценивает стоимость на item, полное покрытие групп ему не нужно.
SMOKE_IDS = ["ru-01-messy", "ru-01-clean", "base-01-inbox", "base-01-inbox-negation_flip"]


def load_fixtures() -> dict:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--smoke", action="store_true", help="4 фикстуры — прикинуть стоимость перед полным прогоном")
    g.add_argument("--full", action="store_true", help="все 50 фикстур; проверяет оценку из --smoke против бюджета")
    a = ap.parse_args(argv)

    if a.full and SMOKE_SUMMARY.exists():
        est = json.loads(SMOKE_SUMMARY.read_text(encoding="utf-8"))["estimated_full_cost_usd"]
        if est > BUDGET_USD:
            print(f"оценка полного прогона ${est:.4f} > бюджета ${BUDGET_USD} — остановлено", file=sys.stderr)
            return 1

    data = load_fixtures()
    items = {it["id"]: it["text"] for it in data["items"]}
    if a.smoke:
        items = {k: items[k] for k in SMOKE_IDS}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    engine = TypeSafeEngine()
    rows = batch.run(engine, items, QUESTIONS, CACHE)

    errs = [f"{r.item_id}: {r.error}" for r in rows if r.error]
    errs += [f"{r.item_id}/{qid}: {ans.error}" for r in rows for qid, ans in r.answers.items() if ans.error]
    cost = cost_usd(sum(r.input_tokens for r in rows))
    print(f"строк: {len(rows)}, ошибок: {len(errs)}, стоимость: ${cost:.5f}")
    for e in errs[:20]:
        print("ERROR", e)

    if a.smoke:
        est_full = cost * (len(data["items"]) / max(len(items), 1))
        SMOKE_SUMMARY.write_text(json.dumps({
            "errors": errs, "smoke_cost_usd": cost, "estimated_full_cost_usd": est_full,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"оценка полного прогона (50 фикстур): ${est_full:.5f}")
        return 1 if errs else 0

    answers_by_item = {r.item_id: r.answers for r in rows}
    table = question_table(answers_by_item, data, QUESTION_IDS)
    text = markdown_table(table)
    print(text)
    (OUT_DIR / "table.md").write_text(text + "\n", encoding="utf-8")
    (OUT_DIR / "cost.json").write_text(json.dumps({"cost_usd": cost, "n_rows": len(rows)}, indent=1), encoding="utf-8")

    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
