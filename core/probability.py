"""Harville式による着順確率モデル。

各馬の「強さ」(strength、勝ちやすさに比例する正の値)から、1着・上位2頭・上位3頭
の組合せ確率を計算する。競馬の着順確率推定として広く使われる古典的なモデルで、
「1着になる確率は強さに比例し、1着馬を除いた残りの中で2着になる確率もまた強さに
比例する」という条件付き独立の仮定を順に適用する(=逐次的な重み付き非復元抽出と
同じ分布)。

おすすめ馬券の期待的中率(core/recommended_ticket.py)と、ダミーレース結果の
抽選(core/result_source.py)の両方がこのモデルに基づく。両者が同じ確率モデルを
共有しているため、「多数のダミーレースを抽選して回収率を集計すると、おすすめ馬券
計算時に見積もった期待値に収束する」という一貫性が保たれる。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.models import HorseScore


def strengths_from_scores(scores: list[HorseScore]) -> dict[int, float]:
    """1着適合率スコアを、Harville式への入力となる「強さ」に変換する。"""
    return {s.horse.number: max(s.win_score, 0.5) for s in scores}


@dataclass
class OrderProbabilities:
    p_first: dict[int, float]
    """P(その馬番が1着)。"""
    p_top2_pair: dict[frozenset[int], float] = field(default_factory=dict)
    """P(1着・2着の組合せがちょうどこのペア)。keyは馬番2つのfrozenset。"""
    p_top3_set: dict[frozenset[int], float] = field(default_factory=dict)
    """P(上位3着の組合せがちょうどこの3頭)。keyは馬番3つのfrozenset。"""
    p_place: dict[int, float] = field(default_factory=dict)
    """P(その馬番が3着以内)。"""


def harville_probabilities(strengths: dict[int, float]) -> OrderProbabilities:
    numbers = list(strengths.keys())
    total = sum(strengths.values())

    p_first = {i: strengths[i] / total for i in numbers}
    p_top2_pair: dict[frozenset[int], float] = {}
    p_top3_set: dict[frozenset[int], float] = {}
    p_place: dict[int, float] = {i: 0.0 for i in numbers}

    for i in numbers:
        remaining_after_1 = total - strengths[i]
        if remaining_after_1 <= 0:
            continue
        for j in numbers:
            if j == i:
                continue
            p_i1_j2 = p_first[i] * (strengths[j] / remaining_after_1)
            pair_key = frozenset((i, j))
            p_top2_pair[pair_key] = p_top2_pair.get(pair_key, 0.0) + p_i1_j2

            remaining_after_2 = remaining_after_1 - strengths[j]
            if remaining_after_2 <= 0:
                continue
            for k in numbers:
                if k == i or k == j:
                    continue
                p_i1_j2_k3 = p_i1_j2 * (strengths[k] / remaining_after_2)
                triple_key = frozenset((i, j, k))
                p_top3_set[triple_key] = p_top3_set.get(triple_key, 0.0) + p_i1_j2_k3

    for triple_key, p in p_top3_set.items():
        for horse_number in triple_key:
            p_place[horse_number] += p

    return OrderProbabilities(p_first=p_first, p_top2_pair=p_top2_pair, p_top3_set=p_top3_set, p_place=p_place)


def top3_subset_probability(probs: OrderProbabilities, box: set[int]) -> float:
    """上位3着が丸ごと box に含まれる確率(三連複boxの的中率)。"""
    return sum(p for triple, p in probs.p_top3_set.items() if triple <= box)


def top2_subset_probability(probs: OrderProbabilities, box: set[int]) -> float:
    """1着・2着の組合せが丸ごと box に含まれる確率(馬連boxの的中率)。"""
    return sum(p for pair, p in probs.p_top2_pair.items() if pair <= box)


def at_least_two_in_top3_probability(probs: OrderProbabilities, box: set[int]) -> float:
    """上位3着のうち少なくとも2頭が box に含まれる確率(ワイドboxの的中率)。"""
    return sum(p for triple, p in probs.p_top3_set.items() if len(triple & box) >= 2)


def pair_in_top3_probability(probs: OrderProbabilities, i: int, j: int) -> float:
    """特定の2頭 i, j がともに上位3着に入る確率(ワイド1点分の的中率)。"""
    return sum(p for triple, p in probs.p_top3_set.items() if i in triple and j in triple)
