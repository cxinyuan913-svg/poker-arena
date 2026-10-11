"""精華剪輯：替每手牌打「精彩分數」，挑出最好看的幾手剪成一支影片。

    python -m poker_arena.highlights --seed 1 --hands 40 --top 3 --out highlights.mp4
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from poker_arena.video import Scene, build_scenes, render_video, total_duration


@dataclass
class Highlight:
    hand_index: int
    score: float
    reasons: list[str] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)

    @property
    def title(self) -> str:
        return "、".join(self.reasons) if self.reasons else "一般牌局"


def score_hand(hand_index: int, events: list[dict[str, Any]], equity_iterations: int = 600, seed: int = 0) -> Highlight:
    """依底池大小、全下、攤牌、逆轉、詐唬成功等因素評分。"""
    scenes = build_scenes(events, equity_iterations=equity_iterations, seed=seed)
    big_blind = next((e["amount"] for e in events if e["type"] == "blind" and e["kind"] == "big_blind"), 10) or 10
    awards = [e for e in events if e["type"] == "award"]
    pot = sum(a["amount"] for a in awards)
    winners = {w for a in awards for w in a["winners"]}
    showdown = any(e["type"] == "showdown" for e in events)
    actions = [e for e in events if e["type"] == "action"]
    all_ins = sum(1 for a in actions if a["all_in"])

    score = pot / big_blind / 10  # 每 10 個大盲 1 分
    reasons: list[str] = []
    if pot >= big_blind * 40:
        reasons.append(f"{pot} 大底池")
    if all_ins:
        score += 3 + all_ins
        reasons.append("全下對決")
    if showdown:
        score += 2

    # 用勝率起伏找逆轉：贏家曾經只剩很低的勝率
    if showdown and scenes:
        for w in winners:
            lowest = min(s.players[w].equity for s in scenes)
            if lowest <= 0.3:
                score += (0.3 - lowest) * 40 + 4
                reasons.append(f"{scenes[0].players[w].name}以 {lowest:.0%} 勝率逆轉")
                break
        losers = {i for i, p in enumerate(scenes[-1].players) if p.in_hand and not p.folded} - winners
        for loser in losers:
            peak = max(s.players[loser].equity for s in scenes)
            if peak >= 0.8:
                score += 3
                reasons.append(f"{scenes[0].players[loser].name}被爆冷（曾有 {peak:.0%}）")
                break

    # 詐唬成功：沒攤牌就贏，而且贏家最後一次加注時的內心話提到詐唬
    if not showdown and winners:
        w = next(iter(winners))
        raises = [a for a in actions if a["seat"] == w and a["action"] == "raise"]
        if raises and "詐唬" in raises[-1]["thought"]:
            score += 5
            reasons.append(f"{raises[-1]['player']}詐唬成功")

    return Highlight(hand_index, round(score, 2), reasons, scenes)


def pick_highlights(hands: list[list[dict[str, Any]]], top: int = 3, equity_iterations: int = 600,
                    seed: int = 0) -> list[Highlight]:
    """回傳分數最高的 top 手（依分數由高到低）。"""
    scored = [score_hand(i, events, equity_iterations, seed + i) for i, events in enumerate(hands)]
    scored.sort(key=lambda h: (-h.score, h.hand_index))
    return scored[:top]


def build_reel(highlights: list[Highlight]) -> list[Scene]:
    """把精華串成一支影片：每手前面加一張標題卡。"""
    reel: list[Scene] = []
    for rank, h in enumerate(highlights, start=1):
        if not h.scenes:
            continue
        intro = h.scenes[0]
        reel.append(
            Scene(
                3.0, intro.players, [], intro.pot, "preflop",
                f"精華 #{rank}　第 {h.hand_index + 1} 手　{h.title}",
            )
        )
        reel.extend(h.scenes)
    return reel


def main(argv: list[str] | None = None) -> None:
    from poker_arena.bots import default_lineup
    from poker_arena.engine import play_match

    parser = argparse.ArgumentParser(description="挑出最精彩的幾手並剪成影片")
    parser.add_argument("--json", help="比賽紀錄 JSON；不給就用 --seed 現打一場")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--hands", type=int, default=40)
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--out", help="輸出影片路徑；不給就只印排名")
    args = parser.parse_args(argv)

    if args.json:
        hands = json.loads(Path(args.json).read_text(encoding="utf-8"))["hands"]
    else:
        result = play_match(default_lineup(seed=args.seed), max_hands=args.hands, seed=args.seed)
        hands = [h.events for h in result.hands]
    best = pick_highlights(hands, args.top, seed=args.seed)
    for rank, h in enumerate(best, start=1):
        print(f"#{rank} 第 {h.hand_index + 1} 手　{h.score:.1f} 分　{h.title}")
    if args.out:
        reel = build_reel(best)
        render_video(reel, Path(args.out))
        print(f"已輸出 {args.out}（{total_duration(reel):.1f} 秒）")


if __name__ == "__main__":
    main()
