"""ダミーのレース結果生成（JRA-VAN連携までの暫定版）。

実際のレース結果はJRA-VAN連携後に取得する想定(core/data_source.pyと同じ方針)。
それまでは、おすすめ馬券の的中率見積もり(core/recommended_ticket.py)と全く同じ
Harville強さモデル(core/probability.py)から実際に1着・2着・3着を逐次的に重み付き
抽選することで、「予想モデルと矛盾しない」ダミーの実結果を生成する。これにより、
多数のレースを集計した際の実測回収率が、おすすめ馬券計算時の見積もり回収率に
近づく(予想モデルとして自己無矛盾)。

同じレース(日付・会場・レース番号)には常に同じ結果を返すよう決定的にシードして
いる。
"""

from __future__ import annotations

import random

from core.models import Horse, HorseScore, RaceCondition
from core.payout_model import payout_multiple
from core.probability import strengths_from_scores


def _seed_for(*parts: object) -> int:
    return abs(hash(tuple(str(p) for p in parts))) % (2**31)


def draw_actual_top3(condition: RaceCondition, scores: list[HorseScore]) -> list[int]:
    """そのレースの実際の(ダミー)上位3着の馬番を、着順どおりに返す。"""
    rng = random.Random(_seed_for(condition.date, condition.venue, condition.race_number, "actual_result"))
    remaining = dict(strengths_from_scores(scores))

    result: list[int] = []
    for _ in range(3):
        numbers = list(remaining.keys())
        weights = list(remaining.values())
        pick = rng.choices(numbers, weights=weights, k=1)[0]
        result.append(pick)
        del remaining[pick]
    return result


def payout_amount(condition: RaceCondition, bet_type: str, horses: list[Horse]) -> int:
    """指定の組合せ(horsesの順序は問わない)が的中した場合の、100円あたりの払戻額(円)。"""
    base = payout_multiple(bet_type, [h.odds for h in horses])
    numbers_key = "-".join(str(h.number) for h in sorted(horses, key=lambda h: h.number))
    rng = random.Random(_seed_for(condition.date, condition.venue, condition.race_number, bet_type, numbers_key))
    noise = rng.uniform(0.85, 1.2)
    return max(100, round(base * noise * 100))
