from poker_arena.cards import Deck, parse_cards
from poker_arena.engine import ActionType, Decision, play_hand
from poker_arena.highlights import build_reel, pick_highlights, score_hand


class Bot:
    def __init__(self, name: str, decisions: list[Decision]) -> None:
        self.name = name
        self.decisions = list(decisions)

    def decide(self, view):
        if self.decisions:
            return self.decisions.pop(0)
        return Decision(ActionType.CALL, thought="跟")


ALL_IN = Decision(ActionType.RAISE, 10**9, "全下")
FOLD = Decision(ActionType.FOLD, thought="棄")


def quiet_hand() -> list[dict]:
    bots = [Bot("a", [FOLD]), Bot("b", [])]
    return play_hand(bots, [500, 500], button=0, small_blind=5, big_blind=10, seed=1).events


def comeback_hand() -> list[dict]:
    # 座位 1 先拿 AA，座位 0 拿 22，河牌出 2 逆轉
    deck = Deck.stacked(parse_cards("Ac Ad 2c 2d 9h 7s 4c Jd 2s"))
    bots = [Bot("a", [ALL_IN]), Bot("b", [])]
    return play_hand(bots, [500, 500], button=0, small_blind=5, big_blind=10, seed=None, deck=deck).events


def bluff_hand() -> list[dict]:
    bluff = Decision(ActionType.RAISE, 100, "沒中，但我要詐唬！")
    bots = [Bot("a", [Decision(ActionType.CALL), bluff]), Bot("b", [Decision(ActionType.CHECK), Decision(ActionType.CHECK), FOLD])]
    return play_hand(bots, [500, 500], button=0, small_blind=5, big_blind=10, seed=3).events


def test_comeback_scores_higher_than_quiet_hand() -> None:
    quiet = score_hand(0, quiet_hand(), equity_iterations=200)
    comeback = score_hand(1, comeback_hand(), equity_iterations=200)
    assert comeback.score > quiet.score + 10
    assert "全下對決" in comeback.reasons
    assert any("逆轉" in r for r in comeback.reasons)
    assert any("爆冷" in r for r in comeback.reasons)


def test_successful_bluff_detected() -> None:
    h = score_hand(0, bluff_hand(), equity_iterations=100)
    assert any("詐唬成功" in r for r in h.reasons)


def test_pick_and_reel() -> None:
    hands = [quiet_hand(), comeback_hand(), quiet_hand()]
    best = pick_highlights(hands, top=2, equity_iterations=100)
    assert [h.hand_index for h in best][0] == 1
    reel = build_reel(best)
    assert reel[0].headline.startswith("精華 #1")
    assert len(reel) == sum(len(h.scenes) for h in best) + len(best)
