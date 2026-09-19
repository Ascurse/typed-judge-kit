"""bd typed-judge-kit-5h1: работает ли Jev хуже на русском, чем на английском?

Черновики в VAULT_DRAFTS — publish-пакеты, где автор своими руками написал ОДНО и ТО ЖЕ
содержание на английском ("## English version"/"## EN variant...") и на русском
("## Russian adaptation"/"## Русская версия"/"## Ответ (RU) — для треда"). Параллельный
человеческий корпус — машинный перевод НЕ используется нигде в этом замере.

find_pairs() переиспользует extract_clean_body() из run_draft_lint_v3.py (тот же способ
резки publish-пакета на секцию версии, что и в основном прогоне v3) — просто вызывает его
дважды на один файл (language="en", language="ru") вместо одного раза по primary_language.
Маркер-таблица расширена (EXTRA_EN_MARKERS/EXTRA_RU_MARKERS) двумя заголовками, которых нет
в исходном списке v3 ("## Russian adaptation" — самый частый RU-заголовок в этих черновиках;
"## EN variant..." — заголовок одного конкретного черновика-ответа в тред) — это те же
данные-маркеры, что и в оригинале, без новой логики резки.

3 повтора на КАЖДОЙ языковой версии (не 1) — нужны, чтобы посчитать внутриязыковой шум
на этих же данных (см. vault-заметка 2026-09-20 "Контаминация..." — N=0.081 из 10 вопросов
на другом наборе вопросов, здесь считаем свой N на 13 вопросах v3).

Запуск:
  uv run python scripts/run_ru_vs_en.py --pairs    # только найти пары EN/RU, без сети
  uv run python scripts/run_ru_vs_en.py --smoke    # 1 пара × 3 повтора × 2 языка, оценка стоимости
  uv run python scripts/run_ru_vs_en.py --full     # все пары; бюджет $1 проверяется перед стартом
  uv run python scripts/run_ru_vs_en.py --analyze  # пересчёт по уже накопленным кэшам, без новых вызовов
"""
from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

# scripts/run_draft_lint_v3.py лежит в этом же каталоге — тот же приём, что и у него самого
# (`from contamination import ITEM_IDS, VAULT_DRAFTS`): каталог скрипта уже на sys.path[0].
from run_draft_lint_v3 import (
    _LANGUAGE_SECTION_MARKERS,
    _split_front_matter,
    extract_clean_body,
)

from typed_judge import batch
from typed_judge.contamination import hamming
from typed_judge.engines.typesafe import TypeSafeEngine, cost_usd
from typed_judge.lang_compare import dp_by_question
from typed_judge.recipes.draft_lint_v3 import QUESTIONS, combine
from typed_judge.verdict import apply

VAULT_DRAFTS = pathlib.Path("/Users/ascurse/Documents/ObsidianSecondBrain/output/Content/drafts")
OUT_DIR = pathlib.Path("/Users/ascurse/Documents/ObsidianSecondBrain/Projects/typed-judge-kit/Outputs/2026-09-20-ru-vs-en")
BUDGET_USD = 1.0
REPS = (1, 2, 3)
LANGS = ("en", "ru")
EXCLUDED = {"README", "post-template-lesson-progress-tradeoff"}

# Расширение маркер-таблицы v3 (не подмена): "## Russian adaptation" — заголовок RU-секции
# в большинстве черновиков (v3-список знал только "Русская версия"/"Ответ (RU) — для треда",
# т.к. основной прогон v3 вообще не заглядывал в RU-секцию для primary_language=en файлов).
# "## EN variant..." — заголовок EN-секции одного конкретного черновика (ответ в тред,
# структура "часть 1/часть 2" в RU vs связный текст в EN — контентно то же, форматно нет,
# см. заметку по этому черновику в замере).
EXTRA_EN_MARKERS = ("## EN variant (standalone — X long / LinkedIn)",)
EXTRA_RU_MARKERS = ("## Russian adaptation",)
_LANGUAGE_SECTION_MARKERS["en"] = _LANGUAGE_SECTION_MARKERS["en"] + EXTRA_EN_MARKERS
_LANGUAGE_SECTION_MARKERS["ru"] = _LANGUAGE_SECTION_MARKERS["ru"] + EXTRA_RU_MARKERS


def _has_section(body: str, language: str) -> bool:
    return any(m in body for m in _LANGUAGE_SECTION_MARKERS[language])


