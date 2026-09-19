"""bd typed-judge-kit-3jk: замер авторегрессионной контаминации 10 вопросов draft_lint.

Режимы (спека — DR-63, раздел 3.1 «открытые вопросы»):
  А — единый вызов, прямой порядок вопросов (как в draft_lint.QUESTIONS);
  Б — единый вызов, инвертированный порядок;
  В — 10 изолированных вызовов (contamination.run_isolated), по одному вопросу на текст.

14 черновиков (тот же набор, что Inputs/labels.json калибровки v2) × 3 режима × 5 прогонов.
Движок typesafe:jev-latest, ключ из env/~/.hermes/.env через load_key() (никогда не печатается).

Кэш: отдельный jsonl на (режим, повтор) в OUT_DIR — гарантирует, что все 5 повторов реально
зовут модель, а не читают кэш друг друга (по cache_key порядок вопросов не различается,
т.к. question_spec сортирует ключи для хеша — поэтому А и Б тоже обязаны жить в разных файлах).

Запуск:
  uv run python scripts/contamination.py --smoke   # 1 черновик × 3 режима × 1 повтор, проверка + оценка стоимости
  uv run python scripts/contamination.py --full     # весь дизайн; бюджет $1 проверяется перед стартом
  uv run python scripts/contamination.py --analyze  # посчитать Hamming по уже накопленным кэшам, без новых вызовов
"""
from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from typed_judge import batch, contamination  # noqa: E402
from typed_judge.engines.typesafe import TypeSafeEngine, cost_usd  # noqa: E402
from typed_judge.recipes.draft_lint import QUESTIONS  # noqa: E402

VAULT_DRAFTS = pathlib.Path("/Users/ascurse/Documents/ObsidianSecondBrain/output/Content/drafts")
OUT_DIR = pathlib.Path(
    "/Users/ascurse/Documents/ObsidianSecondBrain/Projects/typed-judge-kit/Outputs/2026-09-20-contamination"
)
BUDGET_USD = 1.0
REPS = (1, 2, 3, 4, 5)
MODES = ("A", "B", "V")

# тот же набор и порядок, что Inputs/labels.json (14 черновиков калибровки v2)
ITEM_IDS = [
    "2026-08-14-less-context-wins",
    "2026-08-15-independent-dataset-written-by-the-registry",
    "2026-08-15-the-cost-of-a-gate-is-the-rollback",
    "2026-09-18-tiny-local-judge",
    "2026-09-04-memory-eval-reranker-thread-x",
    "2026-08-12-better-prompts-stopped-being-the-lever",
    "2026-08-15-showing-the-model-its-own-mistake",
    "2026-09-04-memory-eval-reader-abstention",
    "2026-09-04-memory-eval-reranker",
    "2026-09-14-second-brain-eval-substack",
    "2026-09-18-reply-threads-jev-clone",
    "2026-09-18-testing-jev-and-its-clones",
    "2026-09-19-jev-checker-layer",
    "2026-09-20-typed-judge-negative-results",
]

MODE_QUESTIONS = {
    "A": QUESTIONS,
    "B": dict(reversed(list(QUESTIONS.items()))),
    "V": QUESTIONS,  # порядок неважен: run_isolated шлёт по одному вопросу за вызов
}


def load_items(item_ids: list[str]) -> dict[str, str]:
    out = {}
    for item_id in item_ids:
        text = (VAULT_DRAFTS / f"{item_id}.md").read_text(encoding="utf-8")
        if text.startswith("---"):
            text = text.split("---", 2)[-1].strip()
        out[item_id] = text
    return out


def run_mode_rep(mode: str, rep: int, engine, items: dict[str, str]) -> list[batch.Row]:
    cache = OUT_DIR / f"{mode}_rep{rep}.jsonl"
    if mode == "V":
        return contamination.run_isolated(engine, items, MODE_QUESTIONS[mode], cache)
    return batch.run(engine, items, MODE_QUESTIONS[mode], cache)


def collect(item_ids: list[str], reps: tuple[int, ...]) -> dict[tuple[str, int], dict[str, batch.Row]]:
    """(режим, повтор) -> {item_id: Row}."""
    items = load_items(item_ids)
    engine = TypeSafeEngine()
    result = {}
    for mode in MODES:
        for rep in reps:
            rows = run_mode_rep(mode, rep, engine, items)
            result[(mode, rep)] = {r.item_id: r for r in rows}
    return result


def report_errors(data: dict[tuple[str, int], dict[str, batch.Row]]) -> list[str]:
    errors = []
    for (mode, rep), rows in data.items():
        for item_id, row in rows.items():
            if row.error:
                errors.append(f"{mode}/rep{rep}/{item_id}: строка — {row.error}")
            for qid, ans in row.answers.items():
                if ans.error:
                    errors.append(f"{mode}/rep{rep}/{item_id}: {qid} — {ans.error}")
    return errors


def total_cost_usd(data: dict[tuple[str, int], dict[str, batch.Row]]) -> float:
    total_input = sum(row.input_tokens for rows in data.values() for row in rows.values())
    return cost_usd(total_input)


