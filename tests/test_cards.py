import pytest

from poker_arena.cards import Card, Deck, parse_cards


def test_card_parse_and_str() -> None:
    card = Card.from_str("As")
    assert card == Card(14, "s")
    assert str(card) == "As"
    assert str(Card.from_str("td")) == "Td"


def test_invalid_card() -> None:
    with pytest.raises(ValueError):
        Card.from_str("1s")
    with pytest.raises(ValueError):
        Card(14, "x")


def test_deck_has_52_unique_cards() -> None:
    deck = Deck(seed=1)
    cards = deck.draw(52)
    assert len(set(cards)) == 52
    assert len(deck) == 0
    with pytest.raises(ValueError):
        deck.draw()


def test_deck_seed_is_reproducible() -> None:
    assert Deck(seed=42).draw(10) == Deck(seed=42).draw(10)
    assert Deck(seed=1).draw(10) != Deck(seed=2).draw(10)


def test_deck_exclude() -> None:
    excluded = parse_cards("As Kd")
    deck = Deck(seed=0, exclude=excluded)
    assert len(deck) == 50
    assert not set(excluded) & set(deck.draw(50))
