"""「おすすめの穴馬」の選定。

出走馬全体をオッズの中央値で人気馬/穴馬に分け、穴馬側の中でスコア
（1着適合率・複勝適合率の平均）が最も高い馬を「スコアの割に人気がない馬」として
提示する。堅実タイプの本命馬とは別に、初心者にも分かりやすい"狙い目"を
1頭だけ示す狙い。
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from core.models import HorseScore, Tendency


@dataclass
class UnderdogPick:
    horse_score: HorseScore
    explanation: str


def pick_underdog(scores: list[HorseScore], tendency: Tendency) -> UnderdogPick | None:
    if len(scores) < 2:
        return None

    odds_median = median(s.horse.odds for s in scores)
    underdogs = [s for s in scores if s.horse.odds > odds_median]
    if not underdogs:
        return None

    best = max(underdogs, key=lambda s: (s.win_score + s.place_score) / 2)
    if best.place_score <= tendency.baseline_fukusho_rate * 100:
        # ベースの複勝率すら上回らない場合は「おすすめ」として提示する根拠が薄い。
        return None

    explanation = (
        f"{best.horse.number}番 {best.horse.name}はオッズ{best.horse.odds}倍（{best.horse.popularity}番人気）"
        f"と人気は控えめですが、複勝適合率は{best.place_score:.1f}%（同条件平均"
        f"{tendency.baseline_fukusho_rate * 100:.1f}%）と平均を上回っており、"
        "妙味のある1頭です。"
    )
    return UnderdogPick(horse_score=best, explanation=explanation)
