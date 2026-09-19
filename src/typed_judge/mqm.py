"""MQM-lite категории дефектов в labels.json (разметка v2, DR-62 §1.6).

Обратная совместимость: старая форма метки — строка-вердикт ("ready"/"light_edit"/"heavy_edit"),
новая — {"verdict": ..., "category": "critical"|"major"|"minor"}, critical = правки чисел/фактов/
юр. рисков. Правило «critical → heavy_edit» — агрегация v3 (bd wnh), здесь только чтение данных.
"""
from __future__ import annotations

CATEGORIES = ("critical", "major", "minor")
Label = str | dict


def verdict_of(entry: Label) -> str:
    return entry if isinstance(entry, str) else entry["verdict"]


def category_of(entry: Label) -> str | None:
    return None if isinstance(entry, str) else entry.get("category")


def plain_verdicts(labels: dict[str, Label]) -> dict[str, str]:
    """labels.json → {id: вердикт}, без категорий — вход для calibrate.py как раньше."""
    return {item_id: verdict_of(v) for item_id, v in labels.items()}


def categories(labels: dict[str, Label]) -> dict[str, str]:
    """{id: категория} только для меток, где категория указана."""
    return {item_id: c for item_id, v in labels.items() if (c := category_of(v)) is not None}
