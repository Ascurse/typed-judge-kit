"""bd typed-judge-kit-08p: сравнение трёх переформулировок unsourced (draft_lint v3) на 55 фикстурах.

unsourced в draft_lint_v3 инвертирован (separation -1.00, вето 5/5 на base-фикстурах без единого
внесённого дефекта — см. бид). Здесь v0 (текущая формулировка), a (переписанная) и b (расщеплённая
на два вопроса + конъюнкция в коде) прогоняются ОДНИМ батч-вызовом на item, чтобы сравниваться на
одних и тех же ответах модели, а не на разных сэмплах.

Позитивный класс — nosource (5 фикстур: base-текст без предложения с источником, правильный ответ
unsourced = ДА, см. tests/fixtures/stress/fixtures.json). Отрицательный — base+critical+ru_messy
(40 фикстур, источник есть или проверяемых утверждений нет вовсе — ДА не должно быть). ru_clean
(10) — истины нет (личный опыт, внешний источник неприменим), приводится отдельно, справочно.

Расчёт fire rate / separation переиспользует typed_judge.question_calibration._fire_rate/_mean —
код не пишется заново, только группы фикстур другие. Порог вето — OVERCLAIM_THRESHOLD (0.76) из
draft_lint_v2, тот же, что использует combine() в draft_lint_v3 — не подбирается заново.

Запуск:
  uv run python scripts/unsourced_rewrite_calibration.py --smoke   # 5 фикстур, оценка стоимости
  uv run python scripts/unsourced_rewrite_calibration.py --full    # все 55; гейт $1 по оценке smoke
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from typed_judge import batch
from typed_judge.engines.typesafe import TypeSafeEngine, cost_usd
from typed_judge.question_calibration import _fire_rate, _mean  # переиспользуем расчёт, не пишем заново
from typed_judge.recipes.draft_lint_v2 import OVERCLAIM_THRESHOLD
from typed_judge.unsourced_rewrite import QUESTIONS, variant_b_probability

FIXTURES = pathlib.Path(__file__).parent.parent / "tests/fixtures/stress/fixtures.json"
OUT_DIR = pathlib.Path(
    "/Users/ascurse/Documents/ObsidianSecondBrain/Projects/typed-judge-kit/Outputs/2026-09-20-unsourced-rewrite"
)
CACHE = OUT_DIR / "cache.jsonl"
SMOKE_SUMMARY = OUT_DIR / "smoke_summary.json"
BUDGET_USD = 1.0

NEGATIVE_KINDS = ("base", "critical", "ru_messy")  # источник есть, либо проверяемых утверждений нет
POSITIVE_KIND = "nosource"                          # источника нет — правильный ответ unsourced = ДА
REFERENCE_KIND = "ru_clean"                         # истины нет, приводится справочно

# По одному представителю на группу — smoke только оценивает стоимость на item.
SMOKE_IDS = ["ru-01-messy", "ru-01-clean", "base-01-inbox", "base-01-inbox-negation_flip",
             "base-01-inbox-nosource"]


def load_fixtures() -> dict:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def _ids_of_kinds(fixtures: dict, kinds: tuple[str, ...]) -> list[str]:
    return [it["id"] for it in fixtures["items"] if it["kind"] in kinds]


def _variant_probs(answers_by_item: dict, ids: list[str], variant: str) -> list[float]:
    out = []
    for item_id in ids:
        a = answers_by_item.get(item_id, {})
        if variant == "unsourced_b":
            claim, source = a.get("unsourced_b_has_claim"), a.get("unsourced_b_has_source")
            if claim is None or source is None or claim.error or source.error:
                continue
            if claim.probability is None or source.probability is None:
                continue
            out.append(variant_b_probability(claim.probability, source.probability))
        else:
            ans = a.get(variant)
            if ans is None or ans.error or ans.probability is None:
                continue
            out.append(ans.probability)
    return out


def report_row(answers_by_item: dict, fixtures: dict, variant: str) -> dict:
    positive_ids = _ids_of_kinds(fixtures, (POSITIVE_KIND,))
    negative_ids = _ids_of_kinds(fixtures, NEGATIVE_KINDS)
    reference_ids = _ids_of_kinds(fixtures, (REFERENCE_KIND,))
    base_ids = _ids_of_kinds(fixtures, ("base",))

    pos_probs = _variant_probs(answers_by_item, positive_ids, variant)
    neg_probs = _variant_probs(answers_by_item, negative_ids, variant)
    ref_probs = _variant_probs(answers_by_item, reference_ids, variant)
    base_probs = _variant_probs(answers_by_item, base_ids, variant)

    pos_rate, neg_rate = _fire_rate(pos_probs), _fire_rate(neg_probs)
    sep = None if pos_rate is None or neg_rate is None else round(pos_rate - neg_rate, 3)
    veto_on_base = sum(p >= OVERCLAIM_THRESHOLD for p in base_probs)

    return {
        "variant": variant,
        "n_positive": len(pos_probs), "positive_fire_rate": pos_rate, "positive_mean_p": _mean(pos_probs),
        "n_negative": len(neg_probs), "negative_fire_rate": neg_rate, "negative_mean_p": _mean(neg_probs),
        "separation": sep,
        "n_reference": len(ref_probs), "reference_fire_rate": _fire_rate(ref_probs), "reference_mean_p": _mean(ref_probs),
        "veto_on_base_n": veto_on_base, "veto_on_base_total": len(base_probs),
    }


def _fmt(x) -> str:
    return "-" if x is None else (f"{x:.3f}" if isinstance(x, float) else str(x))


def markdown_report(rows: list[dict]) -> str:
    header = ("| вариант | nosource fire (n) | mean p | base+critical+ru_messy fire (n) | mean p | "
              "separation | вето на base (0.76) | ru_clean fire (n), справочно |")
    sep = "|---|---|---|---|---|---|---|---|"
    lines = [header, sep]
    for r in rows:
        lines.append(
            f"| {r['variant']} | {_fmt(r['positive_fire_rate'])} ({r['n_positive']}) | {_fmt(r['positive_mean_p'])} | "
            f"{_fmt(r['negative_fire_rate'])} ({r['n_negative']}) | {_fmt(r['negative_mean_p'])} | "
            f"{_fmt(r['separation'])} | {r['veto_on_base_n']}/{r['veto_on_base_total']} | "
            f"{_fmt(r['reference_fire_rate'])} ({r['n_reference']}) |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--smoke", action="store_true", help="5 фикстур — прикинуть стоимость перед полным прогоном")
    g.add_argument("--full", action="store_true", help="все 55 фикстур; проверяет оценку из --smoke против бюджета")
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
    engine = TypeSafeEngine()  # key через load_key(), в вывод не печатается
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
        print(f"оценка полного прогона (55 фикстур): ${est_full:.5f}")
        return 1 if errs else 0

    answers_by_item = {r.item_id: r.answers for r in rows}
    table_rows = [report_row(answers_by_item, data, v) for v in ("unsourced_v0", "unsourced_a", "unsourced_b")]
    text = markdown_report(table_rows)
    print(text)
    (OUT_DIR / "table.md").write_text(text + "\n", encoding="utf-8")
    (OUT_DIR / "cost.json").write_text(json.dumps({"cost_usd": cost, "n_rows": len(rows)}, indent=1), encoding="utf-8")
    (OUT_DIR / "table.json").write_text(json.dumps(table_rows, ensure_ascii=False, indent=1), encoding="utf-8")

    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
