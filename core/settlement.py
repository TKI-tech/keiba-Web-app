"""予想馬券(おすすめ馬券)を実結果と照合し、回収率を確定する。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from itertools import combinations

from core.data_source import get_entry_data_source
from core.history_source import build_tendency
from core.models import Horse
from core.result_source import draw_actual_top3, payout_amount
from core.scoring import score_horses

STAKE_PER_POINT = 100


@dataclass
class SettlementResult:
    hit: bool
    actual_top3: list[int]
    stake: int
    payout_total: int
    return_rate: float
    """払戻総額 / 購入金額 × 100 (%)。"""


def _by_number(horses: list[Horse], numbers: list[int]) -> list[Horse]:
    lookup = {h.number: h for h in horses}
    return [lookup[n] for n in numbers]


def settle_ticket(
    race_date: Date,
    venue: str,
    race_number: int,
    bet_type: str,
    box_numbers: list[int],
    points: int,
) -> SettlementResult:
    condition, horses = get_entry_data_source().get_race(race_date, venue, race_number)
    tendency = build_tendency(condition)
    scores = score_horses(tendency, horses)

    actual_top3 = draw_actual_top3(condition, scores)
    actual_set = set(actual_top3)
    stake = points * STAKE_PER_POINT

    payout_total = 0
    if bet_type == "単勝":
        if box_numbers[0] == actual_top3[0]:
            payout_total = payout_amount(condition, bet_type, _by_number(horses, [box_numbers[0]]))
    elif bet_type == "複勝":
        if box_numbers[0] in actual_set:
            payout_total = payout_amount(condition, bet_type, _by_number(horses, [box_numbers[0]]))
    elif bet_type == "ワイド":
        for i, j in combinations(box_numbers, 2):
            if i in actual_set and j in actual_set:
                payout_total += payout_amount(condition, bet_type, _by_number(horses, [i, j]))
    elif bet_type == "馬連":
        top2_set = set(actual_top3[:2])
        for i, j in combinations(box_numbers, 2):
            if {i, j} == top2_set:
                payout_total += payout_amount(condition, bet_type, _by_number(horses, [i, j]))
    elif bet_type == "三連複":
        for combo in combinations(box_numbers, 3):
            if set(combo) == actual_set:
                payout_total += payout_amount(condition, bet_type, _by_number(horses, list(combo)))
    else:
        raise ValueError(f"unknown bet type: {bet_type}")

    return SettlementResult(
        hit=payout_total > 0,
        actual_top3=actual_top3,
        stake=stake,
        payout_total=payout_total,
        return_rate=(payout_total / stake * 100) if stake > 0 else 0.0,
    )
