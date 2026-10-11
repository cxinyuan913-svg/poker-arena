import pytest

from poker_arena.cards import parse_cards
from poker_arena.equity import calculate_equity


def test_aa_vs_kk_preflop() -> None:
    aa, kk = calculate_equity([parse_cards("As Ah"), parse_cards("Ks Kh")], iterations=5000, seed=7)
    assert aa.win == pytest.approx(0.82, abs=0.03)
    assert kk.win == pytest.approx(0.18, abs=0.03)
    assert aa.win + kk.win + aa.tie == pytest.approx(1.0)
    assert aa.tie == kk.tie


def test_same_hand_mostly_ties() -> None:
    a, b = calculate_equity([parse_cards("As Kd"), parse_cards("Ac Kh")], iterations=3000, seed=3)
    assert a.tie > 0.9
    assert a.win == pytest.approx(b.win, abs=0.03)


def test_complete_board_is_exact() -> None:
    board = parse_cards("2c 7d 9h Js 4c")
    win, lose = calculate_equity([parse_cards("Qs Qd"), parse_cards("Ah Kh")], board)
    assert (win.win, win.tie) == (1.0, 0.0)
    assert (lose.win, lose.tie) == (0.0, 0.0)


def test_board_split_pot() -> None:
    board = parse_cards("Tc Jd Qh Ks Ac")
    results = calculate_equity([parse_cards("2h 3d"), parse_cards("4h 5d")], board)
    assert all(r.tie == 1.0 and r.win == 0.0 for r in results)


def test_drawing_dead_on_turn() -> None:
    # 翻牌後轉牌：對手已成皇家同花順
    board = parse_cards("As Ks Qs Js")
    nuts, dead = calculate_equity(
        [parse_cards("Ts 2d"), parse_cards("Ah Ad")], board, iterations=500, seed=0
    )
    assert nuts.win == 1.0
    assert dead.win == 0.0


def test_seed_reproducible() -> None:
    hands = [parse_cards("Qs Jh"), parse_cards("8c 8d"), parse_cards("Ah 5h")]
    board = parse_cards("8h 9s 2h")
    assert calculate_equity(hands, board, 500, seed=11) == calculate_equity(hands, board, 500, seed=11)


def test_invalid_input() -> None:
    with pytest.raises(ValueError):
        calculate_equity([parse_cards("As Ah")])
    with pytest.raises(ValueError):
        calculate_equity([parse_cards("As Ah"), parse_cards("As Kh")])
