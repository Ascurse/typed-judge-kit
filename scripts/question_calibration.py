"""bd typed-judge-kit-13k: калибровка порогов бинарных вопросов draft_lint v3 на стресс-наборе h37.

Бинарные вопросы draft_lint_v3.py (8 STYLE_DEFECTS + CRITICAL_DEFECTS) прогоняются на всех
фикстурах tests/fixtures/stress/fixtures.json, вероятности читаются напрямую (не через
combine()/вердикт) и сводятся в таблицы typed_judge.question_calibration.

Таблицы, потому что истина у вопросов разная:
- стилистические — пары ru_messy/ru_clean, separation по ним;
- критические (overclaim, бид k55) — минимальные пары base/overclaim, дописанный вывод сильнее
  данных. В ru_messy/ru_clean прямой истины по overclaim нет, и до k55 по нему меряли только
  ложные срабатывания;
- целевые стилистические (topic_sprawl, loose_end; бид 0py) — минимальные пары base/<дефект>:
  в ru-парах ни расползания, ни оборванной недосказанности нет, separation по ним был нулевой
  от отсутствия данных, а не от вопроса.

Метки 14 черновиков (labels.json) НЕ участвуют — они holdout по условию бида. Кэш — отдельный
от stress_bench.py (тот гоняет draft_lint_v2 с другим набором вопросов, другой cache_key).

Запуск:
  uv run python scripts/question_calibration.py --smoke   # 5 фикстур, оценка стоимости полного прогона
  uv run python scripts/question_calibration.py --full    # все фикстуры; останавливается, если оценка по smoke > $1
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
    kind_row,
    markdown_kind_table,
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
QUESTION_IDS = STYLE_DEFECTS + CRITICAL_DEFECTS  # порядок отчёта
# Бид k55: положительный класс по overclaim — base-текст с дописанным перегибом; отрицательный —
# те же base-тексты без него. critical/nosource/ru_* в этот счёт не идут: там менялись факт или
# стиль, а не сила вывода, и в отрицательный класс их брать нельзя без отдельной разметки.
CRITICAL_POSITIVE_KIND = "overclaim"
CRITICAL_NEGATIVE_KINDS = ("base",)
# Бид 0py: вопрос -> kind положительного класса; отрицательный тот же — base без дописанного.
TARGETED_KINDS = {"topic_sprawl": "topic_sprawl", "loose_end": "loose_end"}

# По одному представителю каждой группы фикстур (ru_messy/ru_clean/base/critical) —
# smoke только оценивает стоимость на item, полное покрытие групп ему не нужно.
SMOKE_IDS = ["ru-01-messy", "ru-01-clean", "base-01-inbox", "base-01-inbox-negation_flip",
             "base-01-inbox-overclaim", "base-01-inbox-topic_sprawl", "base-01-inbox-loose_end"]


def table_heading() -> str:
    return "### Стилистические вопросы (истина — пары ru_messy/ru_clean)"


def crit_heading() -> str:
    return (f"### Критические вопросы (истина — пары {CRITICAL_NEGATIVE_KINDS[0]}/"
            f"{CRITICAL_POSITIVE_KIND}, бид k55)")


def targeted_heading(qid: str) -> str:
    return f"### Целевой стилистический вопрос {qid} (истина — пары base/{TARGETED_KINDS[qid]}, бид 0py)"


def load_fixtures() -> dict:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--smoke", action="store_true", help="7 фикстур — прикинуть стоимость перед полным прогоном")
    g.add_argument("--full", action="store_true", help="все фикстуры; проверяет оценку из --smoke против бюджета")
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
        print(f"оценка полного прогона ({len(data['items'])} фикстур): ${est_full:.5f}")
        return 1 if errs else 0

    answers_by_item = {r.item_id: r.answers for r in rows}
    table = question_table(answers_by_item, data, QUESTION_IDS)
    crit = [kind_row(answers_by_item, data, qid, positive_kind=CRITICAL_POSITIVE_KIND,
                     negative_kinds=CRITICAL_NEGATIVE_KINDS) for qid in CRITICAL_DEFECTS]
    text = (f"{table_heading()}\n\n{markdown_table(table)}\n\n{crit_heading()}\n\n"
            f"{markdown_kind_table(crit, CRITICAL_POSITIVE_KIND, CRITICAL_NEGATIVE_KINDS)}")
    for qid, kind in TARGETED_KINDS.items():
        row = kind_row(answers_by_item, data, qid, positive_kind=kind, negative_kinds=CRITICAL_NEGATIVE_KINDS)
        text += f"\n\n{targeted_heading(qid)}\n\n{markdown_kind_table([row], kind, CRITICAL_NEGATIVE_KINDS)}"
    print(text)
    (OUT_DIR / "table.md").write_text(text + "\n", encoding="utf-8")
    (OUT_DIR / "cost.json").write_text(json.dumps({"cost_usd": cost, "n_rows": len(rows)}, indent=1), encoding="utf-8")

    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
