"""無限注德州撲克遊戲引擎。

每手牌的所有事件都記錄在 `HandRecord.events`，之後的影片產生器會用到。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from poker_arena.cards import Card, Deck
from poker_arena.evaluator import best_hand


class ActionType(str, Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    RAISE = "raise"  # 包含第一個下注（bet）


class Street(str, Enum):
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"


@dataclass(frozen=True)
class Decision:
    """機器人的決策。RAISE 時 amount 為本輪「加注到」的總額。thought 是內心話。"""

    action: ActionType
    amount: int = 0
    thought: str = ""


@dataclass(frozen=True)
class GameView:
    """輪到某位玩家時，他能看到的資訊。"""

    seat: int
    hole_cards: tuple[Card, ...]
    board: tuple[Card, ...]
    street: Street
    pot: int  # 含本輪已下注的籌碼
    stack: int  # 尚未投入的籌碼
    to_call: int  # 跟注還需要投入的量（已截到 stack 為止）
    current_bet: int  # 本輪最高下注額
    min_raise_to: int  # 最小合法的「加注到」金額
    max_raise_to: int  # 全下時的「加注到」金額
    big_blind: int
    num_active: int  # 尚未棄牌的玩家數（含自己）
    stacks: tuple[int, ...]
    history: tuple[dict[str, Any], ...]  # 本手牌目前為止的行動

    @property
    def can_check(self) -> bool:
        return self.to_call == 0

    @property
    def can_raise(self) -> bool:
        return self.max_raise_to > self.current_bet


class Bot(Protocol):
    name: str

    def decide(self, view: GameView) -> Decision: ...


@dataclass
class _Seat:
    bot: Bot
    stack: int
    hole: tuple[Card, ...] = ()
    street_bet: int = 0
    total_bet: int = 0
    folded: bool = False
    acted: bool = False

    @property
    def all_in(self) -> bool:
        return self.stack == 0 and not self.folded


@dataclass
class HandRecord:
    hand_id: int
    button: int
    events: list[dict[str, Any]] = field(default_factory=list)
    stacks_before: list[int] = field(default_factory=list)
    stacks_after: list[int] = field(default_factory=list)


def play_hand(
    bots: list[Bot],
    stacks: list[int],
    button: int,
    small_blind: int,
    big_blind: int,
    seed: int | None,
    hand_id: int = 0,
    deck: Deck | None = None,
) -> HandRecord:
    """打一手牌。stacks 中籌碼為 0 的玩家不參與。回傳完整紀錄（含結束後籌碼）。

    發牌順序：從按鈕左手邊起每人連發 2 張，接著翻牌 3 張、轉牌、河牌（不燒牌）。
    """
    seated = [i for i, s in enumerate(stacks) if s > 0]
    if len(seated) < 2:
        raise ValueError("need at least 2 players with chips")
    if button not in seated:
        raise ValueError("button must be on a player with chips")

    seats = {i: _Seat(bots[i], stacks[i]) for i in seated}
    record = HandRecord(hand_id, button, stacks_before=list(stacks))
    events = record.events
    if deck is None:
        deck = Deck(seed)
    board: list[Card] = []

    def order_from(start: int) -> list[int]:
        """從 start 開始（含）依座位順序排列的在座玩家。"""
        idx = seated.index(start) if start in seated else 0
        return seated[idx:] + seated[:idx]

    def next_seat(seat: int) -> int:
        return seated[(seated.index(seat) + 1) % len(seated)]

    def pot_total() -> int:
        return sum(s.total_bet for s in seats.values())

    def live() -> list[int]:
        return [i for i in seated if not seats[i].folded]

    def put_in(seat: int, amount: int) -> int:
        s = seats[seat]
        amount = min(amount, s.stack)
        s.stack -= amount
        s.street_bet += amount
        s.total_bet += amount
        return amount

    events.append(
        {
            "type": "hand_start",
            "hand_id": hand_id,
            "button": button,
            "players": [bots[i].name for i in range(len(bots))],
            "stacks": list(stacks),
        }
    )

    # 盲注：兩人時按鈕位是小盲
    if len(seated) == 2:
        sb_seat = button
    else:
        sb_seat = next_seat(button)
    bb_seat = next_seat(sb_seat)
    for seat, blind, kind in ((sb_seat, small_blind, "small_blind"), (bb_seat, big_blind, "big_blind")):
        paid = put_in(seat, blind)
        events.append({"type": "blind", "seat": seat, "kind": kind, "amount": paid})

    for i in order_from(next_seat(button)):
        seats[i].hole = tuple(deck.draw(2))
    events.append({"type": "deal", "hole_cards": {i: [str(c) for c in seats[i].hole] for i in seated}})

    def betting_round(street: Street, first: int) -> None:
        current_bet = max(s.street_bet for s in seats.values())
        min_raise = big_blind
        for s in seats.values():
            s.acted = False
        order = order_from(first)
        pos = 0
        while True:
            contenders = live()
            if len(contenders) == 1:
                return
            needs_action = [
                i for i in contenders
                if not seats[i].all_in and (not seats[i].acted or seats[i].street_bet < current_bet)
            ]
            if not needs_action:
                return
            # 只剩一人能行動且不需跟注時，不必再問
            can_act = [i for i in contenders if not seats[i].all_in]
            if len(can_act) == 1 and seats[can_act[0]].street_bet >= current_bet:
                return
            seat = order[pos % len(order)]
            pos += 1
            s = seats[seat]
            if s.folded or s.all_in or (s.acted and s.street_bet >= current_bet):
                continue

            to_call = min(current_bet - s.street_bet, s.stack)
            max_raise_to = s.street_bet + s.stack
            view = GameView(
                seat=seat,
                hole_cards=s.hole,
                board=tuple(board),
                street=street,
                pot=pot_total(),
                stack=s.stack,
                to_call=to_call,
                current_bet=current_bet,
                min_raise_to=min(current_bet + min_raise, max_raise_to),
                max_raise_to=max_raise_to,
                big_blind=big_blind,
                num_active=len(contenders),
                stacks=tuple(stacks[i] if i not in seats else seats[i].stack for i in range(len(stacks))),
                history=tuple(e for e in events if e["type"] == "action"),
            )
            decision = s.bot.decide(view)
            action, amount = _normalize(decision, view)

            if action is ActionType.FOLD:
                s.folded = True
            elif action is ActionType.CHECK:
                pass
            elif action is ActionType.CALL:
                put_in(seat, to_call)
            else:
                put_in(seat, amount - s.street_bet)
                raise_size = s.street_bet - current_bet
                if raise_size >= min_raise:
                    min_raise = raise_size
                current_bet = s.street_bet
                # 加注後其他人都要重新表態（簡化：不足額的全下加注也會重新開放行動）
                for other in seats.values():
                    other.acted = False
            s.acted = True
            events.append(
                {
                    "type": "action",
                    "street": street.value,
                    "seat": seat,
                    "player": s.bot.name,
                    "action": action.value,
                    "amount": s.street_bet if action is ActionType.RAISE else (to_call if action is ActionType.CALL else 0),
                    "all_in": s.stack == 0,
                    "pot": pot_total(),
                    "thought": decision.thought,
                }
            )

    def end_street() -> None:
        for s in seats.values():
            s.street_bet = 0

    betting_round(Street.PREFLOP, next_seat(bb_seat))
    end_street()
    for street, n in ((Street.FLOP, 3), (Street.TURN, 1), (Street.RIVER, 1)):
        if len(live()) == 1:
            break
        board.extend(deck.draw(n))
        events.append({"type": "board", "street": street.value, "cards": [str(c) for c in board]})
        first = next_seat(button)
        betting_round(street, first)
        end_street()

    _award(seats, seated, board, button, events)
    final = list(stacks)
    for i, s in seats.items():
        final[i] = s.stack
    record.stacks_after = final
    events.append({"type": "hand_end", "stacks": final})
    return record


def _normalize(decision: Decision, view: GameView) -> tuple[ActionType, int]:
    """把不合法的決策修正成最接近的合法行動。"""
    action = decision.action
    if action is ActionType.RAISE:
        if not view.can_raise or view.to_call >= view.stack:
            return (ActionType.CALL, 0) if view.to_call > 0 else (ActionType.CHECK, 0)
        amount = max(view.min_raise_to, min(decision.amount, view.max_raise_to))
        return ActionType.RAISE, amount
    if action is ActionType.CHECK and view.to_call > 0:
        return ActionType.FOLD, 0
    if action is ActionType.CALL and view.to_call == 0:
        return ActionType.CHECK, 0
    if action is ActionType.FOLD and view.to_call == 0:
        return ActionType.CHECK, 0  # 能免費看牌就不棄牌
    return action, 0


def _award(
    seats: dict[int, _Seat],
    seated: list[int],
    board: list[Card],
    button: int,
    events: list[dict[str, Any]],
) -> None:
    contenders = [i for i in seated if not seats[i].folded]
    if len(contenders) == 1:
        winner = contenders[0]
        amount = sum(s.total_bet for s in seats.values())
        seats[winner].stack += amount
        events.append({"type": "award", "pot": "main", "amount": amount, "winners": [winner], "showdown": False})
        return

    ranks = {i: best_hand([*seats[i].hole, *board]) for i in contenders}
    events.append(
        {
            "type": "showdown",
            "hands": {
                i: {
                    "hole_cards": [str(c) for c in seats[i].hole],
                    "category": ranks[i].rank.category.name,
                    "best_five": [str(c) for c in ranks[i].cards],
                }
                for i in contenders
            },
        }
    )
    # 依未棄牌玩家的投入額分層建立主池與邊池；最上層延伸到最大投入額，確保每個籌碼都分出去
    levels = sorted({seats[i].total_bet for i in contenders})
    top = max(s.total_bet for s in seats.values())
    # 奇數籌碼從按鈕左手邊開始分配
    after_button = seated[seated.index(button) + 1:] + seated[: seated.index(button) + 1]
    prev = 0
    pot_index = 0
    for n, level in enumerate(levels):
        upper = top if n == len(levels) - 1 else level
        layer = {i: min(s.total_bet, upper) - min(s.total_bet, prev) for i, s in seats.items()}
        prev = upper
        eligible = [i for i in contenders if seats[i].total_bet >= level]
        pot = sum(layer.values())
        if pot == 0:
            continue
        if len(eligible) == 1 and pot == layer[eligible[0]]:
            # 沒人跟到的超額下注，退回
            seats[eligible[0]].stack += pot
            events.append({"type": "refund", "seat": eligible[0], "amount": pot})
            continue
        best = max(ranks[i].rank for i in eligible)
        winners = [i for i in after_button if i in eligible and ranks[i].rank == best]
        share, rest = divmod(pot, len(winners))
        for k, w in enumerate(winners):
            seats[w].stack += share + (1 if k < rest else 0)
        events.append(
            {
                "type": "award",
                "pot": "main" if pot_index == 0 else f"side{pot_index}",
                "amount": pot,
                "winners": winners,
                "showdown": True,
            }
        )
        pot_index += 1


@dataclass
class MatchResult:
    hands: list[HandRecord]
    final_stacks: list[int]
    names: list[str]


def play_match(
    bots: list[Bot],
    starting_stack: int = 1000,
    small_blind: int = 5,
    big_blind: int = 10,
    max_hands: int = 100,
    seed: int | None = None,
) -> MatchResult:
    """連續打多手牌，直到剩一人有籌碼或達到 max_hands。"""
    rng = random.Random(seed)
    stacks = [starting_stack] * len(bots)
    button = 0
    hands: list[HandRecord] = []
    for hand_id in range(max_hands):
        if sum(1 for s in stacks if s > 0) < 2:
            break
        while stacks[button] == 0:
            button = (button + 1) % len(bots)
        record = play_hand(bots, stacks, button, small_blind, big_blind, rng.randrange(2**32), hand_id)
        hands.append(record)
        stacks = record.stacks_after
        button = (button + 1) % len(bots)
    return MatchResult(hands, stacks, [b.name for b in bots])
