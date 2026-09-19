"""Не-подгоночная оценка согласия судьи с метками (бид typed-judge-kit-zin).

Протокол — DR-63, «Практический перенос», п.7 (LOOCV + permutation test + flip-rate).
14 меток draft_lint заморожены как holdout ещё в DR-62 (7mb): любое согласие,
посчитанное на них, — проверка направления, не доказательство (та же оговорка,
что в calibrate.report_text для holdout-аудита). Не дублирует calibrate.py —
там CRC-порог/каппа для отдельной задачи (авто-зона), здесь — согласие вердикта с меткой.
"""
from __future__ import annotations

import random
from collections.abc import Callable, Iterable
from typing import TypeVar

from .verdict import Verdict

T = TypeVar("T")
CombineFactory = Callable[[list[str]], Callable[[dict], tuple[float, str]]]


def loocv_agreement(item_ids: list[str], combine_factory: CombineFactory, answers: dict[str, dict],
                     labels: dict[str, str], positive: str) -> tuple[int, int]:
    """Leave-one-out: для каждого размеченного item'а функция вердикта строится
    combine_factory(train_ids) по ОСТАЛЬНЫМ id, затем применяется к held-out item'у.

    Если формула не имеет параметров, подбираемых по меткам (единичные веса/фиксированные
    пороги, Дауэс — как в draft_lint_v3.combine), combine_factory может игнорировать
    train_ids: тогда LOOCV корректно вырождается в прямую оценку k/n — это не баг, а
    ожидаемое следствие отсутствия подгонки (см. docstring модуля).
    """
    ids = [i for i in item_ids if i in labels]
    correct = 0
    for held_out in ids:
        train_ids = [i for i in ids if i != held_out]
        combine = combine_factory(train_ids)
        _, verdict = combine(answers[held_out])
        correct += verdict == labels[held_out]
    return correct, len(ids)


def permutation_test(verdicts: list[Verdict], labels: dict[str, str], n_perm: int = 1000,
                      seed: int = 0) -> tuple[int, float]:
    """Перестановочный тест: наблюдаемое согласие против согласия на n_perm случайных
    перестановках меток. p-value — доля перестановок с согласием >= наблюдаемого
    (односторонне: гипотеза — реальные метки дают согласие выше случайного сопоставления).
    """
    pairs = [(v.verdict, labels[v.item_id]) for v in verdicts if v.item_id in labels]
    observed = sum(pred == lab for pred, lab in pairs)
    if not pairs:
        return 0, 1.0
    label_values = [lab for _, lab in pairs]
    rng = random.Random(seed)
    at_least = 0
    for _ in range(n_perm):
        shuffled = label_values[:]
        rng.shuffle(shuffled)
        agree = sum(pred == lab for (pred, _), lab in zip(pairs, shuffled))
        if agree >= observed:
            at_least += 1
    return observed, at_least / n_perm


def flip_rate(reps: Iterable[dict[str, Verdict]]) -> float:
    """Доля item'ов, чей вердикт хотя бы раз разошёлся между независимыми повторами
    одного и того же (clean, неизменного) state — self-consistency, а не точность."""
    reps = list(reps)
    if not reps:
        return 0.0
    item_ids = set.intersection(*(set(r) for r in reps))
    if not item_ids:
        return 0.0
    flips = sum(1 for i in item_ids if len({r[i].verdict for r in reps}) > 1)
    return flips / len(item_ids)
