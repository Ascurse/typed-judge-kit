"""Сверка вердиктов с метками и подбор auto-порога по CRC (Conformal Risk Control). Без вызовов модели.

DR-62: порог, подобранный и оценённый на одних и тех же 14 метках владельца, — утечка данных
(при n=14 «precision 1.0» ничего не значит). Замена: 14 текущих меток заморожены как holdout
(участвуют только в аудите, не в подборе порога — см. split_holdout), а порог auto-зоны
контролируется CRC вместо точечной precision.
"""
from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass

from .verdict import Verdict

ALPHA_DEFAULT = 0.05
# Границы режимов отчёта — фиксированы спекой DR-62, не зависят от alpha.
REPORT_MIN_N = 19
REPORT_INTERVAL_N = 50
# «Устойчивая согласованность» по каппе — только при 25+ парах слепого тест-ретеста (DR-62 §1.7).
RATER_PAIRS_RELIABLE_MIN = 25


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


def split_holdout(labels: dict[str, str], holdout_ids: Iterable[str]) -> tuple[dict[str, str], dict[str, str]]:
    """(калибровочные метки, замороженный holdout). holdout_ids — поле "holdout" в labels.json.

    Пустой/отсутствующий holdout_ids — старый labels.json читается как раньше, все метки идут в калибровку.
    """
    ids = set(holdout_ids)
    calib = {i: lab for i, lab in labels.items() if i not in ids}
    holdout = {i: lab for i, lab in labels.items() if i in ids}
    return calib, holdout


@dataclass
class Thresholds:
    n: int                     # калибровочная выборка (без holdout, только пары с известным score)
    alpha: float
    auto_at: float | None      # порог CRC на score; None — порога нет (auto выключен)
    k: int | None              # ошибок в найденной auto-зоне; None — порога нет
    zone_n: int | None         # размер auto-зоны в найденном пороге; None — порога нет
    risk_bound: float | None   # верхняя граница риска (k+1)/(n+1) на auto_at
    coverage_auto: float | None  # доля калибровочных точек в auto-зоне (0.0, если порога нет)

    def to_dict(self) -> dict:
        return asdict(self)


def fit_thresholds(verdicts: list[Verdict], labels: dict[str, str], positive: str,
                    alpha: float = ALPHA_DEFAULT) -> Thresholds:
    """CRC-порог: наименьший τ (наибольшая auto-зона score >= τ), при котором верхняя граница
    риска (k+1)/(n+1) <= alpha, где k — число ошибок (label != positive) в зоне, n — весь
    калибровочный набор (не размер зоны — так гарантия становится маргинальной, Angelopoulos
    et al., arXiv:2208.02814). Нетривиальный порог существует только при n >= (k_min+1)/alpha - 1.
    """
    pairs = [(v.score, lab) for v, lab in _labeled(verdicts, labels) if v.score is not None]
    n = len(pairs)
    if n == 0:
        return Thresholds(n=0, alpha=alpha, auto_at=None, k=None, zone_n=None, risk_bound=None, coverage_auto=None)
    for tau in sorted({s for s, _ in pairs}):
        zone = [lab for s, lab in pairs if s >= tau]
        k = sum(lab != positive for lab in zone)
        bound = (k + 1) / (n + 1)
        if bound <= alpha:
            return Thresholds(n=n, alpha=alpha, auto_at=tau, k=k, zone_n=len(zone),
                               risk_bound=bound, coverage_auto=len(zone) / n)
    return Thresholds(n=n, alpha=alpha, auto_at=None, k=None, zone_n=None, risk_bound=None, coverage_auto=0.0)


def cohens_kappa(pairs: list[tuple[str, str]]) -> float:
    """Каппа Коэна для пар меток слепого тест-ретеста (данные — отдельный бид «Разметка v2»)."""
    n = len(pairs)
    if n == 0:
        raise ValueError("нет пар для каппы")
    po = sum(a == b for a, b in pairs) / n
    cats = {c for pair in pairs for c in pair}
    pe = sum((sum(a == c for a, _ in pairs) / n) * (sum(b == c for _, b in pairs) / n) for c in cats)
    return 1.0 if pe == 1.0 else (po - pe) / (1 - pe)  # pe=1 — вырожденный случай, все метки в одной категории