def hamming_table(data: dict[tuple[str, int], dict[str, batch.Row]], item_ids: list[str], reps: tuple[int, ...]):
    """Возвращает (inter_per_pair_per_item, intra_per_mode_per_item) — сырые списки расстояний."""
    inter = {("A", "B"): {}, ("A", "V"): {}, ("B", "V"): {}}
    intra = {"A": {}, "B": {}, "V": {}}
    for item_id in item_ids:
        for m1, m2 in inter:
            dists = []
            for r1, r2 in itertools.product(reps, reps):
                a = data[(m1, r1)][item_id].answers
                b = data[(m2, r2)][item_id].answers
                dists.append(contamination.hamming(a, b, QUESTIONS))
            inter[(m1, m2)][item_id] = statistics.mean(dists)
        for mode in intra:
            dists = []
            for r1, r2 in itertools.combinations(reps, 2):
                a = data[(mode, r1)][item_id].answers
                b = data[(mode, r2)][item_id].answers
                dists.append(contamination.hamming(a, b, QUESTIONS))
            intra[mode][item_id] = statistics.mean(dists) if dists else 0.0
    return inter, intra


def summarize(inter, intra, item_ids: list[str]) -> dict:
    inter_mean_by_pair = {f"{a}-{b}": statistics.mean(v.values()) for (a, b), v in inter.items()}
    intra_mean_by_mode = {m: statistics.mean(v.values()) for m, v in intra.items()}
    inter_overall = statistics.mean(inter_mean_by_pair.values())
    intra_overall = statistics.mean(intra_mean_by_mode.values())
    return {
        "per_item": {
            item_id: {
                "inter": {f"{a}-{b}": inter[(a, b)][item_id] for (a, b) in inter},
                "intra": {m: intra[m][item_id] for m in intra},
            }
            for item_id in item_ids
        },
        "inter_mean_by_pair": inter_mean_by_pair,
        "intra_mean_by_mode": intra_mean_by_mode,
        "inter_overall": inter_overall,
        "intra_overall": intra_overall,
        "verdict": verdict(inter_overall, intra_overall),
    }


def verdict(inter_overall: float, intra_overall: float) -> str:
    """Критерий зафиксирован в vault-замере ДО прогона: D>=N+1.0 И D>=1.5*N — контаминация подтверждена;
    выполнено ровно одно условие — сигнал слабый/неубедительный; ни одного — не обнаружена.
    Вырожденный случай N=0 (нулевой внутренний шум): множитель 1.5*0=0 тривиально верен при любом D>0,
    поэтому здесь правило 1.5× не считается — судит только абсолютный порог D>=1.0."""
    if intra_overall == 0:
        if inter_overall >= 1.0:
            return "контаминация подтверждена"
        if inter_overall > 0:
            return "слабый/неубедительный сигнал"
        return "контаминация не обнаружена (в пределах шума)"
    strong = inter_overall >= intra_overall + 1.0 and inter_overall >= 1.5 * intra_overall
    weak = inter_overall >= intra_overall + 1.0 or inter_overall >= 1.5 * intra_overall
    if strong:
        return "контаминация подтверждена"
    if weak:
        return "слабый/неубедительный сигнал"
    return "контаминация не обнаружена (в пределах шума)"


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--smoke", action="store_true")
    g.add_argument("--full", action="store_true")
    g.add_argument("--analyze", action="store_true")
    a = ap.parse_args()

    item_ids = ITEM_IDS[:1] if a.smoke else ITEM_IDS
    reps = (1,) if a.smoke else REPS
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if a.analyze:
        item_ids, reps = ITEM_IDS, REPS
        data = {(m, r): {row.item_id: row for row in batch.read_rows(OUT_DIR / f"{m}_rep{r}.jsonl")}
                for m in MODES for r in reps}
    else:
        if a.full:
            # оценка по смоуку уже должна лежать в OUT_DIR/smoke_summary.json — бюджет проверяем и здесь
            smoke_path = OUT_DIR / "smoke_summary.json"
            if smoke_path.exists():
                est = json.loads(smoke_path.read_text(encoding="utf-8"))["estimated_full_cost_usd"]
                if est > BUDGET_USD:
                    print(f"оценка полного прогона ${est:.4f} > бюджета ${BUDGET_USD} — остановлено", file=sys.stderr)
                    return 1
        data = collect(item_ids, reps)

    errors = report_errors(data)
    cost = total_cost_usd(data)
    print(f"строк: {sum(len(v) for v in data.values())}, ошибок: {len(errors)}, стоимость: ${cost:.4f}")
    for e in errors[:20]:
        print("ERROR", e)

    summary_path = OUT_DIR / ("smoke_summary.json" if a.smoke else "full_summary.json")
    if a.smoke:
        # грубая экстраполяция на полный дизайн: та же цена за вызов, ×14 черновиков ×5 повторов
        n_smoke_items, n_full_items = len(item_ids), len(ITEM_IDS)
        est_full = cost * (n_full_items / max(n_smoke_items, 1)) * (len(REPS) / max(len(reps), 1))
        summary_path.write_text(json.dumps({
            "errors": errors, "smoke_cost_usd": cost, "estimated_full_cost_usd": est_full,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"оценка полного прогона (14×3×5): ${est_full:.4f}")
    else:
        inter, intra = hamming_table(data, item_ids, reps)
        summary = summarize(inter, intra, item_ids)
        summary["errors"] = errors
        summary["total_cost_usd"] = cost
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({k: v for k, v in summary.items() if k not in ("per_item",)}, ensure_ascii=False, indent=1))

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
