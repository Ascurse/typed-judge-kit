"""bd typed-judge-kit-q36: прогон claim-vs-evidence на стресс-наборе h37.

Источник для критической фикстуры — её парный base-текст: они отличаются ровно одной подменой
факта (дата, имя, число, инверсия «не», абсурд), значит противоречие в паре заведомо есть и
детектируемо. Отрицательный класс — base против самого себя: проверка не должна срабатывать там,
где подмены нет. Решение владельца 2026-09-20.

Границы этого замера: источник синтетический и почти дословно совпадает с черновиком. На реальных
рабочих заметках (короче, другими словами, с лишним) задача строго труднее — число отсюда
переносить на продакшн нельзя.

Запуск:
  uv run python scripts/claim_check_run.py [--smoke] [--cache <path>]
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from typed_judge import batch, claim_check
from typed_judge.engines.typesafe import TypeSafeEngine, cost_usd

FIXTURES = pathlib.Path(__file__).parent.parent / "tests/fixtures/stress/fixtures.json"
DEFAULT_CACHE = pathlib.Path(__file__).parent.parent / "tests/fixtures/stress/claim_check_cache.jsonl"
OUT_DIR = pathlib.Path(
    "/Users/ascurse/Documents/ObsidianSecondBrain/Projects/typed-judge-kit/Outputs/"
    "2026-09-20-claim-check-q36"
)
THRESHOLD = 0.5


def pairs(data: dict) -> list[tuple[str, str, str, str]]:
    """(item_id, kind|defect_type, draft, source). Источник критической фикстуры — её base."""
    by_id = {it["id"]: it for it in data["items"]}
    out = []
    for it in data["items"]:
        if it["kind"] == "critical":
            out.append((it["id"], it["defect_type"], it["text"], by_id[it["base_id"]]["text"]))
        elif it["kind"] == "base":
            out.append((it["id"], "base", it["text"], it["text"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true", help="4 фикстуры — прикинуть стоимость")
    ap.add_argument("--cache", type=pathlib.Path, default=DEFAULT_CACHE)
    a = ap.parse_args()

    data = json.loads(FIXTURES.read_text(encoding="utf-8"))
    rows_in = pairs(data)
    if a.smoke:
        rows_in = rows_in[:3] + [r for r in rows_in if r[1] == "base"][:1]

    engine = TypeSafeEngine()
    results, cost, errs = {}, 0.0, []
    claims_by_item = {}
    for item_id, kind, draft, source in rows_in:
        claims = claim_check.extract_claims(draft)
        claims_by_item[item_id] = claims
        if not claims:
            results[item_id] = (kind, [], {})
            continue
        qs = claim_check.questions_for(claims)
        state = claim_check.state_for(draft=draft, source=source)
        rows = batch.run(engine, {item_id: state}, qs, a.cache)
        r = rows[0]
        cost += cost_usd(r.input_tokens)
        if r.error:
            errs.append(f"{item_id}: {r.error}")
        errs += [f"{item_id}/{q}: {ans.error}" for q, ans in r.answers.items() if ans.error]
        results[item_id] = (kind, claims, r.answers)

    print(f"фикстур: {len(rows_in)}, ошибок: {len(errs)}, стоимость: ${cost:.5f}")
    for e in errs[:20]:
        print("ERROR", e)

    fired = {"contradicts": {}, "supported": {}, "holistic": {}}
    for item_id, (kind, claims, answers) in results.items():
        for ph in ("contradicts", "supported"):
            fired[ph][item_id] = bool(
                claim_check.unsupported(answers, len(claims), threshold=THRESHOLD, phrasing=ph))
        h = answers.get(claim_check.HOLISTIC_QID)
        fired["holistic"][item_id] = bool(h and not h.error and h.probability is not None
                                          and h.probability >= THRESHOLD)

    crit = [i for i, (k, _, _) in results.items() if k != "base"]
    base = [i for i, (k, _, _) in results.items() if k == "base"]
    lines = [f"### claim-vs-evidence на h37 (порог {THRESHOLD}, источник — парный base-текст)", "",
             "| способ | ловит critical (n) | ложно срабатывает на base (n) | separation |",
             "|---|---|---|---|"]
    for ph, label in (("contradicts", "по утверждениям, дефектная формулировка"),
                      ("supported", "по утверждениям, положительная формулировка"),
                      ("holistic", "один целостный вопрос (контроль без разбиения)")):
        c = sum(fired[ph][i] for i in crit) / len(crit) if crit else 0.0
        b = sum(fired[ph][i] for i in base) / len(base) if base else 0.0
        lines.append(f"| {label} | {c:.3f} ({len(crit)}) | {b:.3f} ({len(base)}) | {c - b:.3f} |")

    by_type: dict[str, list[bool]] = collections.defaultdict(list)
    for item_id, (kind, _, _) in results.items():
        if kind != "base":
            by_type[kind].append(fired["contradicts"][item_id])
    lines += ["", "### По типам дефекта (дефектная формулировка)", "",
              "| тип дефекта | поймано | всего |", "|---|---|---|"]
    for t, v in sorted(by_type.items()):
        lines.append(f"| {t} | {sum(v)} | {len(v)} |")
    lines += ["", f"Утверждений на черновик: медиана "
                  f"{sorted(len(c) for c in claims_by_item.values())[len(claims_by_item) // 2]}, "
                  f"без утверждений: {sum(1 for c in claims_by_item.values() if not c)}"]

    text = "\n".join(lines)
    print(text)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "table.md").write_text(text + "\n", encoding="utf-8")
    (OUT_DIR / "cost.json").write_text(json.dumps({"cost_usd": cost, "n": len(rows_in)}, indent=1),
                                       encoding="utf-8")
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
