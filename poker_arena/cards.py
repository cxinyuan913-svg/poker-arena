"""撲克牌與牌組。"""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass

RANKS = "23456789TJQKA"
SUITS = "shdc"  # spades, hearts, diamonds, clubs


@dataclass(frozen=True, order=True)
class Card:
    """一張牌。rank 為 2..14（14 = A），suit 為 's'/'h'/'d'/'c'。"""

    rank: int
    suit: str

    def __post_init__(self) -> None:
        if not 2 <= self.rank <= 14:
            raise ValueError(f"invalid rank: {self.rank}")
        if self.suit not in SUITS:
            raise ValueError(f"invalid suit: {self.suit}")

    @classmethod
    def from_str(cls, text: str) -> Card:
        """由 'As'、'Td'、'2c' 這類字串建立。"""
        if len(text) != 2 or text[0].upper() not in RANKS:
            raise ValueError(f"invalid card: {text!r}")
        return cls(RANKS.index(text[0].upper()) + 2, text[1].lower())

    def __str__(self) -> str:
        return f"{RANKS[self.rank - 2]}{self.suit}"

    def __repr__(self) -> str:
        return f"Card({str(self)!r})"


def parse_cards(text: str) -> list[Card]:
    """由空白分隔的字串解析多張牌，例如 'As Kd 7c'。"""
    return [Card.from_str(token) for token in text.split()]


def full_deck() -> list[Card]:
    return [Card(rank, suit) for suit in SUITS for rank in range(2, 15)]


class Deck:
    """一副 52 張的牌組，可指定 seed 讓洗牌結果可重現。"""

    def __init__(self, seed: int | None = None, exclude: Iterable[Card] = ()) -> None:
        excluded = set(exclude)
        self._rng = random.Random(seed)
        self._cards: list[Card] = [c for c in full_deck() if c not in excluded]
        self._rng.shuffle(self._cards)

    def __len__(self) -> int:
        return len(self._cards)

    def draw(self, n: int = 1) -> list[Card]:
        if n > len(self._cards):
            raise ValueError(f"cannot draw {n} cards, only {len(self._cards)} left")
        drawn = self._cards[:n]
        del self._cards[:n]
        return drawn
