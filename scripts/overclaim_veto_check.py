"""bd typed-judge-kit-ov0: что делает срабатывание overclaim на фикстурах h37.

Считает по уже накопленному кэшу прогона question_calibration.py --full — новых вызовов
модели не делает. Проверяет ровно то, ради чего заведён бид: сколько раз порог срабатывает
на фикстурах БЕЗ дефекта и во что это срабатывание превращает вердикт.

Бид k55 добавил положительный класс (kind "overclaim" — base-текст с дописанным перегибом),
поэтому здесь же печатается сравнение порогов на обоих классах, а не только ложные срабатывания.

Кэш накапливается append-ом и хранит строки от РАЗНЫХ наборов вопросов (набор менялся в 08p).
Строки отбираются по cache_key текущего draft_lint_v3.QUESTIONS, а не по порядку в файле:
иначе достаточно дописать в файл старый прогон, чтобы проверка молча поехала.

Запуск:
  uv run python scripts/overclaim_veto_check.py
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from typed_judge.batch import cache_key  # noqa: E402
from typed_judge.questions import Answer  # noqa: E402
from typed_judge.recipes.draft_lint_v3 import (  # noqa: E402
    CRITICAL_DEFECTS,
    HEAVY_EDIT_AT,
    LIGHT_EDIT_AT,
    OVERCLAIM_THRESHOLD,
    QUESTIONS,
    STYLE_DEFECTS,
    combine,
)

CACHE = pathlib.Path(
    "/Users/ascurse/Documents/ObsidianSecondBrain/Projects/typed-judge-kit/Outputs/"
    "2026-09-20-question-calibration-v3/cache.jsonl"
)
FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "tests/fixtures/stress/fixtures.json"
ENGINE = "typesafe:jev-latest"
# base/ru_clean — фикстуры без подсаженного дефекта: срабатывание здесь заведомо ложное.
# critical — подменён факт, но не сила утверждения; прямой истины по overclaim там нет.
CLEAN_KINDS = ("base", "ru_clean")
POSITIVE_KIND = "overclaim"   # бид k55: base-текст + дописанный вывод сильнее данных
NEGATIVE_KIND = "base"        # тот же текст без дописанного вывода


def _style_only(a: dict[str, Answer]) -> str:
    """Вердикт по одной стилистике — база, с которой сравнивается эффект overclaim."""
    d = sum(a[q].probability >= 0.5 for q in STYLE_DEFECTS)
    return "heavy_edit" if d >= HEAVY_EDIT_AT else "light_edit" if d >= LIGHT_EDIT_AT else "ready"


def main() -> int:
    if not CACHE.exists():
        print(f"нет кэша {CACHE} — сначала scripts/question_calibration.py --full", file=sys.stderr)
        return 1
    items = json.loads(FIXTURES.read_text(encoding="utf-8"))["items"]
    kinds = {it["id"]: it["kind"] for it in items}
    want = {it["id"]: cache_key(ENGINE, it["text"], QUESTIONS) for it in items}
    answers = {
        r["item_id"]: {q: Answer.from_dict(v) for q, v in r["answers"].items()}
        for r in map(json.loads, CACHE.read_text(encoding="utf-8").splitlines())
        if want.get(r["item_id"]) == r["key"]
    }
    missing = sorted(set(want) - set(answers))
    if missing:
        print(f"в кэше нет строк под текущий набор вопросов для {len(missing)} фикстур: "
              f"{missing[:5]}... — прогони scripts/question_calibration.py --full", file=sys.stderr)
        return 1
    crit = CRITICAL_DEFECTS[0]
    print(f"фикстур в кэше: {len(answers)}, порог {crit}: {OVERCLAIM_THRESHOLD}\n")

    print("| класс | n | p>=порога | max p | mean p |")
    print("|---|---|---|---|---|")
    for k in ("base", "ru_clean", "ru_messy", "critical"):
        ps = [answers[i][crit].probability for i in answers if kinds.get(i) == k]
        if ps:
            print(f"| {k} | {len(ps)} | {sum(p >= OVERCLAIM_THRESHOLD for p in ps)} | "
                  f"{max(ps):.2f} | {sum(ps) / len(ps):.3f} |")

    clean = [i for i in answers if kinds.get(i) in CLEAN_KINDS]
    pos = [i for i in answers if kinds.get(i) == POSITIVE_KIND]
    neg = [i for i in answers if kinds.get(i) == NEGATIVE_KIND]
    print(f"\nпороги: {POSITIVE_KIND} (n={len(pos)}) против {NEGATIVE_KIND} (n={len(neg)}) — "
          f"минимальные пары, бид k55; отдельно ложные срабатывания на всех фикстурах без "
          f"дефекта ({'+'.join(CLEAN_KINDS)}, n={len(clean)})")
    print(f"  {'порог':>6} | {POSITIVE_KIND:>10} | {NEGATIVE_KIND:>6} | separation | ложные на чистых")
    for thr in (0.5, 0.7, OVERCLAIM_THRESHOLD, 0.8, 0.9):
        pr = sum(answers[i][crit].probability >= thr for i in pos) / len(pos) if pos else None
        nr = sum(answers[i][crit].probability >= thr for i in neg) / len(neg) if neg else None
        sep = "-" if pr is None or nr is None else f"{pr - nr:10.3f}"
        fp = sorted(i for i in clean if answers[i][crit].probability >= thr)
        print(f"  {thr:6.2f} | {pr:10.3f} | {nr:6.3f} | {sep} | {len(fp)}/{len(clean)} {fp}")

    print("\nвердикты на всех фикстурах:")
    print(f"  только стилистика:   {dict(collections.Counter(_style_only(answers[i]) for i in answers))}")
    print(f"  с учётом {crit}: {dict(collections.Counter(combine(answers[i])[1] for i in answers))}")

    moved = [i for i in sorted(answers) if combine(answers[i])[1] != _style_only(answers[i])]
    print(f"\nсрабатывание сдвинуло вердикт у {len(moved)} фикстур:")
    for i in moved:
        print(f"  {i:34s} {kinds.get(i):9s} p={answers[i][crit].probability:.2f}  "
              f"{_style_only(answers[i])} -> {combine(answers[i])[1]}")

    bad = [i for i in moved if combine(answers[i])[1] == "heavy_edit"]
    print(f"\nсрабатываний, поднявших вердикт до heavy_edit: {len(bad)} {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
