# poker-arena
AI 德州撲克對戰場與自動轉播影片

四位個性不同的演算法 AI（緊兇、鬆凶、跟注站、機率派）互相對戰，每個決策都附帶「內心話」，
並自動產生轉播風格影片（底牌視角、即時勝率條、內心話字幕）、精華剪輯，以及用基因演算法進化出新的 AI。

```bash
python -m poker_arena --hands 20 --seed 1 --json match.json        # 文字轉播
python -m poker_arena.video --seed 1 --hand 0 1 --out hand.mp4      # 渲染指定手牌
python -m poker_arena.highlights --seed 1 --top 3 --out best.mp4    # 精華剪輯
python -m poker_arena.evolve --generations 6 --population 8         # 進化
python -m pytest                                                    # 測試
```

需求：Python 3.11+；影片需要系統安裝 ffmpeg（含 libass）與中文字型（WenQuanYi Zen Hei）。