def _binom_sf_ge(x: int, n: int, p: float) -> float:
    """P(X >= x) для Bin(n, p)."""
    if x <= 0:
        return 1.0
    if x > n:
        return 0.0
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(x, n + 1))


def _solve_increasing(f, target: float) -> float:
    """p из [0,1], где монотонно возрастающая f(p) == target — бисекция вместо явного бета-квантиля."""
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if f(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def clopper_pearson(x: int, n: int, alpha: float = ALPHA_DEFAULT) -> tuple[float, float]:
    """Двусторонний интервал Клоппера–Пирсона (уровень 1 - alpha) для x успехов из n. Без scipy:
    бисекция по биномиальному CDF вместо квантиля бета-распределения."""
    if n == 0:
        return (0.0, 1.0)
    lo = 0.0 if x == 0 else _solve_increasing(lambda p: _binom_sf_ge(x, n, p), alpha / 2)
    hi = 1.0 if x == n else _solve_increasing(lambda p: _binom_sf_ge(x + 1, n, p), 1 - alpha / 2)
    return (lo, hi)


def report_text(verdicts: list[Verdict], calib_labels: dict[str, str], holdout_labels: dict[str, str],
                 t: Thresholds, rater_pairs: list[tuple[str, str]] | None = None) -> str:
    lines: list[str] = []

    if holdout_labels:
        k, n = agreement(verdicts, holdout_labels)
        lines.append(f"замороженный holdout (n={n}, не участвует в подборе порога, только аудит): "
                     f"согласие {k}/{n}")
        for lab, row in sorted(confusion(verdicts, holdout_labels).items()):
            lines.append(f"  {lab}: " + ", ".join(f"{vv}={c}" for vv, c in sorted(row.items())))

    k, n = agreement(verdicts, calib_labels)
    lines.append(f"калибровка (n={t.n}): согласие вердикта с метками {k}/{n}")
    for lab, row in sorted(confusion(verdicts, calib_labels).items()):
        lines.append(f"  {lab}: " + ", ".join(f"{vv}={c}" for vv, c in sorted(row.items())))

    if t.n < REPORT_MIN_N:
        lines.append(f"n={t.n} < {REPORT_MIN_N}: сертификация невозможна, auto off")
        lines.append("auto выключен, coverage 0")
    elif t.auto_at is None:
        lines.append(f"n={t.n}, alpha={t.alpha}: нетривиального порога не существует — "
                      "auto выключен, coverage 0")
    else:
        lines.append(f"CRC: auto при score >= {t.auto_at} (риск <= {t.alpha}, граница {t.risk_bound:.3f}, "
                     f"покрытие {t.coverage_auto:.2f}); ниже — flag/human")
        if t.n < REPORT_INTERVAL_N:
            lines.append(f"ожидаемый риск <= alpha, точечные метрики справочно (n < {REPORT_INTERVAL_N})")
        else:
            successes = t.zone_n - t.k
            lo, hi = clopper_pearson(successes, t.zone_n, t.alpha)
            lines.append(f"n >= {REPORT_INTERVAL_N}: двусторонний интервал Клоппера–Пирсона для точности "
                         f"auto-зоны — [{lo:.3f}, {hi:.3f}] (95%)")

    if rater_pairs:
        kappa = cohens_kappa(rater_pairs)
        n_pairs = len(rater_pairs)
        line = f"каппа Коэна (слепой тест-ретест): {kappa:.2f} (n={n_pairs} пар)"
        if n_pairs >= RATER_PAIRS_RELIABLE_MIN:
            line += " — устойчивая согласованность разметчика"
        else:
            line += f" — ⚠ n={n_pairs} < {RATER_PAIRS_RELIABLE_MIN}: рано говорить об устойчивой согласованности"
        lines.append(line)

    return "\n".join(lines)
