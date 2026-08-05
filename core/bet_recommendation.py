"""選んだ馬券種に対する「堅実タイプ」「荒れ狙いタイプ」の買い目提案。"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from core.models import HorseScore

BET_TYPE_HORSE_COUNT = {
    "単勝": 1,
    "複勝": 1,
    "枠連": 2,
    "ワイド": 2,
    "馬連": 2,
    "馬単": 2,
    "三連複": 3,
    "三連単": 3,
}

BET_TYPES = list(BET_TYPE_HORSE_COUNT.keys())


@dataclass
class BetSuggestion:
    style_label: str
    horses: list[HorseScore]
    explanation: str


def _format_horses(horses: list[HorseScore], bet_type: str) -> str:
    if bet_type == "枠連":
        return "、".join(f"{h.horse.frame}枠（{h.horse.number}番 {h.horse.name}）" for h in horses)
    return "、".join(f"{h.horse.number}番 {h.horse.name}" for h in horses)


def recommend_bets(scores: list[HorseScore], bet_type: str) -> tuple[BetSuggestion, BetSuggestion]:
    if bet_type not in BET_TYPE_HORSE_COUNT:
        raise ValueError(f"unknown bet type: {bet_type}")
    count = BET_TYPE_HORSE_COUNT[bet_type]

    by_rank = sorted(scores, key=lambda s: (s.win_score + s.place_score) / 2, reverse=True)
    odds_median = median(s.horse.odds for s in scores)

    favorites = [s for s in by_rank if s.horse.odds <= odds_median]
    if len(favorites) < count:
        favorites = by_rank
    solid_picks = favorites[:count]
    solid = BetSuggestion(
        style_label="堅実タイプ",
        horses=solid_picks,
        explanation=(
            f"スコア上位かつオッズが低め（人気馬寄り）の馬を中心に選んだ{bet_type}です。"
            f"{_format_horses(solid_picks, bet_type)}を軸に手堅く当てにいく買い方です。"
        ),
    )

    underdogs = [s for s in by_rank if s.horse.odds > odds_median]
    underdogs.sort(key=lambda s: (s.win_score + s.place_score) / 2, reverse=True)
    top_pick = by_rank[0]

    if count == 1:
        # 単勝・複勝は1頭勝負のため、堅実タイプ(人気馬寄り)とは別の馬として
        # スコアの割にオッズが高い穴馬をそのまま提示する。
        rough_picks: list[HorseScore] = (underdogs or by_rank)[:1]
        rough_explanation = (
            f"スコアの割にオッズが高い（人気薄の）穴馬を狙う{bet_type}です。"
            f"{_format_horses(rough_picks, bet_type)}で高配当を狙う買い方です。"
        )
    else:
        # 複数頭選ぶ馬券は「本命馬+穴馬」の組合せで高配当を狙う定番の考え方に沿わせる。
        rough_picks = [top_pick]
        for candidate in underdogs:
            if len(rough_picks) >= count:
                break
            if candidate not in rough_picks:
                rough_picks.append(candidate)
        while len(rough_picks) < count:
            for candidate in by_rank:
                if candidate not in rough_picks:
                    rough_picks.append(candidate)
                    break
        rough_explanation = (
            f"本命馬に、スコアの割にオッズが高い（人気薄の）穴馬を組み合わせた{bet_type}です。"
            f"{_format_horses(rough_picks, bet_type)}を組み合わせて高配当を狙う買い方です。"
        )

    rough = BetSuggestion(style_label="荒れ狙いタイプ", horses=rough_picks, explanation=rough_explanation)

    return solid, rough
