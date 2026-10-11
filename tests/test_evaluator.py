import pytest

from poker_arena.cards import parse_cards
from poker_arena.evaluator import HandCategory, best_hand, evaluate_five, find_winners


def rank7(text: str):
    return best_hand(parse_cards(text)).rank


@pytest.mark.parametrize(
    ("cards", "category"),
    [
        ("As Ks Qs Js Ts 2d 3c", HandCategory.ROYAL_FLUSH),
        ("9h 8h 7h 6h 5h Ac Kd", HandCategory.STRAIGHT_FLUSH),
        ("7c 7d 7h 7s Kd 2c 3h", HandCategory.FOUR_OF_A_KIND),
        ("Kc Kd Kh 2s 2d 9c 4h", HandCategory.FULL_HOUSE),
        ("Ad 9d 7d 4d 2d Kc Qh", HandCategory.FLUSH),
        ("9c 8d 7h 6s 5c Ad 2h", HandCategory.STRAIGHT),
        ("Qc Qd Qh 9s 5c 3d 2h", HandCategory.THREE_OF_A_KIND),
        ("Jc Jd 4h 4s Ac 8d 2h", HandCategory.TWO_PAIR),
        ("Tc Td Ah 8s 6c 4d 2h", HandCategory.ONE_PAIR),
        ("Ac Jd 9h 7s 5c 3d 2h", HandCategory.HIGH_CARD),
    ],
)
def test_all_categories(cards: str, category: HandCategory) -> None:
    assert rank7(cards).category == category


def test_wheel_straight() -> None:
    rank = rank7("Ac 2d 3h 4s 5c Kd Qh")
    assert rank.category == HandCategory.STRAIGHT
    assert rank.tiebreak == (5,)
    # 小順子輸給 6 高順子
    assert rank < rank7("2d 3h 4s 5c 6d Kd Qh")


def test_wheel_straight_flush() -> None:
    rank = rank7("Ah 2h 3h 4h 5h Kd Qc")
    assert rank.category == HandCategory.STRAIGHT_FLUSH
    assert rank.tiebreak == (5,)


def test_no_wraparound_straight() -> None:
    assert rank7("Qc Kd Ah 2s 3c 8d 9h").category == HandCategory.HIGH_CARD


def test_best_five_picks_highest_straight() -> None:
    # 有 3~9 七張連續，應選 9 高順子
    rank = rank7("3c 4d 5h 6s 7c 8d 9h")
    assert rank.category == HandCategory.STRAIGHT
    assert rank.tiebreak == (9,)


def test_straight_flush_beats_four_of_a_kind() -> None:
    assert rank7("9h 8h 7h 6h 5h 5c 5d") > rank7("5s 5c 5d 5h Ah Kd Qc")


def test_flush_compare_by_all_cards() -> None:
    a = evaluate_five(parse_cards("Ah Jh 9h 6h 3h"))
    b = evaluate_five(parse_cards("Ad Jd 9d 6d 2d"))
    assert a > b
    # 7 張中有 6 張同花，選最大的 5 張
    rank = rank7("Ah Kh 9h 6h 3h 2h Qc")
    assert rank.category == HandCategory.FLUSH
    assert rank.tiebreak == (14, 13, 9, 6, 3)


def test_pair_kicker() -> None:
    board = parse_cards("Ac Ad 8h 5s 2c")
    hands = [parse_cards("Kh 3d"), parse_cards("Qh 4d")]
    assert find_winners(hands, board) == [0]


def test_two_pair_kicker() -> None:
    board = parse_cards("Kc Kd 7h 7s 2c")
    hands = [parse_cards("Ah 3d"), parse_cards("Qh Jd")]
    assert find_winners(hands, board) == [0]


def test_kicker_does_not_play_beyond_five_cards() -> None:
    # 公共牌 A A K K Q，兩人的底牌都比 Q 小 -> 平手
    board = parse_cards("Ac Ad Kh Ks Qc")
    hands = [parse_cards("Jh 2d"), parse_cards("Th 3d")]
    assert find_winners(hands, board) == [0, 1]


def test_full_house_compare_trips_first() -> None:
    assert rank7("3c 3d 3h 2s 2c 8d 9h") > rank7("2c 2d 2h As Ac 8d 9h")


def test_four_of_a_kind_kicker() -> None:
    board = parse_cards("9c 9d 9h 9s 2c")
    hands = [parse_cards("Ah 3d"), parse_cards("Kh Qd")]
    assert find_winners(hands, board) == [0]


def test_board_plays_split_pot() -> None:
    board = parse_cards("Tc Jd Qh Ks Ac")
    hands = [parse_cards("2h 3d"), parse_cards("4h 5d"), parse_cards("6h 7s")]
    assert find_winners(hands, board) == [0, 1, 2]


def test_same_hand_different_suits_tie() -> None:
    board = parse_cards("2c 7d 9h Js 4c")
    hands = [parse_cards("Ah Kh"), parse_cards("Ad Kd"), parse_cards("Qs Qd")]
    assert find_winners(hands, board) == [2]
    hands = [parse_cards("Ah Kh"), parse_cards("Ad Kd")]
    assert find_winners(hands, board) == [0, 1]


def test_invalid_input() -> None:
    with pytest.raises(ValueError):
        best_hand(parse_cards("As Ks Qs Js"))
    with pytest.raises(ValueError):
        best_hand(parse_cards("As As Qs Js Ts"))
