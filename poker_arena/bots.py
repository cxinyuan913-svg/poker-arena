"""四種個性的機器人。每個決策都附帶「內心話」。"""

from __future__ import annotations

import math
import random

from poker_arena.cards import Card, pretty
from poker_arena.engine import ActionType, Decision, GameView, Street
from poker_arena.equity import equity_vs_random


def chen_score(hole: tuple[Card, ...]) -> float:
    """Chen 公式：翻牌前起手牌分數，約 -1（72o）到 20（AA）。"""
    high, low = sorted((c.rank for c in hole), reverse=True)
    base = {14: 10, 13: 8, 12: 7, 11: 6}.get(high, high / 2)
    if high == low:
        return max(base * 2, 5)
    score = base
    if hole[0].suit == hole[1].suit:
        score += 2
    gap = high - low - 1
    score -= {0: 0, 1: 1, 2: 2, 3: 4}.get(gap, 5)
    if gap <= 1 and high < 12:
        score += 1
    return math.ceil(score)


def pot_odds(view: GameView) -> float:
    """跟注所需的最低勝率。"""
    if view.to_call == 0:
        return 0.0
    return view.to_call / (view.pot + view.to_call)


class BaseBot:
    """共用工具：估算牌力、產生下注金額。"""

    name = "bot"
    style = ""

    def __init__(self, name: str | None = None, seed: int | None = None, iterations: int = 150) -> None:
        if name is not None:
            self.name = name
        self.rng = random.Random(seed)
        self.iterations = iterations

    def equity(self, view: GameView) -> float:
        return equity_vs_random(
            view.hole_cards, view.board, max(view.num_active - 1, 1), self.iterations, self.rng
        )

    def raise_to(self, view: GameView, pot_fraction: float) -> int:
        """加注到「跟注後底池 × pot_fraction」的大小。"""
        size = (view.pot + view.to_call) * pot_fraction
        return min(view.max_raise_to, max(view.min_raise_to, view.current_bet + int(size)))

    def check_or_fold(self, thought: str) -> Decision:
        return Decision(ActionType.FOLD, thought=thought)  # 引擎會在可過牌時轉成過牌

    def decide(self, view: GameView) -> Decision:
        raise NotImplementedError


def _hand(view: GameView) -> str:
    return pretty(view.hole_cards)


class TightAggressiveBot(BaseBot):
    """緊兇：只玩好牌，玩就打得很兇。"""

    name = "老岩"
    style = "緊兇"

    def decide(self, view: GameView) -> Decision:
        if view.street is Street.PREFLOP:
            score = chen_score(view.hole_cards)
            facing_raise = view.current_bet > view.big_blind
            if score >= 10:
                return Decision(
                    ActionType.RAISE,
                    self.raise_to(view, 1.0),
                    f"{_hand(view)}，Chen 分數 {score:.0f}。這是頂級牌，加注把底池做大。",
                )
            if score >= 8 and not facing_raise:
                return Decision(
                    ActionType.RAISE,
                    view.big_blind * 3,
                    f"{_hand(view)} 夠好了，標準加注 3 倍大盲。",
                )
            if score >= 8 and view.to_call <= view.stack * 0.1:
                return Decision(ActionType.CALL, thought=f"{_hand(view)} 不錯，但有人加注，先跟看看。")
            return self.check_or_fold(f"{_hand(view)} 只有 {score:.0f} 分，紀律第一，不玩。")

        eq = self.equity(view)
        odds = pot_odds(view)
        if eq >= 0.65:
            return Decision(
                ActionType.RAISE,
                self.raise_to(view, 0.75),
                f"勝率約 {eq:.0%}，我領先，下重注收價值。",
            )
        if view.to_call == 0:
            return Decision(ActionType.CHECK, thought=f"勝率約 {eq:.0%}，不夠強，過牌控制底池。")
        if eq >= odds + 0.05:
            return Decision(ActionType.CALL, thought=f"勝率 {eq:.0%} 高於賠率需要的 {odds:.0%}，跟。")
        return Decision(ActionType.FOLD, thought=f"勝率只有 {eq:.0%}，要 {odds:.0%} 才划算，放掉。")


