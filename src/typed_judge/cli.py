"""tj — run / calibrate / variants / report."""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import pathlib
import sys

from . import batch, blind_duplicates, calibrate, claim_check, diffing, mqm, report, routing
from .engines.fake import FakeEngine
from .verdict import HUMAN, Verdict, apply


def load_recipe(spec: str):
    if spec.endswith(".py"):
        s = importlib.util.spec_from_file_location("recipe", spec)
        mod = importlib.util.module_from_spec(s)
        s.loader.exec_module(mod)
    else:
        mod = importlib.import_module(spec)
    for attr in ("QUESTIONS", "combine"):
        if not hasattr(mod, attr):
            raise SystemExit(f"рецепт {spec}: нет {attr}")
    return mod


def make_engine(name: str):
    kind, _, model = name.partition(":")
    if kind == "fake":
        return FakeEngine()
    if kind == "typesafe":
        from .engines.typesafe import TypeSafeEngine
        return TypeSafeEngine(model=model or "jev-latest")
    if kind == "gemini":
        from .engines.gemini import GeminiEngine
        return GeminiEngine(model=model or "gemini-3.5-flash-lite")
    raise SystemExit(f"неизвестный движок: {name} (fake | typesafe[:model] | gemini[:model])")


def load_items(paths: list[str]) -> dict[str, str]:
    items = {}
    for p in paths:
        path = pathlib.Path(p)
        text = path.read_text(encoding="utf-8")
        if text.startswith("---"):
            text = text.split("---", 2)[-1].strip()
        items[path.stem] = text
    return items


def _write_verdicts(path: pathlib.Path, verdicts: list[Verdict]) -> None:
    path.write_text("".join(json.dumps(v.to_dict(), ensure_ascii=False) + "\n" for v in verdicts), encoding="utf-8")


def _exit_code(verdicts: list[Verdict]) -> int:
    # review_required — тоже не «прошло»: пограничное, ушедшее человеку, не должно молча проехать в CI.
    return 1 if any(v.verdict in (HUMAN, routing.REVIEW_REQUIRED) or v.error for v in verdicts) else 0


def claim_states(recipe, items: dict[str, str], sources_dir: str | None) -> dict[str, str]:
    """Источник к черновику — <sources_dir>/<item_id>.md. Нет каталога, нет файла или нет
    CLAIM_QUESTIONS у рецепта — шага не будет: молчание источника вердикт не понижает."""
    if not (sources_dir and getattr(recipe, "CLAIM_QUESTIONS", None)):
        return {}
    root = pathlib.Path(sources_dir)
    states = {}
    for item_id, draft in items.items():
        path = root / f"{item_id}.md"
        if path.exists():
            (source,) = load_items([str(path)]).values()
            states[item_id] = claim_check.state_for(draft=draft, source=source)
    return states


def route_verdicts(recipe, rows: list[batch.Row], verdicts: list[Verdict]) -> list[Verdict]:
    """Пограничное — человеку (routing, бид qei). Рецепт без margins() маршрутизировать нечем:
    расстояния до границ знает он, а не CLI, поэтому вердикты возвращаются как есть."""
    if not hasattr(recipe, "margins"):
        return verdicts
    answers = {r.item_id: r.answers for r in rows}
    # score is None — вердикт уже human; margins по неполным ответам считать нечем, route() и так
    # отправит такой item на review.
    return [routing.route(v, margins=recipe.margins(answers[v.item_id], v.score)
                          if v.score is not None else {}) for v in verdicts]


def cmd_run(a) -> int:
    recipe, engine = load_recipe(a.recipe), make_engine(a.engine)
    cache = pathlib.Path(a.cache)
    items = load_items(a.files)
    rows = batch.run(engine, items, recipe.QUESTIONS, cache)
    # Второй шаг идёт в тот же кэш отдельными строками (ключ включает набор вопросов);
    # apply группирует по item_id, так что на черновик остаётся один вердикт.
    states = claim_states(recipe, items, a.sources)
    claim_rows = batch.run(engine, states, recipe.CLAIM_QUESTIONS, cache) if states else []
    verdicts = apply(rows + claim_rows, recipe.combine)
    if a.route:
        verdicts = route_verdicts(recipe, rows, verdicts)
    _write_verdicts(pathlib.Path(a.out) if a.out else cache.parent / "verdicts.jsonl", verdicts)
    print(report.markdown(rows, verdicts))
    return _exit_code(verdicts)


