"""Прогон диагностического стресс-набора (bead typed-judge-kit-h37): draft_lint_v2 × tests/fixtures/stress/fixtures.json.

Правило auto-off и flip-rate считает typed_judge.stress — этот скрипт только собирает items, гоняет судью через
batch.run (кэш в jsonl) и печатает markdown-отчёт. Движок по умолчанию — typesafe:jev-latest, ключ через load_key(),
никогда не печатается.

Использование:
    uv run --extra dev python scripts/stress_bench.py --cache out/stress.jsonl [--smoke] [--engine typesafe:jev-latest]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from typed_judge import batch, report as tj_report, stress  # noqa: E402
from typed_judge.recipes import draft_lint_v2 as recipe  # noqa: E402
from typed_judge.verdict import apply  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent.parent / "tests/fixtures/stress/fixtures.json"


def load_fixtures() -> dict:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def make_engine(name: str):
    kind, _, model = name.partition(":")
    if kind == "fake":
        from typed_judge.engines.fake import FakeEngine
        return FakeEngine()
    if kind == "typesafe":
        from typed_judge.engines.typesafe import TypeSafeEngine
        return TypeSafeEngine(model=model or "jev-latest")
    raise SystemExit(f"неизвестный движок: {name}")


def ru_pairs(data: dict) -> list[tuple[str, str]]:
    by_pair: dict[str, dict[str, str]] = {}
    for it in data["items"]:
        if it["kind"] in ("ru_messy", "ru_clean"):
            by_pair.setdefault(it["pair"], {})[it["kind"]] = it["id"]
    return [(v["ru_messy"], v["ru_clean"]) for v in by_pair.values()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", required=True, help="jsonl-кэш ответов движка")
    ap.add_argument("--engine", default="typesafe:jev-latest")
    ap.add_argument("--smoke", action="store_true", help="только 2 фикстуры — прикинуть стоимость перед полным прогоном")
    ap.add_argument("--report", help="куда записать markdown-отчёт (по умолчанию — только stdout)")
    a = ap.parse_args(argv)

    data = load_fixtures()
    items = {it["id"]: it["text"] for it in data["items"]}
    if a.smoke:
        smoke_ids = ["base-01-inbox", "base-01-inbox-negation_flip"]
        items = {k: items[k] for k in smoke_ids}

    engine = make_engine(a.engine)
    cache_path = pathlib.Path(a.cache)
    rows = batch.run(engine, items, recipe.QUESTIONS, cache_path)
    verdicts = apply(rows, recipe.combine)

    lines = [tj_report.markdown(rows, verdicts)]

    if not a.smoke:
        critical_ids = {it["id"] for it in data["items"] if it["kind"] == "critical"}
        status = stress.auto_status(verdicts, critical_ids)
        fr = stress.flip_rate(ru_pairs(data), verdicts)
        lines.append("")
        lines.append(f"## auto-off по критическим дефектам\n\nстатус: **{status.status}**")
        if status.missed:
            lines.append("пропуски (критическая фикстура получила ready): " + ", ".join(status.missed))
        lines.append(f"\n## flip-rate RU-пар\n\nflip-rate: **{fr:.3f}** "
                      "(доля пар, где чистая правка оценена хуже канцелярита-исходника)")

    text = "\n".join(lines)
    print(text)
    if a.report:
        pathlib.Path(a.report).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
