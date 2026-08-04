"""出走馬のスコアリング（1着適合率 / 複勝率）。

各馬の属性（脚質・枠・馬体重・体重増減・枠×脚質の組合せ）を、過去5年の同条件
データにおけるカテゴリー別の勝率・複勝率と照合し、重み付き平均で0〜100%の
スコアに変換する。サンプル数が少ないカテゴリーはベースレート（同条件全体の
平均）にフォールバックし、小サンプルによる極端な値を避ける（既存モバイル版
エンジンのロジックを踏襲）。
"""

from __future__ import annotations

from core.models import (
    CategoryRate,
    Horse,
    HorseScore,
    Tendency,
    classify_frame_zone,
    classify_weight_change_zone,
    classify_weight_zone,
    combo_key,
)

_WEIGHTS = {
    "running_style": 0.35,
    "frame_zone": 0.15,
    "weight_zone": 0.10,
    "weight_change_zone": 0.10,
    "combo": 0.30,
}

_MIN_SAMPLE_SIZE = 20


def _rate(rates: dict[str, CategoryRate], key: str, baseline: float, use_tansho: bool) -> float:
    hit = rates.get(key)
    if hit is None or hit.sample_size < _MIN_SAMPLE_SIZE:
        return baseline
    return hit.tansho_rate if use_tansho else hit.fukusho_rate


def _weighted_score(tendency: Tendency, horse: Horse, use_tansho: bool) -> tuple[float, list[str]]:
    baseline = tendency.baseline_tansho_rate if use_tansho else tendency.baseline_fukusho_rate

    frame_zone = classify_frame_zone(horse.frame)
    weight_zone = classify_weight_zone(horse.horse_weight)
    weight_change_zone = classify_weight_change_zone(horse.weight_diff)
    combo = combo_key(frame_zone, horse.running_style)

    style_rate = _rate(tendency.by_running_style, horse.running_style, baseline, use_tansho)
    frame_rate = _rate(tendency.by_frame_zone, frame_zone, baseline, use_tansho)
    weight_rate = _rate(tendency.by_weight_zone, weight_zone, baseline, use_tansho)
    change_rate = _rate(tendency.by_weight_change_zone, weight_change_zone, baseline, use_tansho)
    combo_rate = _rate(tendency.by_combo, combo, baseline, use_tansho)

    score = 100 * (
        _WEIGHTS["running_style"] * style_rate
        + _WEIGHTS["frame_zone"] * frame_rate
        + _WEIGHTS["weight_zone"] * weight_rate
        + _WEIGHTS["weight_change_zone"] * change_rate
        + _WEIGHTS["combo"] * combo_rate
    )

    label = "1着適合率" if use_tansho else "複勝率"
    reasons = [
        f"脚質「{horse.running_style}」の同条件{label}: {style_rate * 100:.1f}%",
        f"{frame_zone}×{horse.running_style}の組合せ{label}: {combo_rate * 100:.1f}%",
    ]
    return score, reasons


def score_horses(tendency: Tendency, horses: list[Horse]) -> list[HorseScore]:
    scored: list[HorseScore] = []
    for horse in horses:
        win_score, win_reasons = _weighted_score(tendency, horse, use_tansho=True)
        place_score, place_reasons = _weighted_score(tendency, horse, use_tansho=False)
        scored.append(
            HorseScore(
                horse=horse,
                win_score=win_score,
                place_score=place_score,
                reasons=[win_reasons[1], place_reasons[0]],
            )
        )

    return sorted(scored, key=lambda s: (s.win_score + s.place_score) / 2, reverse=True)
