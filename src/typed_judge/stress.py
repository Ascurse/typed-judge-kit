"""Диагностический стресс-набор (bead typed-judge-kit-h37): auto-off по критическим дефектам + flip-rate RU-пар.

DR-62 §3.2: редкие катастрофические дефекты статистикой на малых метках не доказуемы — компенсация детерминированным
стресс-бенчем. DR-63, открытый вопрос 2: русскоязычная устойчивость рубрик — пары «канцелярит vs чистая правка».
"""
from __future__ import annotations

from dataclasses import dataclass

from .verdict import Verdict

AUTO = "auto"
OFF = "off"


@dataclass
class AutoStatus:
    status: str  # AUTO | OFF
    missed: list[str]  # id критических фикстур, которым судья дал auto_verdict


def auto_status(verdicts: list[Verdict], critical_ids: set[str], auto_verdict: str = "ready") -> AutoStatus:
    """Пропуск = критическая фикстура получила auto_verdict. Хотя бы один пропуск — auto выключается целиком."""
    by_id = {v.item_id: v for v in verdicts}
    missed = sorted(cid for cid in critical_ids if cid in by_id and by_id[cid].verdict == auto_verdict)
    return AutoStatus(OFF if missed else AUTO, missed)


def flip_rate(pairs: list[tuple[str, str]], verdicts: list[Verdict]) -> float:
    """Доля пар (messy, clean), где чистая правка получила score ниже мусорного исходника."""
    by_id = {v.item_id: v for v in verdicts}
    scored = []
    for messy_id, clean_id in pairs:
        m, c = by_id.get(messy_id), by_id.get(clean_id)
        if m is None or c is None or m.score is None or c.score is None:
            continue
        scored.append((m.score, c.score))
    if not scored:
        return 0.0
    return sum(1 for messy, clean in scored if clean < messy) / len(scored)
