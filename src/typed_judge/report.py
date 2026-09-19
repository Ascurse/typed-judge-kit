"""Markdown-отчёты: прогон и построчное сравнение двух прогонов (расхождения видны, не усредняются)."""
from __future__ import annotations

import statistics

from .batch import Row
from .verdict import Verdict


def _cell(x) -> str:
    """Значение ячейки может содержать | или перенос строки (текст ошибки движка) — экранируем, иначе таблица рвётся."""
    return str(x).replace("|", "\\|").replace("\n", " ")


def markdown(rows: list[Row], verdicts: list[Verdict]) -> str:
    lines = ["| item | verdict | score | error |", "|---|---|---|---|"]
    for v in verdicts:
        lines.append(f"| {v.item_id} | {_cell(v.verdict)} | {'' if v.score is None else v.score} | "
                      f"{_cell(v.error) if v.error else ''} |")
    errs = sum(1 for v in verdicts if v.error)
    lat = [r.latency_s for r in rows if r.latency_s]
    lines += ["", f"items: {len(verdicts)}, ошибок: {errs}, "
                  f"токены in/out: {sum(r.input_tokens for r in rows)}/{sum(r.output_tokens for r in rows)}, "
                  f"медиана latency: {round(statistics.median(lat), 3) if lat else '-'} с"]
    return "\n".join(lines)


def compare(a: list[Verdict], b: list[Verdict]) -> str:
    bm = {v.item_id: v for v in b}
    lines = ["| item | A | B | |", "|---|---|---|---|"]
    ok = n = 0
    for va in a:
        vb = bm.get(va.item_id)
        if vb is None:
            continue
        n += 1
        same = va.verdict == vb.verdict
        ok += same
        lines.append(f"| {va.item_id} | {_cell(va.verdict)} | {_cell(vb.verdict)} | {'✓' if same else '✗'} |")
    lines += ["", f"совпало {ok}/{n}"]
    return "\n".join(lines)
