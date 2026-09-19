"""Слепые дубли: 1 ранее размеченный текст на ~5 новых, повторная разметка не раньше чем через
14 дней, без уведомления разметчика — измеряет собственный шум разметчика (тест-ретест), а не
согласие с эталоном. Каппа Коэна по парам (первая/повторная метка) — см. calibrate.cohens_kappa.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

RATIO = 5
MIN_AGE_DAYS = 14


@dataclass
class LabeledItem:
    item_id: str
    label: str
    labeled_on: dt.date


def eligible_for_blind_duplicate(items: list[LabeledItem], today: dt.date,
                                  min_age_days: int = MIN_AGE_DAYS) -> list[LabeledItem]:
    return [it for it in items if (today - it.labeled_on).days >= min_age_days]


def schedule_blind_duplicates(new_batch_ids: list[str], pool: list[LabeledItem], today: dt.date,
                               ratio: int = RATIO, min_age_days: int = MIN_AGE_DAYS) -> list[tuple[int, str]]:
    """[(позиция в новом батче, item_id дубля)] — куда подмешать старый текст на повторную
    разметку. Позиции — каждый ratio-й слот. Дубли берутся из eligible-пула по кругу, порядок —
    по item_id (детерминированно, без рандома — воспроизводимость)."""
    eligible = sorted(eligible_for_blind_duplicate(pool, today, min_age_days), key=lambda it: it.item_id)
    if not eligible or not new_batch_ids:
        return []
    slots = range(ratio - 1, len(new_batch_ids), ratio)
    return [(pos, eligible[i % len(eligible)].item_id) for i, pos in enumerate(slots)]


def record_retest(labels_doc: dict, item_id: str, first_label: str, retest_label: str,
                   first_date: str, retest_date: str) -> dict:
    """Новый labels.json с добавленной парой тест-ретест (поле "retest_pairs"). Не мутирует
    вход, не трогает "labels"/"holdout" — ручная запись меток остаётся работой владельца."""
    doc = dict(labels_doc)
    doc["retest_pairs"] = [*labels_doc.get("retest_pairs", []),
                            {"id": item_id, "first": first_label, "first_date": first_date,
                             "retest": retest_label, "retest_date": retest_date}]
    return doc


def rater_pairs_from_doc(labels_doc: dict) -> list[tuple[str, str]]:
    """(первая метка, повторная метка) — вход для calibrate.cohens_kappa / report_text."""
    return [(p["first"], p["retest"]) for p in labels_doc.get("retest_pairs", [])]