def cmd_calibrate(a) -> int:
    recipe = load_recipe(a.recipe)
    rows = batch.read_rows(pathlib.Path(a.cache))
    verdicts = apply(rows, recipe.combine)
    raw = json.loads(pathlib.Path(a.labels).read_text(encoding="utf-8"))
    # mqm.plain_verdicts — читает и старую форму метки (строка), и новую (verdict+category, DR-62 §1.6)
    calib_labels, holdout_labels = calibrate.split_holdout(mqm.plain_verdicts(raw.get("labels", {})),
                                                             raw.get("holdout", []))
    positive = getattr(recipe, "LABEL_POSITIVE", "ready")
    t = calibrate.fit_thresholds(verdicts, calib_labels, positive=positive)
    rater_pairs = blind_duplicates.rater_pairs_from_doc(raw) or None
    print(calibrate.report_text(verdicts, calib_labels, holdout_labels, t, rater_pairs=rater_pairs))
    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(t.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def cmd_diff_published(a) -> int:
    print(diffing.published_report(pathlib.Path(a.vault_root)))
    return 0


def cmd_variants(a) -> int:
    recipe, engine = load_recipe(a.recipe), make_engine(a.engine)
    variants = getattr(recipe, "VARIANTS", {"default": recipe.QUESTIONS})
    combines = getattr(recipe, "COMBINES", {})
    items = load_items([a.file])
    print("| variant | verdict | score |", "|---|---|---|", sep="\n")
    for name, qs in variants.items():
        rows = batch.run(engine, items, qs, pathlib.Path(a.cache))
        (v,) = apply(rows, combines.get(name, recipe.combine))
        print(f"| {name} | {v.verdict} | {'' if v.score is None else v.score} |")
    return 0


def cmd_report(a) -> int:
    recipe = load_recipe(a.recipe)
    if a.compare:
        va = apply(batch.read_rows(pathlib.Path(a.compare[0])), recipe.combine)
        vb = apply(batch.read_rows(pathlib.Path(a.compare[1])), recipe.combine)
        print(report.compare(va, vb))
        return 0
    rows = batch.read_rows(pathlib.Path(a.cache))
    print(report.markdown(rows, apply(rows, recipe.combine)))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tj", description="типизированные вопросы к модели, вердикт в коде, пороги по меткам")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="прогнать items через движок с кэшем и посчитать вердикты")
    r.add_argument("--recipe", required=True); r.add_argument("--engine", default="fake")
    r.add_argument("--cache", required=True); r.add_argument("--out")
    r.add_argument("--sources", help="каталог с источниками: <DIR>/<item_id>.md — включает шаг claim-vs-evidence")
    r.add_argument("--route", action="store_true",
                   help="пограничное (полоса вокруг границ рецепта) уводить в review_required, exit 1")
    r.add_argument("files", nargs="+")
    r.set_defaults(fn=cmd_run)

    c = sub.add_parser("calibrate", help="сверить вердикты по кэшу с метками и подобрать пороги")
    c.add_argument("--recipe", required=True); c.add_argument("--cache", required=True)
    c.add_argument("--labels", required=True); c.add_argument("--out")
    c.set_defaults(fn=cmd_calibrate)

    d = sub.add_parser("diff-published", help="дифф черновик↔опубликованная версия по vault, отчёт стиль/факт")
    d.add_argument("--vault-root", required=True)
    d.set_defaults(fn=cmd_diff_published)

    v = sub.add_parser("variants", help="один item, несколько формулировок — таблица вердиктов")
    v.add_argument("--recipe", required=True); v.add_argument("--engine", default="fake")
    v.add_argument("--cache", required=True); v.add_argument("file")
    v.set_defaults(fn=cmd_variants)

    p = sub.add_parser("report", help="markdown по кэшу или сравнение двух кэшей")
    p.add_argument("--recipe", required=True)
    pg = p.add_mutually_exclusive_group(required=True)
    pg.add_argument("--cache"); pg.add_argument("--compare", nargs=2)
    p.set_defaults(fn=cmd_report)

    try:
        a = ap.parse_args(argv)
        return a.fn(a)
    except SystemExit as e:
        if isinstance(e.code, str):  # int-код (argparse) уже сопровождён его собственным сообщением
            print(e, file=sys.stderr)
        return 2 if isinstance(e.code, str) else int(e.code or 0)
    except (ImportError, OSError) as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
