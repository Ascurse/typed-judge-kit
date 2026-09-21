"""bd typed-judge-kit-sqd: claim_check на РЕАЛЬНЫХ черновиках с естественным источником.

Источник не синтезирован агентом: это секция «Source material» publish-пакета черновика
(output/Content/drafts/<id>.md) — рабочие заметки владельца, из которых пост писался.
Черновик — чистое тело поста (тот же extract_clean_body, что в run_draft_lint_v3).

Истины «где ошибка» здесь нет: посты опубликованы, подсаженных дефектов в них нет. Меряется
то, чего синтетический прогон q36 показать не мог — частота ЛОЖНЫХ срабатываний на настоящей
паре, где источник короче черновика, написан другими словами и покрывает не всё.

Запуск: uv run python scripts/claim_check_drafts.py
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from contamination import ITEM_IDS, VAULT_DRAFTS  # noqa: E402
from run_draft_lint_v3 import load_items  # noqa: E402

from typed_judge import batch, claim_check  # noqa: E402
from typed_judge.engines.typesafe import TypeSafeEngine, cost_usd  # noqa: E402

OUT_DIR = pathlib.Path("/Users/ascurse/Documents/ObsidianSecondBrain/Projects/typed-judge-kit/"
                       "Outputs/2026-09-21-claim-check-real-drafts-sqd")
CACHE = OUT_DIR / "cache.jsonl"
THRESHOLD = 0.5
_SECTION = re.compile(r"^#+\s*Source material.*$", re.M | re.I)
_NEXT_HEADING = re.compile(r"^#+\s+\S", re.M)


def source_note(item_id: str) -> str | None:
    """Секция «Source material» пакета черновика. Нет секции — пары нет, черновик пропускается."""
    path = VAULT_DRAFTS / f"{item_id}.md"
    if not path.exists():
        return None
    m = _SECTION.search(path.read_text(encoding="utf-8"))
    if not m:
        return None
    rest = path.read_text(encoding="utf-8")[m.end():]
    nxt = _NEXT_HEADING.search(rest)
    return (rest[:nxt.start()] if nxt else rest).strip() or None


def main() -> int:
    bodies = load_items(ITEM_IDS)
    pairs = [(i, bodies[i], s) for i in ITEM_IDS if (s := source_note(i))]
    print(f"пар черновик/источник: {len(pairs)} из {len(ITEM_IDS)}")

    engine, rows_out, cost, errs = TypeSafeEngine(), {}, 0.0, []
    for item_id, draft, source in pairs:
        claims = claim_check.extract_claims(draft)
        qs = claim_check.questions_for(claims)
        r = batch.run(engine, {item_id: claim_check.state_for(draft=draft, source=source)}, qs, CACHE)[0]
        cost += cost_usd(r.input_tokens)
        if r.error:
            errs.append(f"{item_id}: {r.error}")
        rows_out[item_id] = (claims, r.answers)
    print(f"стоимость: ${cost:.5f}, ошибок: {len(errs)}")
    for e in errs:
        print("ERROR", e)

    lines = [f"### claim_check на реальных парах черновик/Source material (порог {THRESHOLD})", "",
             "| черновик | утверждений | не подтверждено (дефектная) | не подтверждено (положительная) | целостный вопрос |",
             "|---|---|---|---|---|"]
    holistic_fired = 0
    for item_id, (claims, answers) in rows_out.items():
        bad_d = claim_check.unsupported(answers, len(claims), threshold=THRESHOLD)
        bad_s = claim_check.unsupported(answers, len(claims), threshold=THRESHOLD, phrasing="supported")
        h = answers.get(claim_check.HOLISTIC_QID)
        fired = bool(h and not h.error and h.probability is not None and h.probability >= THRESHOLD)
        holistic_fired += fired
        lines.append(f"| {item_id} | {len(claims)} | {len(bad_d)} | {len(bad_s)} | "
                     f"{'ДА' if fired else 'нет'} ({h.probability if h else '-'}) |")
    n = len(rows_out)
    tot_claims = sum(len(c) for c, _ in rows_out.values())
    tot_d = sum(len(claim_check.unsupported(a, len(c), threshold=THRESHOLD)) for c, a in rows_out.values())
    lines += ["", f"Целостный вопрос (тот, что ушёл в вето по q36) срабатывает на {holistic_fired} из {n} "
                  f"реальных черновиков без подсаженных ошибок — это ложные срабатывания: "
                  f"{holistic_fired / n:.3f}.",
              f"По утверждениям: не подтверждено {tot_d} из {tot_claims} ({tot_d / tot_claims:.3f})."]
    text = "\n".join(lines)
    print(text)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "table.md").write_text(text + "\n", encoding="utf-8")
    (OUT_DIR / "cost.json").write_text(json.dumps({"cost_usd": cost, "n_pairs": n}, indent=1), encoding="utf-8")
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
