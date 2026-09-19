"""bd typed-judge-kit-zin: прогон draft_lint_v3 на 14 черновиках + не-подгоночная оценка
согласия с метками (LOOCV + permutation test + flip-rate, протокол DR-63).

Кэш v3 — отдельный от v2 (Outputs/2026-09-20-run-typesafe-v3/), чтобы `tj calibrate` и
дальнейшие сверки не смешивали строки двух рецептов (см. draft_lint_v2 note о том же).
3 независимых повтора (rep1/rep2/rep3, отдельные jsonl-файлы — иначе кэш второго и
третьего повтора читал бы первый, а не звал модель заново) нужны для flip-rate.

Пункт 3 бида ("чистое тело поста, без «пакета с секциями»"): черновики в VAULT_DRAFTS —
publish-пакеты (Source material с заметками + English version + Russian adaptation +
Platform adaptations + Pre-publish check одним файлом). contamination.py (3jk) для
сравнения режимов батчинга специально брал весь пакет как есть (там сравнивались режимы
подачи вопросов, не формат state) — здесь, наоборот, важно скормить модели только
реальный текст поста. load_items() ниже вырезает секцию версии по primary_language
из front-matter (English version / Ответ (RU) — фиксированный список маркеров, задан
до прогона по факту разметки черновиков, не подбирался по результату); нет маркера —
пакета в файле и не было, весь текст уже чистое тело (see second-brain-eval-substack —
известное ограничение: EN+RU без секции-маркера, фолбэк берёт оба языка подряд).

Запуск:
  uv run python scripts/run_draft_lint_v3.py --smoke    # 1 черновик × 3 повтора, оценка стоимости
  uv run python scripts/run_draft_lint_v3.py --full      # 14 × 3; бюджет $1 проверяется перед стартом
  uv run python scripts/run_draft_lint_v3.py --analyze   # пересчёт по уже накопленным кэшам, без новых вызовов
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from typed_judge import batch, calibrate, validate  # noqa: E402
from typed_judge.engines.typesafe import TypeSafeEngine, cost_usd  # noqa: E402
from typed_judge.recipes import draft_lint_v2, draft_lint_v3  # noqa: E402
from typed_judge.verdict import apply  # noqa: E402

# тот же список 14 id, что в contamination.py (3jk) и исходном прогоне v2 — не дублируем.
from contamination import ITEM_IDS, VAULT_DRAFTS  # noqa: E402

OUT_DIR = pathlib.Path("/Users/ascurse/Documents/ObsidianSecondBrain/Projects/typed-judge-kit/Outputs/2026-09-20-run-typesafe-v3")
V2_CACHE = pathlib.Path("/Users/ascurse/Documents/ObsidianSecondBrain/Projects/typed-judge-kit/Outputs/2026-09-20-run-typesafe-v2.jsonl")
LABELS_PATH = pathlib.Path("/Users/ascurse/Documents/ObsidianSecondBrain/Projects/typed-judge-kit/Inputs/labels.json")
BUDGET_USD = 1.0
REPS = (1, 2, 3)

# фиксированный список маркеров секции — выбран до прогона, по факту разметки черновиков
# (front-matter primary_language: en|ru), не подбирался по результату оценки согласия.
_LANGUAGE_SECTION_MARKERS = {
    "en": ("## English version", "## English Version", "## English"),
    "ru": ("## Русская версия", "## Russian version", "## Ответ (RU) — для треда"),
}


def _split_front_matter(raw: str) -> tuple[str, str]:
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        return raw[3:end], raw[end + 4:].strip()
    return "", raw.strip()


def _primary_language_of(front_matter: str) -> str:
    for line in front_matter.splitlines():
        if line.strip().startswith("primary_language:"):
            return line.split(":", 1)[1].strip()
    return "en"


def extract_clean_body(text: str, primary_language: str) -> str:
    """Чистое тело поста (п.3 бида): секция версии primary_language из publish-пакета
    (Source material + English version + Russian adaptation + Platform adaptations +
    Pre-publish check в одном файле), а не весь пакет. Нет маркера секции — пакета не
    было, весь текст уже чистое тело (fallback; second-brain-eval-substack — известное
    ограничение: EN+RU без секции-маркера, фолбэк отдаёт оба языка подряд)."""
    for marker in _LANGUAGE_SECTION_MARKERS.get(primary_language, ()):
        i = text.find(marker)
        if i < 0:
            continue
        rest = text[i + len(marker):]
        j = rest.find("\n## ")
        return (rest[:j] if j >= 0 else rest).strip()
    return text.strip()


def load_items(item_ids: list[str]) -> dict[str, str]:
    out = {}
    for item_id in item_ids:
        raw = (VAULT_DRAFTS / f"{item_id}.md").read_text(encoding="utf-8")
        front_matter, body = _split_front_matter(raw)
        out[item_id] = extract_clean_body(body, _primary_language_of(front_matter))
    return out


def run_rep(rep: int, engine, items: dict[str, str]) -> list[batch.Row]:
    cache = OUT_DIR / f"rep{rep}.jsonl"
    return batch.run(engine, items, draft_lint_v3.QUESTIONS, cache)


def collect(item_ids: list[str], reps: tuple[int, ...]) -> dict[int, list[batch.Row]]:
    items = load_items(item_ids)
    engine = TypeSafeEngine()
    return {rep: run_rep(rep, engine, items) for rep in reps}


def errors_of(rows_by_rep: dict[int, list[batch.Row]]) -> list[str]:
    out = []
    for rep, rows in rows_by_rep.items():
        for row in rows:
            if row.error:
                out.append(f"rep{rep}/{row.item_id}: строка — {row.error}")
            for qid, ans in row.answers.items():
                if ans.error:
                    out.append(f"rep{rep}/{row.item_id}: {qid} — {ans.error}")
    return out


def total_cost(rows_by_rep: dict[int, list[batch.Row]]) -> float:
    return cost_usd(sum(r.input_tokens for rows in rows_by_rep.values() for r in rows))


def load_labels() -> tuple[dict[str, str], list[str]]:
    raw = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    return raw["labels"], raw.get("holdout", [])


def v2_agreement(labels: dict[str, str]) -> tuple[int, int]:
    rows = batch.read_rows(V2_CACHE)
    verdicts = apply(rows, draft_lint_v2.combine)
    return calibrate.agreement(verdicts, labels)


def analyze(rows_by_rep: dict[int, list[batch.Row]]) -> dict:
    labels, holdout = load_labels()
    verdicts_by_rep = {rep: apply(rows, draft_lint_v3.combine) for rep, rows in rows_by_rep.items()}
    primary = verdicts_by_rep[REPS[0]]

    k, n = calibrate.agreement(primary, labels)

    answers_by_item = {r.item_id: r.answers for r in rows_by_rep[REPS[0]]}
    item_ids = [r.item_id for r in rows_by_rep[REPS[0]]]
    loo_k, loo_n = validate.loocv_agreement(
        item_ids, lambda train_ids: draft_lint_v3.combine, answers_by_item, labels, positive="ready"
    )
    observed, p_value = validate.permutation_test(primary, labels, n_perm=1000, seed=0)

    reps_verdict_maps = [{v.item_id: v for v in vs} for vs in verdicts_by_rep.values()]
    fr = validate.flip_rate(reps_verdict_maps)

    v2_k, v2_n = v2_agreement(labels)

    return {
        "v3_agreement": {"k": k, "n": n},
        "v3_loocv_agreement": {"k": loo_k, "n": loo_n},
        "v3_permutation_test": {"observed": observed, "p_value": p_value, "n_perm": 1000},
        "v3_flip_rate_over_3_reps": fr,
        "v2_agreement_same_labels": {"k": v2_k, "n": v2_n},
        "note": "те же 14 меток, что и в v2/DR-62 holdout — проверка направления, не доказательство",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--smoke", action="store_true")
    g.add_argument("--full", action="store_true")
    g.add_argument("--analyze", action="store_true")
    ap.add_argument("--out", help="каталог кэша; по умолчанию OUT_DIR замера zin")
    a = ap.parse_args()

    global OUT_DIR
    if a.out:
        OUT_DIR = pathlib.Path(a.out)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    item_ids = ITEM_IDS[:1] if a.smoke else ITEM_IDS
    reps = (1,) if a.smoke else REPS

    if a.analyze:
        rows_by_rep = {rep: batch.read_rows(OUT_DIR / f"rep{rep}.jsonl") for rep in REPS}
        summary = analyze(rows_by_rep)
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

    rows_by_rep = collect(item_ids, reps)
    errs = errors_of(rows_by_rep)
    cost = total_cost(rows_by_rep)
    print(f"строк: {sum(len(v) for v in rows_by_rep.values())}, ошибок: {len(errs)}, стоимость: ${cost:.4f}")
    for e in errs[:20]:
        print("ERROR", e)

    if a.smoke:
        n_smoke, n_full = len(item_ids), len(ITEM_IDS)
        est_full = cost * (n_full / max(n_smoke, 1)) * (len(REPS) / max(len(reps), 1))
        (OUT_DIR / "smoke_summary.json").write_text(json.dumps({
            "errors": errs, "smoke_cost_usd": cost, "estimated_full_cost_usd": est_full,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"оценка полного прогона (14×3): ${est_full:.4f}")

    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
