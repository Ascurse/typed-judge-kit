"""Зона сомнения и роутинг пограничных решений (бид typed-judge-kit-qei).

DR-63 ранг 6 (каскад FrugalGPT): дешёвая модель решает всё, кроме пограничного — пограничное
уходит дороже (второй движок) или человеку. Решает КОД, а не модель: review_required ставится
по расстоянию до границы рецепта и по расхождению повторов, модель об этом интерфейсе не знает
и повлиять на него отдельным ответом не может.

Ширина полосы — параметр, предрегистрированный в биде до замера, а не подобранный по доле
попадания (README Rule: пороги не крутим на малом n; калибровка ширины ждёт 30+ меток).

Полоса считается по ЛЮБОЙ оси, от которой зависит вердикт, а не только по итоговому score:
первый замер (14 черновиков, кэш v2) показал, что по composite в полосе 0 из 14 — все 14 значений
лежат кучей 0.82..0.93 плюс один 0.639, а ready/light_edit там делят не они, а гейты рецепта
hook_raw >= 2 и evidence >= 0.6. Полоса только по score мерила бы ось, которая в этом наборе
ничего не решает. Поэтому route() принимает margins — нормированные расстояния до всех границ
сразу, а считает их вызывающий код, знающий свои шкалы (composite 0..1, hook 0..3).
"""
from __future__ import annotations

from dataclasses import replace

from .verdict import HUMAN, Verdict

REVIEW_REQUIRED = "review_required"
# Предрегистрировано 2026-09-20 (бид qei) до замера доли: ±0.05 вокруг границы.
BAND_WIDTH = 0.10


def margin(value: float, threshold: float, scale: float = 1.0) -> float:
    """Расстояние до границы в долях диапазона своей шкалы — иначе одна ширина значит разное."""
    return round(abs(value - threshold) / scale, 3)


def route(v: Verdict, *, margins: dict[str, float], width: float = BAND_WIDTH,
          repeats: list[str] | None = None) -> Verdict:
    if v.score is None or v.verdict == HUMAN:
        return replace(v, verdict=REVIEW_REQUIRED,
                       error=v.error or "нет score — маршрутизация без дефолта")
    if repeats and len(set(repeats)) > 1:
        return replace(v, verdict=REVIEW_REQUIRED,
                       error=f"повторы разошлись: {', '.join(repeats)}")
    # 1e-9: расстояния округлены до 3 знаков, но 0.05 в float сравнивается с самим собой не всегда
    near = sorted(name for name, d in margins.items() if d <= width / 2 + 1e-9)
    if near:
        return replace(v, verdict=REVIEW_REQUIRED,
                       error=f"в полосе +-{width / 2} по границам: {', '.join(near)}")
    return v


def review_share(routed: list[Verdict]) -> float:
    if not routed:
        return 0.0
    return round(sum(v.verdict == REVIEW_REQUIRED for v in routed) / len(routed), 3)
