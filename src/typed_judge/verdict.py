"""Вердикт считает код пользователя, не модель. Любая дыра в ответах → human, никаких дефолтов."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

from .batch import Row
from .questions import Answer

HUMAN = "human"
Combine = Callable[[dict[str, Answer]], tuple[float, str]]


@dataclass
class Verdict:
    item_id: str
    score: float | None
    verdict: str
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def apply(rows: list[Row], combine: Combine) -> list[Verdict]:
    out = []
    for r in rows:
        if r.error:
            out.append(Verdict(r.item_id, None, HUMAN, r.error))
            continue
        bad = [q for q, a in r.answers.items() if a.error]
        if bad:
            out.append(Verdict(r.item_id, None, HUMAN, f"ответы с ошибкой: {', '.join(bad)}"))
            continue
        try:
            score, verdict = combine(r.answers)
            out.append(Verdict(r.item_id, score, verdict))
        except Exception as e:  # noqa: BLE001 — формула упала на неполных ответах
            out.append(Verdict(r.item_id, None, HUMAN, f"{type(e).__name__}: {e}"))
    return out