def find_pairs(vault_dir: pathlib.Path) -> dict[str, dict[str, str]]:
    """item_id -> {"en": текст, "ru": текст} для черновиков, где ОБЕ секции найдены и непусты.

    Не пара (пропускается): нет ни одного маркера языка (текст не разбит на EN/RU секции
    известным заголовком) или секция после резки пустая."""
    pairs: dict[str, dict[str, str]] = {}
    for path in sorted(vault_dir.glob("*.md")):
        if path.stem in EXCLUDED:
            continue
        raw = path.read_text(encoding="utf-8")
        _, body = _split_front_matter(raw)
        texts = {}
        for lang in LANGS:
            texts[lang] = extract_clean_body(body, lang).strip() if _has_section(body, lang) else ""
        if texts["en"] and texts["ru"]:
            pairs[path.stem] = texts
    return pairs


def run_lang_rep(lang: str, rep: int, engine, items: dict[str, str]) -> list[batch.Row]:
    cache = OUT_DIR / f"{lang}_rep{rep}.jsonl"
    return batch.run(engine, items, QUESTIONS, cache)


def collect(pairs: dict[str, dict[str, str]], reps: tuple[int, ...]) -> dict[tuple[str, int], dict[str, batch.Row]]:
    engine = TypeSafeEngine()
    out: dict[tuple[str, int], dict[str, batch.Row]] = {}
    for lang in LANGS:
        items = {item_id: texts[lang] for item_id, texts in pairs.items()}
        for rep in reps:
            rows = run_lang_rep(lang, rep, engine, items)
            out[(lang, rep)] = {r.item_id: r for r in rows}
    return out


def errors_of(data: dict[tuple[str, int], dict[str, batch.Row]]) -> list[str]:
    out = []
    for (lang, rep), rows in data.items():
        for item_id, row in rows.items():
            if row.error:
                out.append(f"{lang}/rep{rep}/{item_id}: строка — {row.error}")
            for qid, ans in row.answers.items():
                if ans.error:
                    out.append(f"{lang}/rep{rep}/{item_id}: {qid} — {ans.error}")
    return out


def total_cost(data: dict[tuple[str, int], dict[str, batch.Row]]) -> float:
    return cost_usd(sum(r.input_tokens for rows in data.values() for r in rows.values()))


# Критерий предрегистрирован ДО полного прогона (та же операционализация, что уже
# проверена в замере "Контаминация..." 2026-09-20, bd 3jk — переиспользуем, не изобретаем
# заново): D>=N+1.0 И D>=1.5*N -> разница языков подтверждена; ровно одно условие -> слабый/
# неубедительный сигнал; ни одного -> разница не обнаружена (в пределах шума). N=0 (нулевой
# внутриязыковой шум) — множитель 1.5*0 тривиален, судит только D>=1.0.
def verdict_rule(inter: float, intra: float) -> str:
    if intra == 0:
        if inter >= 1.0:
            return "разница языков подтверждена"
        if inter > 0:
            return "слабый/неубедительный сигнал"
        return "разница языков не обнаружена (в пределах шума)"
    strong = inter >= intra + 1.0 and inter >= 1.5 * intra
    weak = inter >= intra + 1.0 or inter >= 1.5 * intra
    if strong:
        return "разница языков подтверждена"
    if weak:
        return "слабый/неубедительный сигнал"
    return "разница языков не обнаружена (в пределах шума)"


def hamming_stats(data: dict[tuple[str, int], dict[str, batch.Row]], item_ids: list[str],
                   reps: tuple[int, ...]) -> dict:
    inter_per_pair, intra_per_lang = {}, {"en": {}, "ru": {}}
    for item_id in item_ids:
        dists = []
        for r_en, r_ru in itertools.product(reps, reps):
            a = data[("en", r_en)][item_id].answers
            b = data[("ru", r_ru)][item_id].answers
            dists.append(hamming(a, b, QUESTIONS))
        inter_per_pair[item_id] = statistics.mean(dists)
        for lang in ("en", "ru"):
            d2 = [hamming(data[(lang, r1)][item_id].answers, data[(lang, r2)][item_id].answers, QUESTIONS)
                  for r1, r2 in itertools.combinations(reps, 2)]
            intra_per_lang[lang][item_id] = statistics.mean(d2) if d2 else 0.0
    inter_overall = statistics.mean(inter_per_pair.values())
    intra_en = statistics.mean(intra_per_lang["en"].values())
    intra_ru = statistics.mean(intra_per_lang["ru"].values())
    intra_overall = statistics.mean([intra_en, intra_ru])
    return {
        "inter_per_pair": inter_per_pair, "intra_per_pair": intra_per_lang,
        "inter_overall": inter_overall, "intra_en": intra_en, "intra_ru": intra_ru,
        "intra_overall": intra_overall, "verdict": verdict_rule(inter_overall, intra_overall),
    }