class LooseAggressiveBot(BaseBot):
    """鬆凶：什麼牌都想玩，喜歡施壓與詐唬。"""

    name = "狂人"
    style = "鬆凶"
    bluff_rate = 0.35

    def decide(self, view: GameView) -> Decision:
        if view.street is Street.PREFLOP:
            score = chen_score(view.hole_cards)
            if score >= 7 or (score >= 4 and self.rng.random() < 0.6):
                return Decision(
                    ActionType.RAISE,
                    self.raise_to(view, 1.2),
                    f"{_hand(view)}？夠玩了！先加注，讓他們怕我。",
                )
            if score >= 3 and view.to_call <= view.big_blind * 3:
                return Decision(ActionType.CALL, thought=f"{_hand(view)} 便宜看翻牌，什麼都可能中。")
            return self.check_or_fold(f"{_hand(view)} 真的太爛，連我都不想碰。")

        eq = self.equity(view)
        odds = pot_odds(view)
        if eq >= 0.55:
            return Decision(
                ActionType.RAISE,
                self.raise_to(view, 1.0),
                f"勝率 {eq:.0%}，打滿底池，逼他們做決定！",
            )
        if self.rng.random() < self.bluff_rate:
            return Decision(
                ActionType.RAISE,
                self.raise_to(view, 0.8),
                f"其實只有 {eq:.0%}……但他們不知道。詐唬！",
            )
        if view.to_call == 0:
            return Decision(ActionType.CHECK, thought=f"勝率 {eq:.0%}，這次先放他們一馬。")
        if eq >= odds:
            return Decision(ActionType.CALL, thought=f"{eq:.0%} 對 {odds:.0%}，跟了，下一張再說。")
        return Decision(ActionType.FOLD, thought=f"只有 {eq:.0%}，好吧，這手讓你。")


class CallingStationBot(BaseBot):
    """跟注站：幾乎什麼都跟，很少加注，也很少棄牌。"""

    name = "阿跟"
    style = "跟注站"

    def decide(self, view: GameView) -> Decision:
        if view.street is Street.PREFLOP:
            score = chen_score(view.hole_cards)
            if score <= 1 and view.to_call > view.big_blind * 4:
                return self.check_or_fold(f"{_hand(view)} 加這麼多……好啦這次不跟。")
            if view.to_call == 0:
                return Decision(ActionType.CHECK, thought=f"{_hand(view)}，免費看牌最棒了。")
            return Decision(ActionType.CALL, thought=f"{_hand(view)}，跟一下看看翻牌嘛。")

        eq = self.equity(view)
        if eq >= 0.85:
            return Decision(
                ActionType.RAISE,
                self.raise_to(view, 0.5),
                f"勝率 {eq:.0%}！連我都忍不住要加注了。",
            )
        if view.to_call == 0:
            return Decision(ActionType.CHECK, thought=f"勝率 {eq:.0%}，過牌，看下一張。")
        if eq < 0.1 and view.to_call > view.stack * 0.5:
            return Decision(ActionType.FOLD, thought=f"勝率才 {eq:.0%} 又要我押一半身家，不行。")
        return Decision(ActionType.CALL, thought=f"勝率 {eq:.0%}……說不定他在詐唬，我跟！")


class ProbabilisticBot(BaseBot):
    """機率派：完全依照勝率與底池賠率計算期望值。"""

    name = "教授"
    style = "機率派"

    def decide(self, view: GameView) -> Decision:
        if view.street is Street.PREFLOP:
            # 翻牌前也用模擬估算，迭代次數較少
            eq = equity_vs_random(
                view.hole_cards, (), max(view.num_active - 1, 1), max(self.iterations // 2, 1), self.rng
            )
        else:
            eq = self.equity(view)
        fair = 1 / max(view.num_active, 2)  # 平均分配下的公平勝率
        odds = pot_odds(view)
        ev = eq * (view.pot + view.to_call) - view.to_call
        if eq >= fair * 1.6 and eq >= 0.5:
            fraction = min(1.0, (eq - 0.4) * 2)
            return Decision(
                ActionType.RAISE,
                self.raise_to(view, fraction),
                f"勝率 {eq:.1%}（公平值 {fair:.0%}），跟注 EV {ev:+.0f}。加注 {fraction:.0%} 底池。",
            )
        if view.to_call == 0:
            return Decision(ActionType.CHECK, thought=f"勝率 {eq:.1%}，優勢不足以下注，過牌。")
        if eq > odds:
            return Decision(
                ActionType.CALL,
                thought=f"勝率 {eq:.1%} > 賠率門檻 {odds:.1%}，EV {ev:+.0f}，跟注。",
            )
        return Decision(
            ActionType.FOLD,
            thought=f"勝率 {eq:.1%} < 賠率門檻 {odds:.1%}，EV {ev:+.0f}，棄牌。",
        )


def default_lineup(seed: int | None = None, iterations: int = 150) -> list[BaseBot]:
    """四種機器人各一位，各自有可重現的 seed。"""
    rng = random.Random(seed)
    classes = (TightAggressiveBot, LooseAggressiveBot, CallingStationBot, ProbabilisticBot)
    return [cls(seed=rng.randrange(2**32), iterations=iterations) for cls in classes]
