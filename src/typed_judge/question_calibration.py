"""Калибровка бинарных вопросов draft_lint v3 на стресс-наборе h37 (bead typed-judge-kit-13k).

Читает вероятности Noul-ответов напрямую (a[qid].probability), не вердикт combine() —
задача про отдельные вопросы, а не про агрегацию. Бинаризация 0.5 — тот же порог, что
в draft_lint_v3.combine(), чтобы «сработал» здесь и там значило одно и то же.

Разметка истины (см. бид typed-judge-kit-13k, метки 14 черновиков в подборе НЕ участвуют):
- ru_messy/ru_clean пары (общий "pair") — прямая истина для стилистических вопросов
  (STYLE_DEFECTS): messy → дефект есть, clean → дефекта нет.
- base/critical пары (общий "base_id") — контроль на шум: критический вариант отличается
  от base ТОЛЬКО подменой факта, стиль идентичен. Расхождение бинаризованного ответа на
  такой паре — шум, а не сигнал, для ЛЮБОГО из 10 вопросов.
- Для overclaim/unsourced (CRITICAL_DEFECTS) прямой истины в наборе нет — числа считаются
  и печатаются, но интерпретация "правильно/неправильно" для них не делается здесь.
"""
from __future__ import annotations

from dataclasses import dataclass

from .questions import Answer


def binarize(p: float | None) -> bool | None:
    return None if p is None else p >= 0.5


@dataclass
class QuestionRow:
    qid: str
    n_messy: int
    n_clean: int
    messy_fire_rate: float | None
    clean_fire_rate: float | None
    separation: float | None
    messy_mean_prob: float | None
    clean_mean_prob: float | None
    n_control_pairs: int
    control_disagreement_rate: float | None


def _ids_of_kind(fixtures: dict, kind: str) -> list[str]:
    return [it["id"] for it in fixtures["items"] if it["kind"] == kind]