def dp_stats(data: dict[tuple[str, int], dict[str, batch.Row]], item_ids: list[str], reps: tuple[int, ...]) -> dict:
    per_item = {}
    for item_id in item_ids:
        en_reps = [data[("en", r)][item_id].answers for r in reps]
        ru_reps = [data[("ru", r)][item_id].answers for r in reps]
        per_item[item_id] = dp_by_question(en_reps, ru_reps, QUESTIONS)
    overall = {}
    for qid in QUESTIONS:
        vals = [per_item[i][qid] for i in item_ids if per_item[i][qid] is not None]
        overall[qid] = None if not vals else round(statistics.mean(vals), 4)
    return {"per_item": per_item, "overall": overall}


def verdict_disagreement(data: dict[tuple[str, int], dict[str, batch.Row]], item_ids: list[str]) -> dict:
    en_rows = [data[("en", REPS[0])][i] for i in item_ids]
    ru_rows = [data[("ru", REPS[0])][i] for i in item_ids]
    en_v = {v.item_id: v.verdict for v in apply(en_rows, combine)}
    ru_v = {v.item_id: v.verdict for v in apply(ru_rows, combine)}
    diffs = {i: {"en": en_v[i], "ru": ru_v[i]} for i in item_ids if en_v[i] != ru_v[i]}
    return {"n_pairs": len(item_ids), "n_disagree": len(diffs), "disagreements": diffs}


def analyze(pairs: dict[str, dict[str, str]], reps: tuple[int, ...] = REPS) -> dict:
    item_ids = sorted(pairs)
    data = {(lang, rep): {row.item_id: row for row in batch.read_rows(OUT_DIR / f"{lang}_rep{rep}.jsonl")}
            for lang in LANGS for rep in reps}
    # оставляем только пары, где есть данные во всех (lang, rep) срезах
    item_ids = [i for i in item_ids if all(i in data[(lang, rep)] for lang in LANGS for rep in reps)]
    return {
        "n_pairs": len(item_ids), "item_ids": item_ids,
        "hamming": hamming_stats(data, item_ids, reps),
        "dp_by_question": dp_stats(data, item_ids, reps),
        "verdict_disagreement": verdict_disagreement(data, item_ids),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pairs", action="store_true")
    g.add_argument("--smoke", action="store_true")
    g.add_argument("--full", action="store_true")
    g.add_argument("--analyze", action="store_true")
    a = ap.parse_args()

    pairs = find_pairs(VAULT_DRAFTS)

    if a.pairs:
        print(f"пар (EN и RU секции обе найдены и непусты): {len(pairs)}")
        for item_id in sorted(pairs):
            print(f"  {item_id}  (en={len(pairs[item_id]['en'])} симв., ru={len(pairs[item_id]['ru'])} симв.)")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if a.analyze:
        summary = analyze(pairs)
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        (OUT_DIR / "analysis.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        return 0

    if a.full:
        smoke_path = OUT_DIR / "smoke_summary.json"
        if smoke_path.exists():
            est = json.loads(smoke_path.read_text(encoding="utf-8"))["estimated_full_cost_usd"]
            if est > BUDGET_USD:
                print(f"оценка полного прогона ${est:.4f} > бюджета ${BUDGET_USD} — остановлено", file=sys.stderr)
                return 1

    run_pairs = dict(list(pairs.items())[:1]) if a.smoke else pairs
    run_reps = (1,) if a.smoke else REPS

    data = collect(run_pairs, run_reps)
    errs = errors_of(data)
    cost = total_cost(data)
    print(f"строк: {sum(len(v) for v in data.values())}, ошибок: {len(errs)}, стоимость: ${cost:.4f}")
    for e in errs[:20]:
        print("ERROR", e)

    if a.smoke:
        n_smoke, n_full = len(run_pairs), len(pairs)
        est_full = cost * (n_full / max(n_smoke, 1)) * (len(REPS) / max(len(run_reps), 1))
        (OUT_DIR / "smoke_summary.json").write_text(json.dumps({
            "n_pairs_total": n_full, "errors": errs, "smoke_cost_usd": cost, "estimated_full_cost_usd": est_full,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"оценка полного прогона ({n_full} пар × {len(REPS)} повтора × 2 языка): ${est_full:.4f}")

    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
