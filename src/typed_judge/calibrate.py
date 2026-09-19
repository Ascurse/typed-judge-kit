"""Сверка вердиктов с метками и подбор порогов auto / flag / human. Без вызовов модели."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from .verdict import Verdict

MIN_LABELS = 20
P_MIN = 0.95


def _labeled(verdicts: list[Verdict], labels: dict[str, str]) -> list[tuple[Verdict, str]]:
    return [(v, labels[v.item_id]) for v in verdicts if v.item_id in labels]


def agreement(verdicts: list[Verdict], labels: dict[str, str]) -> tuple[int, int]:
    pairs = _labeled(verdicts, labels)
    return sum(v.verdict == lab for v, lab in pairs), len(pairs)


def confusion(verdicts: list[Verdict], labels: dict[str, str]) -> dict[str, dict[str, int]]:
    m: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for v, lab in _labeled(verdicts, labels):
        m[lab][v.verdict] += 1
    return {k: dict(d) for k, d in m.items()}


@dataclass
class Thresholds:
    auto_at: float | None
    human_below: float | None
    precision_auto: float | None
    coverage_auto: float | None
    n: int
    reliable: bool
    warning: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def fit_thresholds(verdicts: list[Verdict], labels: dict[str, str], positive: str,
                   p_min: float = P_MIN, min_labels: int = MIN_LABELS) -> Thresholds:
    pairs = [(v.score, lab) for v, lab in _labeled(verdicts, labels) if v.score is not None]
    n = len(pairs)
    warning = None if n >= min_labels else f"n={n} < {min_labels}: пороги ненадёжны, копите метки"
    grid = sorted({s for s, _ in pairs})
    best = None  # (coverage, -t, t, precision)
    for t in grid:
        zone = [lab for s, lab in pairs if s >= t]
        prec = sum(lab == positive for lab in zone) / len(zone)
        if prec >= p_min:
            cand = (len(zone) / n, -t, t, prec)
            best = max(best, cand) if best else cand
    human_below = None
    for u in reversed(grid):
        if all(lab != positive for s, lab in pairs if s < u) and any(s < u for s, _ in pairs):
            human_below = u
            break
    return Thresholds(
        auto_at=best[2] if best else None,
        human_below=human_below,
        precision_auto=best[3] if best else None,
        coverage_auto=best[0] if best else None,
        n=n, reliable=n >= min_labels, warning=warning,
    )


def report_text(verdicts: list[Verdict], labels: dict[str, str], t: Thresholds) -> str:
    k, n = agreement(verdicts, labels)
    lines = [f"согласие вердикта с метками: {k}/{n}", "матрица (метка → вердикт: n):"]
    for lab, row in sorted(confusion(verdicts, labels).items()):
        lines.append(f"  {lab}: " + ", ".join(f"{v}={c}" for v, c in sorted(row.items())))
    lines.append(f"пороги: auto при score ≥ {t.auto_at} (precision {t.precision_auto}, покрытие {t.coverage_auto}); "
                 f"human при score < {t.human_below}; между — flag")
    if t.warning:
        lines.append(f"⚠ {t.warning}")
    return "\n".join(lines)
