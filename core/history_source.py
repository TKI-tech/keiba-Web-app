"""過去5年データの傾向照合（モック版）。

本来は実データ（例: 忘れないカメラ系リポジトリの keiba.db のような、過去の
レース結果を蓄積したDB）に対して「同コース・同条件」でSQL集計する処理になる。
今回はダミーデータ運用のため、コース条件から「経験則としてよく言われる有利
条件」を疑似的な統計値として生成する ARCHETYPE_RULES に置き換えている。

実データに接続する際は、この関数の戻り値（Tendency）の形さえ揃えれば
core/scoring.py 以降は変更不要。
"""

from __future__ import annotations

import random

from core.models import (
    RUNNING_STYLES,
    CategoryRate,
    RaceCondition,
    Tendency,
    combo_key,
)

_FRAME_ZONES = ["内枠", "中枠", "外枠"]
_WEIGHT_ZONES = ["小型馬", "標準馬", "大型馬"]
_WEIGHT_CHANGE_ZONES = ["体重減", "体重維持", "体重増"]

# 過去5年データを想定した平均出走頭数(この値をもとにベースの勝率/複勝率を仮定する)。
_BASELINE_FIELD_SIZE = 14
_BASELINE_TANSHO_RATE = 1 / _BASELINE_FIELD_SIZE
_BASELINE_FUKUSHO_RATE = min(0.85, 3 / _BASELINE_FIELD_SIZE)


def _seed_for(*parts: object) -> int:
    return abs(hash(tuple(str(p) for p in parts))) % (2**31)


def _archetype_boosts(condition: RaceCondition) -> dict[tuple[str, str], float]:
    """条件に応じて有利になりやすいカテゴリーへの倍率を返す（経験則ベースの簡易モデル）。"""
    boosts: dict[tuple[str, str], float] = {}

    def boost(dimension: str, key: str, multiplier: float) -> None:
        boosts[(dimension, key)] = max(boosts.get((dimension, key), 1.0), multiplier)

    if condition.course_type == "ダート" and condition.distance <= 1400:
        boost("running_style", "先行", 1.7)
        boost("running_style", "逃げ", 1.5)
        boost("frame_zone", "内枠", 1.3)
    elif condition.course_type == "芝" and condition.distance >= 2000:
        boost("running_style", "差し", 1.6)
        boost("running_style", "追込", 1.3)
        boost("frame_zone", "外枠", 1.25)
    elif condition.course_type == "芝" and condition.distance <= 1400:
        boost("running_style", "逃げ", 1.5)
        boost("running_style", "先行", 1.3)
        boost("frame_zone", "内枠", 1.2)
    else:
        boost("running_style", "先行", 1.4)
        boost("frame_zone", "中枠", 1.15)

    if condition.track_condition in ("重", "不良"):
        boost("weight_zone", "大型馬", 1.5)
        boost("running_style", "先行", 1.2)

    return boosts


def _rate(
    rng: random.Random,
    baseline: float,
    multiplier: float,
    volatility: float,
) -> float:
    noise = rng.uniform(1 - volatility, 1 + volatility)
    return max(0.01, min(0.95, baseline * multiplier * noise))


def build_tendency(condition: RaceCondition) -> Tendency:
    rng = random.Random(_seed_for(condition.venue, condition.course_type, condition.distance, condition.track_condition))
    boosts = _archetype_boosts(condition)

    def make_rates(dimension: str, keys: list[str]) -> dict[str, CategoryRate]:
        rates: dict[str, CategoryRate] = {}
        for key in keys:
            multiplier = boosts.get((dimension, key), 1.0)
            sample_size = rng.randint(80, 380)
            tansho_rate = _rate(rng, _BASELINE_TANSHO_RATE, multiplier, 0.15)
            fukusho_rate = _rate(rng, _BASELINE_FUKUSHO_RATE, 1 + (multiplier - 1) * 0.7, 0.12)
            rates[key] = CategoryRate(
                key=key, label=key, sample_size=sample_size, tansho_rate=tansho_rate, fukusho_rate=fukusho_rate
            )
        return rates

    by_running_style = make_rates("running_style", RUNNING_STYLES)
    by_frame_zone = make_rates("frame_zone", _FRAME_ZONES)
    by_weight_zone = make_rates("weight_zone", _WEIGHT_ZONES)
    by_weight_change_zone = make_rates("weight_change_zone", _WEIGHT_CHANGE_ZONES)

    by_combo: dict[str, CategoryRate] = {}
    for frame_zone in _FRAME_ZONES:
        for style in RUNNING_STYLES:
            key = combo_key(frame_zone, style)
            frame_mult = boosts.get(("frame_zone", frame_zone), 1.0)
            style_mult = boosts.get(("running_style", style), 1.0)
            combo_mult = frame_mult * style_mult
            sample_size = rng.randint(20, 120)
            tansho_rate = _rate(rng, _BASELINE_TANSHO_RATE, combo_mult, 0.18)
            fukusho_rate = _rate(rng, _BASELINE_FUKUSHO_RATE, 1 + (combo_mult - 1) * 0.7, 0.15)
            by_combo[key] = CategoryRate(
                key=key, label=key, sample_size=sample_size, tansho_rate=tansho_rate, fukusho_rate=fukusho_rate
            )

    top_combo = max(by_combo.values(), key=lambda r: r.fukusho_rate)
    highlight = (
        f"過去5年の同条件（{condition.venue}・{condition.course_type}{condition.distance}m・"
        f"馬場{condition.track_condition}）では「{top_combo.label}」の複勝率が"
        f"{top_combo.fukusho_rate * 100:.1f}%（{top_combo.sample_size}件中）と最も高い条件です。"
    )

    return Tendency(
        matched_races=rng.randint(180, 620),
        baseline_tansho_rate=_BASELINE_TANSHO_RATE,
        baseline_fukusho_rate=_BASELINE_FUKUSHO_RATE,
        by_running_style=by_running_style,
        by_frame_zone=by_frame_zone,
        by_weight_zone=by_weight_zone,
        by_weight_change_zone=by_weight_change_zone,
        by_combo=by_combo,
        highlight=highlight,
    )