def _base_to_criticals(fixtures: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for it in fixtures["items"]:
        if it["kind"] == "critical":
            out.setdefault(it["base_id"], []).append(it["id"])
    return out


def _answer(answers_by_item: dict[str, dict[str, Answer]], item_id: str, qid: str) -> Answer | None:
    a = answers_by_item.get(item_id, {}).get(qid)
    if a is None or a.error or a.probability is None:
        return None
    return a


def _probs(answers_by_item: dict[str, dict[str, Answer]], ids: list[str], qid: str) -> list[float]:
    out = []
    for item_id in ids:
        a = _answer(answers_by_item, item_id, qid)
        if a is not None:
            out.append(a.probability)
    return out


def _fire_rate(probs: list[float]) -> float | None:
    return None if not probs else sum(p >= 0.5 for p in probs) / len(probs)


def _mean(probs: list[float]) -> float | None:
    return None if not probs else round(sum(probs) / len(probs), 3)


def question_table(answers_by_item: dict[str, dict[str, Answer]], fixtures: dict,
                    question_ids: tuple[str, ...]) -> list[QuestionRow]:
    messy_ids = _ids_of_kind(fixtures, "ru_messy")
    clean_ids = _ids_of_kind(fixtures, "ru_clean")
    base_to_criticals = _base_to_criticals(fixtures)

    rows = []
    for qid in question_ids:
        messy_probs = _probs(answers_by_item, messy_ids, qid)
        clean_probs = _probs(answers_by_item, clean_ids, qid)
        messy_rate, clean_rate = _fire_rate(messy_probs), _fire_rate(clean_probs)
        sep = None if messy_rate is None or clean_rate is None else round(messy_rate - clean_rate, 3)

        disagreements = n_pairs = 0
        for base_id, critical_ids in base_to_criticals.items():
            base_a = _answer(answers_by_item, base_id, qid)
            if base_a is None:
                continue
            base_bin = binarize(base_a.probability)
            for cid in critical_ids:
                crit_a = _answer(answers_by_item, cid, qid)
                if crit_a is None:
                    continue
                n_pairs += 1
                disagreements += binarize(crit_a.probability) != base_bin

        rows.append(QuestionRow(
            qid=qid,
            n_messy=len(messy_probs), n_clean=len(clean_probs),
            messy_fire_rate=messy_rate, clean_fire_rate=clean_rate, separation=sep,
            messy_mean_prob=_mean(messy_probs), clean_mean_prob=_mean(clean_probs),
            n_control_pairs=n_pairs,
            control_disagreement_rate=None if n_pairs == 0 else round(disagreements / n_pairs, 3),
        ))
    return rows


@dataclass
class KindRow:
    """Разделение классов, заданных не парой messy/clean, а парой kind'ов фикстур.

    Нужна критическим вопросам (бид k55): у overclaim прямой истины в ru_messy/ru_clean нет,
    зато есть минимальные пары base/overclaim — тот же текст с дописанным перегибом.
    """
    qid: str
    n_positive: int
    n_negative: int
    positive_fire_rate: float | None
    negative_fire_rate: float | None
    separation: float | None
    positive_mean_prob: float | None
    negative_mean_prob: float | None


def kind_row(answers_by_item: dict[str, dict[str, Answer]], fixtures: dict, qid: str, *,
             positive_kind: str, negative_kinds: tuple[str, ...]) -> KindRow:
    pos = _probs(answers_by_item, _ids_of_kind(fixtures, positive_kind), qid)
    neg = [p for k in negative_kinds for p in _probs(answers_by_item, _ids_of_kind(fixtures, k), qid)]
    pos_rate, neg_rate = _fire_rate(pos), _fire_rate(neg)
    return KindRow(
        qid=qid, n_positive=len(pos), n_negative=len(neg),
        positive_fire_rate=pos_rate, negative_fire_rate=neg_rate,
        separation=None if pos_rate is None or neg_rate is None else round(pos_rate - neg_rate, 3),
        positive_mean_prob=_mean(pos), negative_mean_prob=_mean(neg),
    )


def _fmt(x: float | None) -> str:
    return "-" if x is None else f"{x:.3f}"


def markdown_table(rows: list[QuestionRow]) -> str:
    header = ("| вопрос | messy fire (n) | clean fire (n) | separation | "
              "messy mean p | clean mean p | control disagreement (n) |")
    sep = "|---|---|---|---|---|---|---|"
    lines = [header, sep]
    for r in rows:
        lines.append(
            f"| {r.qid} | {_fmt(r.messy_fire_rate)} ({r.n_messy}) | {_fmt(r.clean_fire_rate)} ({r.n_clean}) | "
            f"{_fmt(r.separation)} | {_fmt(r.messy_mean_prob)} | {_fmt(r.clean_mean_prob)} | "
            f"{_fmt(r.control_disagreement_rate)} ({r.n_control_pairs}) |"
        )
    return "\n".join(lines)


def markdown_kind_table(rows: list[KindRow], positive_kind: str,
                        negative_kinds: tuple[str, ...]) -> str:
    neg = "+".join(negative_kinds)
    lines = [f"| вопрос | {positive_kind} fire (n) | {neg} fire (n) | separation | "
             f"{positive_kind} mean p | {neg} mean p |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| {r.qid} | {_fmt(r.positive_fire_rate)} ({r.n_positive}) | "
            f"{_fmt(r.negative_fire_rate)} ({r.n_negative}) | {_fmt(r.separation)} | "
            f"{_fmt(r.positive_mean_prob)} | {_fmt(r.negative_mean_prob)} |"
        )
    return "\n".join(lines)


@dataclass
class PairedShift:
    """Сдвиг вероятностей одного вопроса от переформулировки (бид p6g).

    Пары — по item_id: один и тот же текст, два прогона с разной формулировкой вопроса.
    Сравнивать средние по прогонам недостаточно — они скрывают разнонаправленные сдвиги;
    n_flips считает то, что реально меняет вердикт: переход через порог.
    """
    qid: str
    threshold: float
    n: int
    mean_delta: float | None
    max_abs_delta: float | None
    fire_rate_a: float | None
    fire_rate_b: float | None
    n_flips: int


def paired_shift(answers_a: dict[str, dict[str, Answer]], answers_b: dict[str, dict[str, Answer]],
                 qid: str, *, threshold: float) -> PairedShift:
    pairs = []
    for item_id in answers_a:
        a, b = _answer(answers_a, item_id, qid), _answer(answers_b, item_id, qid)
        if a is not None and b is not None:
            pairs.append((a.probability, b.probability))
    deltas = [pb - pa for pa, pb in pairs]
    rate = lambda ps: None if not ps else round(sum(p >= threshold for p in ps) / len(ps), 3)  # noqa: E731
    return PairedShift(
        qid=qid, threshold=threshold, n=len(pairs),
        mean_delta=None if not deltas else round(sum(deltas) / len(deltas), 3),
        max_abs_delta=None if not deltas else round(max(abs(d) for d in deltas), 3),
        fire_rate_a=rate([pa for pa, _ in pairs]), fire_rate_b=rate([pb for _, pb in pairs]),
        n_flips=sum((pa >= threshold) != (pb >= threshold) for pa, pb in pairs),
    )
