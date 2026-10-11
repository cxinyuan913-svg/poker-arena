import json
import shutil

import pytest

from poker_arena.cards import Deck, parse_cards
from poker_arena.engine import ActionType, Decision, play_hand
from poker_arena.video import build_scenes, render_video, scenes_to_ass, total_duration


class Caller:
    def __init__(self, name: str, first: Decision | None = None) -> None:
        self.name = name
        self.first = first

    def decide(self, view):
        if self.first is not None:
            d, self.first = self.first, None
            return d
        return Decision(ActionType.CALL, thought=f"{self.name} 跟注")


def sample_hand(fold_first: bool = False) -> list[dict]:
    # 座位 1、2、0 依序拿底牌；座位 0 拿 AA 並在河牌成三條
    deck = Deck.stacked(parse_cards("Kc Kd 7c 2d Ac Ad 9h 5s 3c Jd As"))
    first = Decision(ActionType.FOLD, thought="不玩") if fold_first else None
    bots = [Caller("甲"), Caller("乙", first), Caller("丙")]
    record = play_hand(bots, [500, 500, 500], button=0, small_blind=5, big_blind=10, seed=None, deck=deck)
    # 模擬 JSON 存讀（字典鍵變成字串）
    return json.loads(json.dumps(record.events))


def test_scenes_track_state_and_equity() -> None:
    scenes = build_scenes(sample_hand(), equity_iterations=300, seed=1)
    assert scenes[0].headline.endswith("發牌")
    for scene in scenes:
        live = [p for p in scene.players if not p.folded]
        assert sum(p.equity for p in live) == pytest.approx(1.0, abs=0.02)
    river = [s for s in scenes if s.street == "river"][0]
    # 河牌已確定：座位 0 三條 A 必勝
    assert river.players[0].equity == 1.0
    final = scenes[-1]
    assert final.winners == [0]
    assert final.players[0].stack == 520
    assert final.pot == 0
    assert any(s.thought == "甲 跟注" and s.speaker == 0 for s in scenes)


def test_folded_player_has_no_equity() -> None:
    scenes = build_scenes(sample_hand(fold_first=True), equity_iterations=200, seed=1)
    after_fold = [s for s in scenes if s.thought == "不玩"][0]
    assert after_fold.players[1].folded and after_fold.players[1].equity == 0.0


def test_ass_contains_layout() -> None:
    scenes = build_scenes(sample_hand(), equity_iterations=100, seed=1)
    ass = scenes_to_ass(scenes)
    assert ass.startswith("[Script Info]")
    assert "PlayResX: 1280" in ass
    assert "內心話" in ass and "A\\N♣" in ass and "三條" in ass
    assert ass.count("Dialogue:") > 50
    assert total_duration(scenes) > 10


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="需要 ffmpeg")
def test_render_video(tmp_path) -> None:
    scenes = build_scenes(sample_hand(fold_first=True), equity_iterations=100, seed=1)[:3]
    out = render_video(scenes, tmp_path / "hand.mp4", size=(320, 180), fps=5)
    assert out.stat().st_size > 1000
