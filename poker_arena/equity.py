"""蒙地卡羅勝率計算。"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from poker_arena.cards import Card, full_deck
from poker_arena.evaluator import find_winners


@dataclass(frozen=True)
class EquityResult:
    win: float  # 單獨獲勝的比例
    tie: float  # 與他人平分底池的比例


def calculate_equity(
    hole_cards: Sequence[Sequence[Card]],
    board: Sequence[Card] = (),
    iterations: int = 10_000,
    seed: int | None = None,
) -> list[EquityResult]:
    """模擬補完公共牌，回傳每位玩家的勝率與平手率。"""
    if len(hole_cards) < 2:
        raise ValueError("need at least 2 players")
    if any(len(h) != 2 for h in hole_cards):
        raise ValueError("each player needs exactly 2 hole cards")
    if len(board) > 5:
        raise ValueError("board has at most 5 cards")
    known = [c for h in hole_cards for c in h] + list(board)
    if len(set(known)) != len(known):
        raise ValueError("duplicate cards")

    missing = 5 - len(board)
    if missing == 0:
        iterations = 1  # 公共牌已發完，結果是確定的
    remaining = [c for c in full_deck() if c not in set(known)]
    rng = random.Random(seed)
    wins = [0] * len(hole_cards)
    ties = [0] * len(hole_cards)

    for _ in range(iterations):
        full_board = [*board, *rng.sample(remaining, missing)]
        winners = find_winners(hole_cards, full_board)
        if len(winners) == 1:
            wins[winners[0]] += 1
        else:
            for i in winners:
                ties[i] += 1

    return [EquityResult(w / iterations, t / iterations) for w, t in zip(wins, ties)]


def equity_vs_random(
    hole: Sequence[Card],
    board: Sequence[Card],
    num_opponents: int,
    iterations: int,
    rng: random.Random,
) -> float:
    """自己對上 num_opponents 位隨機底牌對手的權益（勝 + 平手按人數分）。

    機器人看不到對手底牌時用這個估計自己的牌力。
    """
    if num_opponents < 1:
        raise ValueError("need at least 1 opponent")
    known = set(hole) | set(board)
    remaining = [c for c in full_deck() if c not in known]
    missing = 5 - len(board)
    need = missing + 2 * num_opponents
    total = 0.0
    for _ in range(iterations):
        drawn = rng.sample(remaining, need)
        full_board = [*board, *drawn[:missing]]
        opponents = [drawn[missing + 2 * k: missing + 2 * k + 2] for k in range(num_opponents)]
        winners = find_winners([list(hole), *opponents], full_board)
        if 0 in winners:
            total += 1 / len(winners)
    return total / iterations
