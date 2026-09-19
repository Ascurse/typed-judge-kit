"""bd typed-judge-kit-qei: доля 14 черновиков в зоне сомнения. Без новых вызовов — только кэш.

Ширина полосы предрегистрирована в биде до этого прогона (routing.BAND_WIDTH = 0.10, ±0.05 вокруг
границ рецепта 0.72 и 0.5) и по результату не двигается — калибровка ширины ждёт 30+ меток.

Два независимых триггера: расстояние до границы (по v2, кэш прогона 2026-09-20) и расхождение
трёх повторов (по v3, rep1/rep2/rep3 — отдельные кэши, модель звалась заново).

Запуск: uv run python scripts/routing_band.py
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from typed_judge import routing
from typed_judge.batch import read_rows
from typed_judge.recipes import draft_lint_v2, draft_lint_v3
from typed_judge.verdict import apply

OUT_ROOT = pathlib.Path(
    "/Users/ascurse/Documents/ObsidianSecondBrain/Projects/typed-judge-kit/Outputs")
V2_CACHE = OUT_ROOT / "2026-09-20-run-typesafe-v2.jsonl"
LABELS = OUT_ROOT.parent / "Inputs" / "labels.json"
V3_REPS = [OUT_ROOT / "2026-09-20-run-typesafe-v3" / f"rep{i}.jsonl" for i in (1, 2, 3)]
OUT_DIR = OUT_ROOT / "2026-09-20-routing-band-qei"
# Все оси, от которых зависит вердикт draft_lint.combine: итоговый composite и два гейта ready.
# Гейты — не «дополнение»: на 14 черновиках именно они делят ready/light_edit, composite у всех
# кроме одного лежит выше 0.72 (см. docstring routing.py).
def margins_of(row_answers, score: float) -> dict[str, float]:
    return {
        "composite->0.72": routing.margin(score, 0.72),
        "composite->0.50": routing.margin(score, 0.50),
        "hook->2": routing.margin(float(row_answers["hook"].value), 2, scale=3),
        "evidence->0.6": routing.margin(row_answers["evidence"].probability, 0.6),
    }


def main() -> int:
    v2_rows = {r.item_id: r for r in read_rows(V2_CACHE)}
    v2 = apply(list(v2_rows.values()), draft_lint_v2.combine)
    reps = [{v.item_id: v.verdict for v in apply(read_rows(p), draft_lint_v3.combine)} for p in V3_REPS]

    band_only, repeat_only, both, clean = [], [], [], []
    for v in v2:
        rep_list = [r[v.item_id] for r in reps if v.item_id in r]
        m = margins_of(v2_rows[v.item_id].answers, v.score)
        in_band = routing.route(v, margins=m).verdict == routing.REVIEW_REQUIRED
        disagree = len(set(rep_list)) > 1
        (both if in_band and disagree else band_only if in_band
         else repeat_only if disagree else clean).append(v.item_id)

    routed = [routing.route(v, margins=margins_of(v2_rows[v.item_id].answers, v.score),
                            repeats=[r[v.item_id] for r in reps if v.item_id in r]) for v in v2]
    n = len(v2)
    lines = [
        f"### Зона сомнения на 14 черновиках (ширина {routing.BAND_WIDTH} доли шкалы)", "",
        "Оси: composite->0.72, composite->0.50, hook->2 (шкала 0..3), evidence->0.6.", "",
        "| триггер | черновиков | доля |", "|---|---|---|",
        f"| в полосе вокруг границы | {len(band_only) + len(both)} | "
        f"{(len(band_only) + len(both)) / n:.3f} |",
        f"| расхождение 3 повторов (v3) | {len(repeat_only) + len(both)} | "
        f"{(len(repeat_only) + len(both)) / n:.3f} |",
        f"| оба триггера сразу | {len(both)} | {len(both) / n:.3f} |",
        f"| **итого review_required** | {sum(v.verdict == routing.REVIEW_REQUIRED for v in routed)} | "
        f"{routing.review_share(routed):.3f} |",
        f"| проходит автоматом | {len(clean)} | {len(clean) / n:.3f} |", "",
        f"Только полоса: {', '.join(band_only) or '—'}",
        f"Только повторы: {', '.join(repeat_only) or '—'}",
        f"Оба: {', '.join(both) or '—'}",
    ]
    # Точность маршрутизации — направление, не доказательство: 14 меток заморожены как holdout,
    # и при 3 отправленных на review случайный выбор поймал бы в среднем 0.64 из 3 расхождений.
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    labels = labels.get("labels", labels)
    mismatch = {v.item_id for v in v2 if v.item_id in labels and v.verdict != labels[v.item_id]}
    review = {v.item_id for v in routed if v.verdict == routing.REVIEW_REQUIRED}
    expected_by_chance = len(review) * len(mismatch) / n
    lines += ["", "### Точность маршрутизации (14 меток владельца, holdout — только направление)", "",
              f"Расхождений судьи с метками: {len(mismatch)} ({', '.join(sorted(mismatch))}).",
              f"Из них отправлено на review: {len(review & mismatch)} из {len(mismatch)}; "
              f"случайный выбор {len(review)} из {n} поймал бы в среднем {expected_by_chance:.2f}.",
              "При n=14 это неотличимо от случайного — число записано как направление, не как результат."]

    text = "\n".join(lines)
    print(text)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "table.md").write_text(text + "\n", encoding="utf-8")
    (OUT_DIR / "routed.json").write_text(
        json.dumps([v.to_dict() for v in routed], ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
