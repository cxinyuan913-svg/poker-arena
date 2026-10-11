"""命令列：跑一場四機器人比賽，印出文字轉播，並可存成 JSON 給影片產生器使用。

    python -m poker_arena --hands 30 --seed 1 --json match.json
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from poker_arena.bots import default_lineup
from poker_arena.cards import Card, pretty
from poker_arena.engine import MatchResult, play_match

ACTION_TEXT = {"fold": "棄牌", "check": "過牌", "call": "跟注", "raise": "加注到"}
CATEGORY_TEXT = {
    "HIGH_CARD": "高牌",
    "ONE_PAIR": "一對",
    "TWO_PAIR": "兩對",
    "THREE_OF_A_KIND": "三條",
    "STRAIGHT": "順子",
    "FLUSH": "同花",
    "FULL_HOUSE": "葫蘆",
    "FOUR_OF_A_KIND": "四條",
    "STRAIGHT_FLUSH": "同花順",
    "ROYAL_FLUSH": "皇家同花順",
}
STREET_TEXT = {"flop": "翻牌", "turn": "轉牌", "river": "河牌"}


def _cards(codes: list[str]) -> str:
    return pretty(Card.from_str(c) for c in codes)


def narrate_hand(events: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    names: list[str] = []
    for e in events:
        t = e["type"]
        if t == "hand_start":
            names = e["players"]
            lines.append(f"===== 第 {e['hand_id'] + 1} 手（按鈕：{names[e['button']]}）=====")
        elif t == "deal":
            for seat, cards in e["hole_cards"].items():
                lines.append(f"  {names[int(seat)]} 底牌 {_cards(cards)}")
        elif t == "blind":
            kind = "小盲" if e["kind"] == "small_blind" else "大盲"
            lines.append(f"  {names[e['seat']]} 下{kind} {e['amount']}")
        elif t == "board":
            lines.append(f"  --- {STREET_TEXT[e['street']]}：{_cards(e['cards'])}")
        elif t == "action":
            amount = f" {e['amount']}" if e["action"] in ("call", "raise") else ""
            all_in = "（全下）" if e["all_in"] else ""
            lines.append(f"  {e['player']} {ACTION_TEXT[e['action']]}{amount}{all_in}　💭 {e['thought']}")
        elif t == "showdown":
            for seat, h in e["hands"].items():
                lines.append(f"  攤牌 {names[int(seat)]}：{_cards(h['hole_cards'])} → {CATEGORY_TEXT[h['category']]}")
        elif t == "refund":
            lines.append(f"  退回 {names[e['seat']]} 未被跟注的 {e['amount']}")
        elif t == "award":
            who = "、".join(names[w] for w in e["winners"])
            label = "主池" if e["pot"] == "main" else "邊池"
            lines.append(f"  🏆 {who} 贏得{label} {e['amount']}")
    return lines


def match_to_json(result: MatchResult) -> dict[str, Any]:
    return {
        "players": result.names,
        "final_stacks": result.final_stacks,
        "hands": [h.events for h in result.hands],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="AI 德州撲克對戰場")
    parser.add_argument("--hands", type=int, default=20, help="最多打幾手")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--stack", type=int, default=1000)
    parser.add_argument("--iterations", type=int, default=150, help="機器人估算勝率的模擬次數")
    parser.add_argument("--json", help="把完整事件紀錄存成 JSON")
    parser.add_argument("--quiet", action="store_true", help="只印最終結果")
    args = parser.parse_args(argv)

    bots = default_lineup(seed=args.seed, iterations=args.iterations)
    result = play_match(bots, starting_stack=args.stack, max_hands=args.hands, seed=args.seed)
    if not args.quiet:
        for hand in result.hands:
            print("\n".join(narrate_hand(hand.events)))
    print(f"\n共打了 {len(result.hands)} 手。最終籌碼：")
    ranking = sorted(zip(result.names, result.final_stacks, bots), key=lambda x: -x[1])
    for name, stack, bot in ranking:
        print(f"  {name}（{bot.style}）：{stack}（{stack - args.stack:+d}）")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(match_to_json(result), f, ensure_ascii=False, indent=1)
        print(f"事件紀錄已存到 {args.json}")


if __name__ == "__main__":
    main()
