"""牌型判斷與比牌。"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum
from itertools import combinations

from poker_arena.cards import Card


class HandCategory(IntEnum):
    HIGH_CARD = 1
    ONE_PAIR = 2
    TWO_PAIR = 3
    THREE_OF_A_KIND = 4
    STRAIGHT = 5
    FLUSH = 6
    FULL_HOUSE = 7
    FOUR_OF_A_KIND = 8
    STRAIGHT_FLUSH = 9
    ROYAL_FLUSH = 10


@dataclass(frozen=True, order=True)
class HandRank:
    """可直接比較大小的牌力。tiebreak 依序為比牌用的點數（含踢腳）。"""

    category: HandCategory
    tiebreak: tuple[int, ...]


@dataclass(frozen=True)
class BestHand:
    rank: HandRank
    cards: tuple[Card, ...]


def _straight_high(ranks: Sequence[int]) -> int | None:
    """ranks 為 5 個不重複點數（遞減）。是順子則回傳最高點，A-2-3-4-5 回傳 5。"""
    if ranks[0] - ranks[4] == 4:
        return ranks[0]
    if list(ranks) == [14, 5, 4, 3, 2]:
        return 5
    return None


def evaluate_five(cards: Sequence[Card]) -> HandRank:
    """判斷剛好 5 張牌的牌力。"""
    if len(cards) != 5:
        raise ValueError("evaluate_five requires exactly 5 cards")
    counts = Counter(c.rank for c in cards)
    # 依 (張數, 點數) 遞減排序，例如葫蘆 KKK22 -> [K, 2]
    grouped = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    ranks = [r for r, _ in grouped]
    shape = [n for _, n in grouped]
    is_flush = len({c.suit for c in cards}) == 1
    straight_high = _straight_high(ranks) if len(ranks) == 5 else None

    if straight_high is not None and is_flush:
        if straight_high == 14:
            return HandRank(HandCategory.ROYAL_FLUSH, (14,))
        return HandRank(HandCategory.STRAIGHT_FLUSH, (straight_high,))
    if shape == [4, 1]:
        return HandRank(HandCategory.FOUR_OF_A_KIND, tuple(ranks))
    if shape == [3, 2]:
        return HandRank(HandCategory.FULL_HOUSE, tuple(ranks))
    if is_flush:
        return HandRank(HandCategory.FLUSH, tuple(ranks))
    if straight_high is not None:
        return HandRank(HandCategory.STRAIGHT, (straight_high,))
    if shape == [3, 1, 1]:
        return HandRank(HandCategory.THREE_OF_A_KIND, tuple(ranks))
    if shape == [2, 2, 1]:
        return HandRank(HandCategory.TWO_PAIR, tuple(ranks))
    if shape == [2, 1, 1, 1]:
        return HandRank(HandCategory.ONE_PAIR, tuple(ranks))
    return HandRank(HandCategory.HIGH_CARD, tuple(ranks))


def best_hand(cards: Sequence[Card]) -> BestHand:
    """從 5~7 張牌中找出最佳的 5 張組合。"""
    if not 5 <= len(cards) <= 7:
        raise ValueError("best_hand requires 5 to 7 cards")
    if len(set(cards)) != len(cards):
        raise ValueError("duplicate cards")
    best: BestHand | None = None
    for combo in combinations(cards, 5):
        rank = evaluate_five(combo)
        if best is None or rank > best.rank:
            best = BestHand(rank, tuple(combo))
    assert best is not None
    return best


def find_winners(hands: Sequence[Sequence[Card]], board: Sequence[Card]) -> list[int]:
    """回傳贏家的索引；多於一人代表平手分池。"""
    ranks = [best_hand([*hole, *board]).rank for hole in hands]
    top = max(ranks)
    return [i for i, r in enumerate(ranks) if r == top]
