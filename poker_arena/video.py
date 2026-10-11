"""轉播風格影片產生器。

流程：事件紀錄 → 場景時間軸（含即時勝率）→ ASS 字幕腳本（畫出牌桌、底牌、勝率條、內心話）
→ 交給系統的 ffmpeg（需支援 libass）輸出 MP4。Python 端不需要任何第三方套件。

    python -m poker_arena.video --seed 1 --hand 0 --out hand.mp4
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from poker_arena.cards import RANKS, SUIT_SYMBOLS, Card
from poker_arena.equity import calculate_equity

WIDTH, HEIGHT = 1280, 720
FONT = "WenQuanYi Zen Hei"
ACTION_TEXT = {"fold": "棄牌", "check": "過牌", "call": "跟注", "raise": "加注到"}
CATEGORY_TEXT = {
    "HIGH_CARD": "高牌", "ONE_PAIR": "一對", "TWO_PAIR": "兩對", "THREE_OF_A_KIND": "三條",
    "STRAIGHT": "順子", "FLUSH": "同花", "FULL_HOUSE": "葫蘆", "FOUR_OF_A_KIND": "四條",
    "STRAIGHT_FLUSH": "同花順", "ROYAL_FLUSH": "皇家同花順",
}
STREET_TEXT = {"preflop": "翻牌前", "flop": "翻牌", "turn": "轉牌", "river": "河牌"}


@dataclass
class PlayerState:
    name: str
    hole: list[str]
    stack: int
    bet: int = 0  # 本手已投入
    folded: bool = False
    in_hand: bool = True  # 開局時有籌碼
    last_action: str = ""
    equity: float = 0.0  # 勝 + 平手/2 的近似權益，用於勝率條
    hand_label: str = ""  # 攤牌時的牌型


@dataclass
class Scene:
    duration: float
    players: list[PlayerState]
    board: list[str]
    pot: int
    street: str
    headline: str
    speaker: int | None = None  # 正在說內心話的座位
    thought: str = ""
    winners: list[int] = field(default_factory=list)


def _copy_players(players: list[PlayerState]) -> list[PlayerState]:
    return [replace(p, hole=list(p.hole)) for p in players]


def _update_equity(players: list[PlayerState], board: list[str], iterations: int, seed: int) -> None:
    live = [i for i, p in enumerate(players) if p.in_hand and not p.folded]
    for p in players:
        p.equity = 0.0
    if len(live) == 1:
        players[live[0]].equity = 1.0
        return
    results = calculate_equity(
        [[Card.from_str(c) for c in players[i].hole] for i in live],
        [Card.from_str(c) for c in board],
        iterations=iterations,
        seed=seed,
    )
    # 平手時大家平分；用 tie/人數 的近似（多人平手時略有誤差，對勝率條足夠）
    for i, r in zip(live, results):
        players[i].equity = r.win + r.tie / max(len(live), 2)


def build_scenes(events: list[dict[str, Any]], equity_iterations: int = 1500, seed: int = 0) -> list[Scene]:
    """把一手牌的事件轉成場景列表。勝率只在牌面或存活人數改變時重算。"""
    start = events[0]
    if start["type"] != "hand_start":
        raise ValueError("events must start with hand_start")
    names: list[str] = start["players"]
    players = [PlayerState(n, [], s, in_hand=s > 0) for n, s in zip(names, start["stacks"])]
    board: list[str] = []
    street = "preflop"
    scenes: list[Scene] = []
    title = f"第 {start['hand_id'] + 1} 手"
    calc = 0
    awarded = 0

    def pot() -> int:
        return sum(p.bet for p in players) - awarded

    def snap(duration: float, headline: str, **kw: Any) -> None:
        scenes.append(Scene(duration, _copy_players(players), list(board), pot(), street, headline, **kw))

    def refresh_equity() -> None:
        nonlocal calc
        _update_equity(players, board, equity_iterations, seed + calc)
        calc += 1

    for e in events[1:]:
        t = e["type"]
        if t == "blind":
            p = players[e["seat"]]
            p.bet += e["amount"]
            p.stack -= e["amount"]
            p.last_action = ("小盲 " if e["kind"] == "small_blind" else "大盲 ") + str(e["amount"])
        elif t == "deal":
            for seat, cards in e["hole_cards"].items():
                players[int(seat)].hole = list(cards)
            refresh_equity()
            snap(3.0, f"{title}　發牌")
        elif t == "action":
            p = players[e["seat"]]
            if e["action"] == "fold":
                p.folded = True
            elif e["action"] == "call":
                p.bet += e["amount"]
                p.stack -= e["amount"]
            elif e["action"] == "raise":
                # amount 是本輪「加注到」；用事件中的底池差算出這次投入的量
                added = e["pot"] - pot()
                p.bet += added
                p.stack -= added
            label = ACTION_TEXT[e["action"]]
            if e["action"] in ("call", "raise"):
                label += f" {e['amount']}"
            if e["all_in"]:
                label += " 全下"
            p.last_action = label
            if e["action"] == "fold":
                refresh_equity()
            duration = min(6.0, max(2.5, len(e["thought"]) * 0.12 + 1.0))
            snap(duration, f"{title}　{STREET_TEXT[street]}　{p.name} {label}", speaker=e["seat"], thought=e["thought"])
        elif t == "board":
            street = e["street"]
            board = list(e["cards"])
            for p in players:
                if not p.folded:
                    p.last_action = ""
            refresh_equity()
            snap(2.5, f"{title}　{STREET_TEXT[street]}")
        elif t == "showdown":
            for seat, h in e["hands"].items():
                players[int(seat)].hand_label = CATEGORY_TEXT[h["category"]]
            snap(3.0, f"{title}　攤牌")
        elif t == "refund":
            p = players[e["seat"]]
            p.bet -= e["amount"]
            p.stack += e["amount"]
        elif t == "award":
            awarded += e["amount"]
            for w in e["winners"]:
                players[w].stack += e["amount"] // len(e["winners"])
            who = "、".join(names[w] for w in e["winners"])
            label = "主池" if e["pot"] == "main" else "邊池"
            snap(3.0, f"{title}　{who} 贏得{label} {e['amount']}", winners=list(e["winners"]))
        elif t == "hand_end":
            for p, s in zip(players, e["stacks"]):
                p.stack = s
    return scenes


# ---------- ASS 輸出 ----------

def _ass_time(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _color(rgb: str, alpha: int = 0) -> str:
    """'RRGGBB' → ASS 的 &HAABBGGRR。"""
    r, g, b = rgb[0:2], rgb[2:4], rgb[4:6]
    return f"&H{alpha:02X}{b}{g}{r}&"


def _rect(x: float, y: float, w: float, h: float, fill: str, alpha: int = 0, layer: int = 0) -> tuple[int, str]:
    shape = f"m 0 0 l {w:.0f} 0 {w:.0f} {h:.0f} 0 {h:.0f}"
    return layer, (
        f"{{\\an7\\pos({x:.0f},{y:.0f})\\bord0\\shad0\\1c{_color(fill)}\\1a&H{alpha:02X}&\\p1}}{shape}"
    )


def _text(x: float, y: float, text: str, size: int, color: str = "FFFFFF", align: int = 7,
          layer: int = 3, bold: bool = False, alpha: int = 0) -> tuple[int, str]:
    text = text.replace("{", "(").replace("}", ")").replace("\n", "\\N")
    b = "\\b1" if bold else ""
    return layer, (
        f"{{\\an{align}\\pos({x:.0f},{y:.0f})\\fs{size}{b}\\bord2\\shad0\\3c&H000000&"
        f"\\1c{_color(color)}\\alpha&H{alpha:02X}&}}{text}"
    )


def _card(x: float, y: float, code: str | None, scale: float = 1.0, dim: bool = False) -> list[tuple[int, str]]:
    w, h = 54 * scale, 76 * scale
    if code is None:
        return [_rect(x, y, w, h, "1E6B47", alpha=0x40, layer=1)]
    alpha = 0x90 if dim else 0
    card = Card.from_str(code)
    red = card.suit in "hd"
    label = f"{RANKS[card.rank - 2]}\\N{SUIT_SYMBOLS[card.suit]}"
    return [
        _rect(x, y, w, h, "F5F5F0", alpha=alpha, layer=1),
        (2, f"{{\\an5\\pos({x + w / 2:.0f},{y + h / 2:.0f})\\fs{int(28 * scale)}\\b1\\bord0\\shad0"
            f"\\1c{_color('D32F2F' if red else '111111')}\\alpha&H{alpha:02X}&}}{label}"),
    ]


# 四個座位的面板左上角位置；超過 4 人時依序往下排
PANEL_POS = [(40, 110), (900, 110), (900, 400), (40, 400)]
PANEL_W, PANEL_H = 340, 190


def _panel(seat: int, p: PlayerState, scene: Scene) -> list[tuple[int, str]]:
    x, y = PANEL_POS[seat] if seat < len(PANEL_POS) else (40 + 60 * seat, 110)
    items: list[tuple[int, str]] = []
    speaking = scene.speaker == seat
    winner = seat in scene.winners
    border = "FFD54F" if speaking or winner else "263238"
    items.append(_rect(x - 4, y - 4, PANEL_W + 8, PANEL_H + 8, border, alpha=0 if speaking or winner else 0x60))
    items.append(_rect(x, y, PANEL_W, PANEL_H, "102027", alpha=0x30))
    if not p.in_hand:
        items.append(_text(x + 16, y + 12, f"{p.name}（出局）", 26, "9E9E9E"))
        return items
    dim = p.folded
    name_color = "9E9E9E" if dim else "FFFFFF"
    items.append(_text(x + 16, y + 10, p.name, 28, name_color, bold=True))
    items.append(_text(x + PANEL_W - 16, y + 14, f"籌碼 {p.stack}", 22, "B0BEC5", align=9))
    for k, code in enumerate(p.hole):
        items.extend(_card(x + 16 + k * 62, y + 52, code, dim=dim))
    status = "棄牌" if p.folded else p.last_action
    if p.hand_label and not p.folded:
        status = p.hand_label
    items.append(_text(x + 150, y + 60, status, 24, "FFD54F" if not dim else "757575"))
    if p.bet:
        items.append(_text(x + 150, y + 96, f"投入 {p.bet}", 20, "B0BEC5"))
    if dim:
        return items
    # 勝率條
    bar_x, bar_y, bar_w, bar_h = x + 16, y + 146, PANEL_W - 110, 24
    items.append(_rect(bar_x, bar_y, bar_w, bar_h, "37474F", layer=1))
    if p.equity > 0:
        fill = "66BB6A" if p.equity >= 0.5 else ("FFA726" if p.equity >= 0.25 else "EF5350")
        items.append(_rect(bar_x, bar_y, max(bar_w * p.equity, 2), bar_h, fill, layer=2))
    items.append(_text(x + PANEL_W - 16, bar_y - 2, f"{p.equity:.0%}", 24, name_color, align=9, bold=True))
    return items


def _scene_items(scene: Scene) -> list[tuple[int, str]]:
    items: list[tuple[int, str]] = []
    items.append(_text(WIDTH / 2, 22, "AI 德州撲克對戰場", 34, "FFD54F", align=8, bold=True))
    items.append(_text(WIDTH / 2, 66, scene.headline, 24, "FFFFFF", align=8))
    # 牌桌中央：公共牌與底池
    items.append(_rect(410, 230, 460, 170, "0B4D30", alpha=0x20))
    for k in range(5):
        code = scene.board[k] if k < len(scene.board) else None
        items.extend(_card(437 + k * 82, 250, code, scale=1.1))
    items.append(_text(WIDTH / 2, 352, f"底池 {scene.pot}", 28, "FFFFFF", align=8, bold=True))
    for seat, p in enumerate(scene.players):
        items.extend(_panel(seat, p, scene))
    if scene.speaker is not None and scene.thought:
        speaker = scene.players[scene.speaker].name
        items.append(_rect(140, 610, 1000, 80, "000000", alpha=0x50, layer=1))
        items.append(_text(WIDTH / 2, 650, f"【{speaker}的內心話】{scene.thought}", 28, "FFFFFF", align=5))
    return items


def scenes_to_ass(scenes: list[Scene]) -> str:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT},28,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    t = 0.0
    for scene in scenes:
        start, end = _ass_time(t), _ass_time(t + scene.duration)
        for layer, text in _scene_items(scene):
            lines.append(f"Dialogue: {layer},{start},{end},Default,,0,0,0,,{text}\n")
        t += scene.duration
    return "".join(lines)


def total_duration(scenes: list[Scene]) -> float:
    return sum(s.duration for s in scenes)


def render_video(scenes: list[Scene], out: Path, size: tuple[int, int] = (WIDTH, HEIGHT), fps: int = 24) -> Path:
    """用 ffmpeg 把場景渲染成 MP4。需要系統安裝支援 libass 的 ffmpeg。"""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("找不到 ffmpeg，請先安裝（需支援 libass）")
    duration = total_duration(scenes)
    with tempfile.TemporaryDirectory() as tmp:
        ass_path = Path(tmp) / "hand.ass"
        ass_path.write_text(scenes_to_ass(scenes), encoding="utf-8")
        cmd = [
            ffmpeg, "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c=0x0E5E3A:s={WIDTH}x{HEIGHT}:r={fps}:d={duration:.2f}",
            "-vf", f"ass={ass_path},scale={size[0]}:{size[1]}",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(out),
        ]
        subprocess.run(cmd, check=True)
    return out


def main(argv: list[str] | None = None) -> None:
    import json

    from poker_arena.bots import default_lineup
    from poker_arena.engine import play_match

    parser = argparse.ArgumentParser(description="把一手牌渲染成轉播影片")
    parser.add_argument("--json", help="python -m poker_arena --json 產生的比賽紀錄；不給就用 --seed 現打一場")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--hands", type=int, default=20, help="現打時的手數")
    parser.add_argument("--hand", type=int, nargs="+", default=[0], help="要渲染的手（從 0 起算），可多個")
    parser.add_argument("--out", default="hand.mp4")
    parser.add_argument("--ass", help="另外輸出 ASS 腳本（除錯用）")
    args = parser.parse_args(argv)

    if args.json:
        hands = json.loads(Path(args.json).read_text(encoding="utf-8"))["hands"]
    else:
        result = play_match(default_lineup(seed=args.seed), max_hands=args.hands, seed=args.seed)
        hands = [h.events for h in result.hands]
    scenes: list[Scene] = []
    for k in args.hand:
        scenes.extend(build_scenes(hands[k], seed=args.seed + k))
    if args.ass:
        Path(args.ass).write_text(scenes_to_ass(scenes), encoding="utf-8")
    render_video(scenes, Path(args.out))
    print(f"已輸出 {args.out}（{total_duration(scenes):.1f} 秒）")


if __name__ == "__main__":
    main()
