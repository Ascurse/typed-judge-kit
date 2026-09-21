"""Вердикт считает код пользователя, не модель. Любая дыра в ответах → human, никаких дефолтов."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

from .batch import Row
from .questions import Answer

HUMAN = "human"
# Рецепт объявляет combine(a) или combine(a, claims) — второй аргумент приходит, только если у item
# есть строки второго шага (claim-vs-evidence). Старая сигнатура так остаётся рабочей.
Combine = Callable[..., tuple[float, str]]


@dataclass
class Verdict:
    item_id: str
    score: float | None
    verdict: str
    error: str | None = None
    # error — только сбой (движок, неполные ответы); note — объяснение маршрутизации (бид en7)
    note: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _by_item(rows: list[Row]) -> dict[str, list[Row]]:
    groups: dict[str, list[Row]] = {}
    for r in rows:
        groups.setdefault(r.item_id, []).append(r)
    return groups


def apply(rows: list[Row], combine: Combine) -> list[Verdict]:
    """Один вердикт на item_id. Несколько строк на item — шаги одного рецепта (бид x5r): первая
    несёт ответы рецепта, остальные складываются во второй аргумент combine."""
    out = []
    for item_id, group in _by_item(rows).items():
        err = next((r.error for r in group if r.error), None)
        if err:
            out.append(Verdict(item_id, None, HUMAN, err))
            continue
        bad = [q for r in group for q, a in r.answers.items() if a.error]
        if bad:
            out.append(Verdict(item_id, None, HUMAN, f"ответы с ошибкой: {', '.join(bad)}"))
            continue
        primary, *extra = group
        claims = {q: a for r in extra for q, a in r.answers.items()}
        try:
            score, verdict = combine(primary.answers, claims) if extra else combine(primary.answers)
            out.append(Verdict(item_id, score, verdict))
        except Exception as e:  # noqa: BLE001 — формула упала на неполных ответах
            out.append(Verdict(item_id, None, HUMAN, f"{type(e).__name__}: {e}"))
    return out
