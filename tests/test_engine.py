from poker_arena.cards import Deck, parse_cards
from poker_arena.engine import ActionType, Decision, GameView, play_hand, play_match
from poker_arena.bots import default_lineup


class Scripted:
    """依序執行預先寫好的決策；用完後一律過牌/跟注。"""

    def __init__(self, name: str, decisions: list[Decision] | None = None) -> None:
        self.name = name
        self.decisions = list(decisions or [])
        self.views: list[GameView] = []

    def decide(self, view: GameView) -> Decision:
        self.views.append(view)
        if self.decisions:
            return self.decisions.pop(0)
        return Decision(ActionType.CALL, thought="跟")


ALL_IN = Decision(ActionType.RAISE, 10**9, "全下")
FOLD = Decision(ActionType.FOLD, thought="棄")


def stacked(text: str) -> Deck:
    return Deck.stacked(parse_cards(text))


def actions(record) -> list[tuple[int, str]]:
    return [(e["seat"], e["action"]) for e in record.events if e["type"] == "action"]


def test_heads_up_action_order() -> None:
    bots = [Scripted("a"), Scripted("b")]
    record = play_hand(bots, [100, 100], button=0, small_blind=5, big_blind=10, seed=1)
    acts = actions(record)
    # 按鈕位是小盲，翻牌前先行動；翻牌後大盲先行動
    assert acts[0] == (0, "call")
    assert acts[1] == (1, "check")
    flop = [e for e in record.events if e["type"] == "action" and e["street"] == "flop"]
    assert flop[0]["seat"] == 1
    assert sum(record.stacks_after) == 200


def test_everyone_folds_to_big_blind() -> None:
    bots = [Scripted("a", [FOLD]), Scripted("b", [FOLD]), Scripted("c")]
    record = play_hand(bots, [100, 100, 100], button=0, small_blind=5, big_blind=10, seed=1)
    assert record.stacks_after == [100, 95, 105]
    assert not any(e["type"] == "board" for e in record.events)


def test_side_pot() -> None:
    # 發牌從按鈕左邊開始：座位 1、2、0，接著公共牌
    deck = stacked("Kc Kd Qc Qd Ac Ad 2c 7d 9h 3s 8c")
    bots = [Scripted("short", [ALL_IN]), Scripted("mid", [ALL_IN]), Scripted("big")]
    record = play_hand(bots, [100, 300, 300], button=0, small_blind=5, big_blind=10, seed=None, deck=deck)
    awards = [e for e in record.events if e["type"] == "award"]
    assert [(a["pot"], a["amount"], a["winners"]) for a in awards] == [
        ("main", 300, [0]),
        ("side1", 400, [1]),
    ]
    assert record.stacks_after == [300, 400, 0]


def test_split_pot_odd_chip_goes_left_of_button() -> None:
    deck = stacked("2c 3d 4c 5d 6c 7d As Ks Qs Js Ts")
    bots = [Scripted("a"), Scripted("b", [FOLD]), Scripted("c")]
    record = play_hand(bots, [100, 100, 100], button=0, small_blind=5, big_blind=10, seed=None, deck=deck)
    # 底池 25（小盲棄牌留下 5），兩人平分，多的 1 籌碼給按鈕左手邊的座位 2
    assert record.stacks_after == [102, 95, 103]


def test_uncalled_bet_refunded() -> None:
    deck = stacked("2c 3d Ac Ad 7h 8h 9s Jd Kc")
    bots = [Scripted("a", [ALL_IN]), Scripted("b")]
    record = play_hand(bots, [1000, 200], button=0, small_blind=5, big_blind=10, seed=None, deck=deck)
    refund = [e for e in record.events if e["type"] == "refund"]
    assert refund == [{"type": "refund", "seat": 0, "amount": 800}]
    assert record.stacks_after == [1200, 0]


def test_illegal_decisions_are_normalized() -> None:
    check_facing_bet = Decision(ActionType.CHECK)
    tiny_raise = Decision(ActionType.RAISE, 11)
    bots = [Scripted("a", [tiny_raise]), Scripted("b", [check_facing_bet])]
    record = play_hand(bots, [100, 100], button=0, small_blind=5, big_blind=10, seed=1)
    acts = [e for e in record.events if e["type"] == "action"]
    assert acts[0]["action"] == "raise" and acts[0]["amount"] == 20  # 最小加注到 20
    assert acts[1]["action"] == "fold"
    assert record.stacks_after == [110, 90]


def test_reraise_reopens_action() -> None:
    raise_to_30 = Decision(ActionType.RAISE, 30)
    raise_to_90 = Decision(ActionType.RAISE, 90)
    bots = [Scripted("a", [raise_to_30]), Scripted("b", [raise_to_90])]
    record = play_hand(bots, [500, 500], button=0, small_blind=5, big_blind=10, seed=3)
    pre = [(e["seat"], e["action"], e["amount"]) for e in record.events
           if e["type"] == "action" and e["street"] == "preflop"]
    assert pre == [(0, "raise", 30), (1, "raise", 90), (0, "call", 60)]


def test_view_information() -> None:
    a, b = Scripted("a"), Scripted("b")
    play_hand([a, b], [100, 100], button=0, small_blind=5, big_blind=10, seed=1)
    v = a.views[0]
    assert v.to_call == 5 and v.pot == 15 and v.min_raise_to == 20 and v.max_raise_to == 100
    assert len(v.hole_cards) == 2 and v.board == ()


def test_match_conserves_chips_and_is_reproducible() -> None:
    def run():
        return play_match(default_lineup(seed=5, iterations=30), max_hands=15, seed=9)

    first, second = run(), run()
    assert sum(first.final_stacks) == 4000
    assert first.final_stacks == second.final_stacks
    assert [h.events for h in first.hands] == [h.events for h in second.hands]
    for hand in first.hands:
        assert sum(hand.stacks_after) == 4000
        for e in hand.events:
            if e["type"] == "action":
                assert e["thought"]


def test_match_stops_when_one_player_left() -> None:
    bots = [Scripted("a", [ALL_IN] * 100), Scripted("b", [ALL_IN] * 100)]
    result = play_match(bots, starting_stack=100, max_hands=50, seed=2)
    assert sorted(result.final_stacks) == [0, 200]
    assert len(result.hands) < 50
