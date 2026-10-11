from poker_arena.bots import (
    CallingStationBot,
    LooseAggressiveBot,
    ProbabilisticBot,
    TightAggressiveBot,
    chen_score,
)
from poker_arena.cards import parse_cards
from poker_arena.engine import ActionType, GameView, Street


def view(hole: str, board: str = "", to_call: int = 0, pot: int = 15, current_bet: int = 10,
         street: Street = Street.PREFLOP, num_active: int = 2) -> GameView:
    return GameView(
        seat=0, hole_cards=tuple(parse_cards(hole)), board=tuple(parse_cards(board)), street=street,
        pot=pot, stack=1000, to_call=to_call, current_bet=current_bet,
        min_raise_to=current_bet + 10, max_raise_to=1000, big_blind=10,
        num_active=num_active, stacks=(1000, 1000), history=(),
    )


def test_chen_score() -> None:
    assert chen_score(tuple(parse_cards("As Ah"))) == 20
    assert chen_score(tuple(parse_cards("As Ks"))) == 12
    assert chen_score(tuple(parse_cards("7c 2d"))) <= 0
    assert chen_score(tuple(parse_cards("2c 2d"))) == 5


def test_tight_aggressive() -> None:
    bot = TightAggressiveBot(seed=0, iterations=50)
    assert bot.decide(view("As Ah", to_call=5)).action is ActionType.RAISE
    d = bot.decide(view("7c 2d", to_call=5))
    assert d.action is ActionType.FOLD and d.thought


def test_loose_aggressive_raises_wide() -> None:
    bot = LooseAggressiveBot(seed=0, iterations=50)
    raises = sum(bot.decide(view("9c 7c", to_call=5)).action is ActionType.RAISE for _ in range(50))
    assert raises > 20


def test_calling_station_calls_big_bet_with_weak_hand() -> None:
    bot = CallingStationBot(seed=0, iterations=50)
    v = view("8c 6d", board="Ah Kd 2s", to_call=100, pot=150, current_bet=100, street=Street.FLOP)
    assert bot.decide(v).action is ActionType.CALL


def test_probabilistic_uses_pot_odds() -> None:
    bot = ProbabilisticBot(seed=0, iterations=200)
    # 河牌只有高牌 8，面對大注 -> 棄牌
    weak = view("8c 6d", board="Ah Kd 2s Js 4h", to_call=300, pot=400, current_bet=300, street=Street.RIVER)
    assert bot.decide(weak).action is ActionType.FOLD
    # 已成葫蘆 -> 加注
    strong = view("Ah Ad", board="As Kd Ks 7h 2c", to_call=50, pot=200, current_bet=50, street=Street.RIVER)
    d = bot.decide(strong)
    assert d.action is ActionType.RAISE and "勝率" in d.thought


def test_bots_are_seed_reproducible() -> None:
    v = view("Td 9d", board="8d 7c 2h", to_call=20, pot=60, current_bet=20, street=Street.FLOP)
    for cls in (TightAggressiveBot, LooseAggressiveBot, CallingStationBot, ProbabilisticBot):
        assert cls(seed=4, iterations=40).decide(v) == cls(seed=4, iterations=40).decide(v)
