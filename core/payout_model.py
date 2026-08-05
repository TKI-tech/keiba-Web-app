"""オッズから払戻倍率を見積もる、共通のおおまかな換算式。

公式の払戻計算式ではなく、「人気薄の組合せほど倍率が高くなる」という方向性だけを
再現した経験則。core/recommended_ticket.py（見積もり回収率の計算）と
core/result_source.py（ダミー実結果の払戻生成）の両方から参照し、同じ換算式を
共有することで一貫性を保っている。
"""

from __future__ import annotations


def payout_multiple(bet_type: str, odds: list[float]) -> float:
    sorted_odds = sorted(odds, reverse=True)
    if bet_type == "単勝":
        return sorted_odds[0]
    if bet_type == "複勝":
        return max(1.05, round(1 + (sorted_odds[0] - 1) * 0.3, 1))
    if bet_type == "枠連":
        # 馬連より当たりやすい(同じ枠に複数頭いる分)ため倍率は低めにしてある。
        return (sorted_odds[0] * sorted_odds[1]) ** 0.5 * 0.7
    if bet_type == "ワイド":
        return (sorted_odds[0] * sorted_odds[1]) ** 0.5 * 0.6
    if bet_type == "馬連":
        return (sorted_odds[0] * sorted_odds[1]) ** 0.6
    if bet_type == "馬単":
        # 着順まで当てる分、同じ組合せの馬連より高倍率。
        return (sorted_odds[0] * sorted_odds[1]) ** 0.65 * 1.3
    if bet_type == "三連複":
        return (sorted_odds[0] * sorted_odds[1] * sorted_odds[2]) ** (1 / 3) * 1.6
    if bet_type == "三連単":
        # 着順まで当てる分、同じ組合せの三連複よりさらに高倍率。
        return (sorted_odds[0] * sorted_odds[1] * sorted_odds[2]) ** (1 / 3) * 2.8
    raise ValueError(f"unknown bet type: {bet_type}")
