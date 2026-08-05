"""「おすすめ馬券」の選定: 回収率と的中率のバランスが良い1点を、30点以内で選ぶ。

候補馬券(単勝・複勝・ワイド/馬連/三連複box)ごとに、Harville式(core/probability.py)
で見積もった的中率と、出走馬のオッズから見積もった期待回収率を計算し、両者の
バランス(調和平均)が最も良い候補を選ぶ。的中率だけを追えば単勝1点や複勝1点に
寄りがちで、回収率だけを追えば大穴だけの三連複に寄りがちなため、片方に偏り過ぎ
ない馬券を選ぶのが狙い。

購入点数は最大30点までに制限する(要求仕様)。
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import comb

from core.models import HorseScore
from core.payout_model import payout_multiple
from core.probability import (
    OrderProbabilities,
    at_least_two_in_top3_probability,
    harville_probabilities,
    pair_in_top3_probability,
    strengths_from_scores,
    top2_subset_probability,
    top3_subset_probability,
)

MAX_POINTS = 30


@dataclass
class TicketCandidate:
    bet_type: str
    horses: list[HorseScore]
    points: int
    hit_rate: float
    """見積もり的中率 (0-1)。"""
    return_rate: float
    """見積もり期待回収率 (%, 100が損益分岐)。"""


@dataclass
class RecommendedTicket:
    candidate: TicketCandidate
    explanation: str


def _build_candidates(scores: list[HorseScore], probs: OrderProbabilities) -> list[TicketCandidate]:
    ranked = scores  # score_horses() が既にスコア降順で返す
    candidates: list[TicketCandidate] = []

    top = ranked[0]
    hit = probs.p_first[top.horse.number]
    mult = payout_multiple("単勝", [top.horse.odds])
    candidates.append(TicketCandidate("単勝", [top], points=1, hit_rate=hit, return_rate=hit * mult * 100))

    hit = probs.p_place[top.horse.number]
    mult = payout_multiple("複勝", [top.horse.odds])
    candidates.append(TicketCandidate("複勝", [top], points=1, hit_rate=hit, return_rate=hit * mult * 100))

    box_specs = [("ワイド", 2, 2), ("馬連", 2, 2), ("三連複", 3, 3)]
    for bet_type, min_k, combo_size in box_specs:
        k = min_k
        while True:
            points = comb(k, combo_size)
            if points > MAX_POINTS or k > len(ranked):
                break
            box = ranked[:k]
            box_numbers = {s.horse.number for s in box}
            odds_by_number = {s.horse.number: s.horse.odds for s in box}

            if bet_type == "ワイド":
                hit = at_least_two_in_top3_probability(probs, box_numbers)
            elif bet_type == "馬連":
                hit = top2_subset_probability(probs, box_numbers)
            else:
                hit = top3_subset_probability(probs, box_numbers)

            # 期待回収率は「組合せごとの的中確率×その組合せの払戻倍率」を合算し、
            # 購入点数(=賭け金)で割った1点あたりの期待値。ticket全体の的中率
            # (上のhit、＝どれか1点でも当たる確率)とは別物なので混同しない。
            expected_payout = 0.0
            if bet_type == "馬連":
                for i, j in combinations(box_numbers, 2):
                    p = probs.p_top2_pair.get(frozenset((i, j)), 0.0)
                    expected_payout += p * payout_multiple(bet_type, [odds_by_number[i], odds_by_number[j]])
            elif bet_type == "ワイド":
                for i, j in combinations(box_numbers, 2):
                    p = pair_in_top3_probability(probs, i, j)
                    expected_payout += p * payout_multiple(bet_type, [odds_by_number[i], odds_by_number[j]])
            else:  # 三連複
                for combo in combinations(box_numbers, 3):
                    p = probs.p_top3_set.get(frozenset(combo), 0.0)
                    expected_payout += p * payout_multiple(bet_type, [odds_by_number[n] for n in combo])

            return_rate = expected_payout / points * 100
            candidates.append(
                TicketCandidate(bet_type, box, points=points, hit_rate=hit, return_rate=return_rate)
            )
            k += 1

    return candidates


def _balance_score(candidate: TicketCandidate, max_hit: float, max_return: float) -> float:
    hit_norm = candidate.hit_rate / max_hit if max_hit > 0 else 0.0
    return_norm = candidate.return_rate / max_return if max_return > 0 else 0.0
    if hit_norm + return_norm == 0:
        return 0.0
    # 調和平均: 片方が極端に低いと全体スコアも低くなる(バランス重視)。
    return 2 * hit_norm * return_norm / (hit_norm + return_norm)


def _format_horses(horses: list[HorseScore]) -> str:
    return "、".join(f"{h.horse.number}番 {h.horse.name}" for h in horses)


def pick_recommended_ticket(scores: list[HorseScore]) -> RecommendedTicket:
    strengths = strengths_from_scores(scores)
    probs = harville_probabilities(strengths)
    candidates = _build_candidates(scores, probs)

    max_hit = max(c.hit_rate for c in candidates)
    max_return = max(c.return_rate for c in candidates)
    best = max(candidates, key=lambda c: _balance_score(c, max_hit, max_return))

    combo_desc = (
        f"{best.bet_type}（{_format_horses(best.horses)}）"
        if len(best.horses) <= 3
        else f"{best.bet_type}（{_format_horses(best.horses)} の{best.points}点ボックス）"
    )
    explanation = (
        f"{combo_desc}は見積もり的中率{best.hit_rate * 100:.1f}%・見積もり回収率"
        f"{best.return_rate:.0f}%で、購入{best.points}点の中で的中率と回収率の"
        "バランスが最も良い買い方です。"
    )

    return RecommendedTicket(candidate=best, explanation=explanation)
