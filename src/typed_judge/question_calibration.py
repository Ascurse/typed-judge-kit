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
