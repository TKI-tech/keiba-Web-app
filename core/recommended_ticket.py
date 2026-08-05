"""「おすすめ馬券」の選定: 回収率と的中率のバランスが良い1点を、30点以内で選ぶ。

候補馬券(単勝・複勝・枠連・ワイド・馬連・馬単・三連複・三連単のbox)ごとに、
Harville式(core/probability.py)で見積もった的中率と、出走馬のオッズから見積もった
期待回収率を計算し、両者のバランス(調和平均)が最も良い候補を選ぶ。的中率だけを
追えば単勝1点や複勝1点に寄りがちで、回収率だけを追えば大穴だけの三連単に寄りがち
なため、片方に偏り過ぎない馬券を選ぶのが狙い。

「box」で全通り購入する場合、着順を当てる馬券(馬単・三連単)も着順を問わない馬券
(馬連・三連複)も「的中に必要な馬がboxに全頭含まれているか」という的中条件は同じ
になる(順序違いの組合せも全て買うため)。差が出るのは点数(組合せ数 vs 順列数)と
1点あたりの払戻倍率だけなので、的中率の計算は馬連/三連複と共通のものを使い回して
いる。

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


def _single_horse_candidates(scores: list[HorseScore], probs: OrderProbabilities) -> list[TicketCandidate]:
    top = scores[0]

    hit = probs.p_first[top.horse.number]
    mult = payout_multiple("単勝", [top.horse.odds])
    tansho = TicketCandidate("単勝", [top], points=1, hit_rate=hit, return_rate=hit * mult * 100)

    hit = probs.p_place[top.horse.number]
    mult = payout_multiple("複勝", [top.horse.odds])
    fukusho = TicketCandidate("複勝", [top], points=1, hit_rate=hit, return_rate=hit * mult * 100)

    return [tansho, fukusho]


def _pair_box_candidates(
    bet_type: str, ranked: list[HorseScore], probs: OrderProbabilities, ordered: bool
) -> list[TicketCandidate]:
    """ワイド・馬連・馬単のbox候補(2頭の組合せベース)。

    的中条件は馬連/馬単で共通(boxに実際の上位2頭が両方含まれていればよい)なので
    hit_rate・期待払戻の集計方法は同じにし、pointsだけ順列(馬単)か組合せ(その他)
    かで変える。
    """
    candidates: list[TicketCandidate] = []
    k = 2
    while k <= len(ranked):
        points = k * (k - 1) if ordered else comb(k, 2)
        if points > MAX_POINTS:
            break
        box = ranked[:k]
        box_numbers = {s.horse.number for s in box}
        odds_by_number = {s.horse.number: s.horse.odds for s in box}

        if bet_type == "ワイド":
            hit = at_least_two_in_top3_probability(probs, box_numbers)
            expected_payout = sum(
                pair_in_top3_probability(probs, i, j) * payout_multiple(bet_type, [odds_by_number[i], odds_by_number[j]])
                for i, j in combinations(box_numbers, 2)
            )
        else:  # 馬連 / 馬単
            hit = top2_subset_probability(probs, box_numbers)
            expected_payout = sum(
                probs.p_top2_pair.get(frozenset((i, j)), 0.0)
                * payout_multiple(bet_type, [odds_by_number[i], odds_by_number[j]])
                for i, j in combinations(box_numbers, 2)
            )

        return_rate = expected_payout / points * 100
        candidates.append(TicketCandidate(bet_type, box, points=points, hit_rate=hit, return_rate=return_rate))
        k += 1

    return candidates


def _triple_box_candidates(
    bet_type: str, ranked: list[HorseScore], probs: OrderProbabilities, ordered: bool
) -> list[TicketCandidate]:
    """三連複・三連単のbox候補(3頭の組合せベース)。的中条件は共通、pointsのみ異なる。"""
    candidates: list[TicketCandidate] = []
    k = 3
    while k <= len(ranked):
        points = k * (k - 1) * (k - 2) if ordered else comb(k, 3)
        if points > MAX_POINTS:
            break
        box = ranked[:k]
        box_numbers = {s.horse.number for s in box}
        odds_by_number = {s.horse.number: s.horse.odds for s in box}

        hit = top3_subset_probability(probs, box_numbers)
        expected_payout = sum(
            probs.p_top3_set.get(frozenset(combo), 0.0)
            * payout_multiple(bet_type, [odds_by_number[n] for n in combo])
            for combo in combinations(box_numbers, 3)
        )

        return_rate = expected_payout / points * 100
        candidates.append(TicketCandidate(bet_type, box, points=points, hit_rate=hit, return_rate=return_rate))
        k += 1

    return candidates


def _frame_box_candidates(ranked: list[HorseScore], probs: OrderProbabilities) -> list[TicketCandidate]:
    """枠連のbox候補。馬ではなく枠番の組合せで購入するため、スコア上位から出てくる
    「異なる枠」を集めてbox化する(同じ枠の馬が複数出走している場合はまとめて1枠として
    数える)。同一枠同士の組合せ(自枠)は簡略化のため対象外にしている。
    """
    frame_of = {s.horse.number: s.horse.frame for s in ranked}
    # 払戻の見積もりには実際に的中に絡みうる馬(box代表馬に限らず、同じ枠の馬全員)の
    # オッズが要るため、出走馬全体のオッズ表を持っておく。
    odds_by_number = {s.horse.number: s.horse.odds for s in ranked}
    candidates: list[TicketCandidate] = []
    box: list[HorseScore] = []
    seen_frames: set[int] = set()

    for s in ranked:
        if s.horse.frame in seen_frames:
            continue
        seen_frames.add(s.horse.frame)
        box.append(s)
        k = len(box)
        if k < 2:
            continue
        points = comb(k, 2)
        if points > MAX_POINTS:
            break

        frame_set = seen_frames
        hit = sum(
            p
            for pair, p in probs.p_top2_pair.items()
            if all(frame_of[n] in frame_set for n in pair)
        )
        expected_payout = sum(
            p * payout_multiple("枠連", [odds_by_number[i], odds_by_number[j]])
            for (i, j), p in probs.p_top2_pair.items()
            if frame_of[i] in frame_set and frame_of[j] in frame_set
        )
        return_rate = expected_payout / points * 100
        candidates.append(TicketCandidate("枠連", list(box), points=points, hit_rate=hit, return_rate=return_rate))

    return candidates


def _build_candidates(scores: list[HorseScore], probs: OrderProbabilities) -> list[TicketCandidate]:
    ranked = scores  # score_horses() が既にスコア降順で返す
    candidates: list[TicketCandidate] = _single_horse_candidates(scores, probs)
    candidates += _frame_box_candidates(ranked, probs)
    candidates += _pair_box_candidates("ワイド", ranked, probs, ordered=False)
    candidates += _pair_box_candidates("馬連", ranked, probs, ordered=False)
    candidates += _pair_box_candidates("馬単", ranked, probs, ordered=True)
    candidates += _triple_box_candidates("三連複", ranked, probs, ordered=False)
    candidates += _triple_box_candidates("三連単", ranked, probs, ordered=True)
    return candidates


def _balance_score(candidate: TicketCandidate, max_hit: float, max_return: float) -> float:
    hit_norm = candidate.hit_rate / max_hit if max_hit > 0 else 0.0
    return_norm = candidate.return_rate / max_return if max_return > 0 else 0.0
    if hit_norm + return_norm == 0:
        return 0.0
    # 調和平均: 片方が極端に低いと全体スコアも低くなる(バランス重視)。
    return 2 * hit_norm * return_norm / (hit_norm + return_norm)


def _format_horses(horses: list[HorseScore], bet_type: str) -> str:
    if bet_type == "枠連":
        return "、".join(f"{h.horse.frame}枠（{h.horse.number}番 {h.horse.name}）" for h in horses)
    return "、".join(f"{h.horse.number}番 {h.horse.name}" for h in horses)


def pick_recommended_ticket(scores: list[HorseScore]) -> RecommendedTicket:
    strengths = strengths_from_scores(scores)
    probs = harville_probabilities(strengths)
    candidates = _build_candidates(scores, probs)

    max_hit = max(c.hit_rate for c in candidates)
    max_return = max(c.return_rate for c in candidates)
    best = max(candidates, key=lambda c: _balance_score(c, max_hit, max_return))

    horses_desc = _format_horses(best.horses, best.bet_type)
    combo_desc = f"{best.bet_type}（{horses_desc}）" if len(best.horses) <= 3 else f"{best.bet_type}（{horses_desc} の{best.points}点ボックス）"
    explanation = (
        f"{combo_desc}は見積もり的中率{best.hit_rate * 100:.1f}%・見積もり回収率"
        f"{best.return_rate:.0f}%で、購入{best.points}点の中で的中率と回収率の"
        "バランスが最も良い買い方です。"
    )

    return RecommendedTicket(candidate=best, explanation=explanation)
