# CLAUDE.md

給本專案每個階段的工作階段閱讀。

## 專案目標

「AI 德州撲克對戰場」：多個演算法 AI 玩家互相對戰，並自動產生轉播風格的影片（底牌視角、即時勝率條、AI 內心話字幕）。

## 路線圖

- **階段 0：基礎**（已完成）— Card / Deck、7 選 5 牌型判斷與比牌、蒙地卡羅勝率計算、測試。
- **階段 1：遊戲引擎與 4 種機器人** — 緊兇、鬆凶、跟注站、機率派。每個決策都要記錄「內心話」。
- **階段 2：影片產生器** — 底牌視角、即時勝率條、內心話字幕。
- **階段 3：精華剪輯與進化系統。**

## 目前結構

- `poker_arena/cards.py` — `Card`（rank 2..14，suit `s/h/d/c`）、`parse_cards("As Kd")`、`Deck(seed=..., exclude=...)`
- `poker_arena/evaluator.py` — `evaluate_five`、`best_hand`（5~7 張選最佳 5 張）、`find_winners`（回傳贏家索引，多人即平手分池）；`HandRank` 可直接比較大小
- `poker_arena/equity.py` — `calculate_equity(hole_cards, board, iterations, seed)` 回傳每位玩家的 `EquityResult(win, tie)`
- `tests/` — pytest，執行：`python -m pytest`

## 程式慣例

- Python 3.11+，所有函式都要有型別標註。
- 除 pytest 外不使用第三方套件（除非該階段明確需要並經同意）。
- 所有隨機性都必須可用 seed 重現：使用 `random.Random(seed)` 實例，不要用全域 `random`。
- 整個測試套件要能在 1 分鐘內跑完（蒙地卡羅測試請控制迭代次數）。

## 預算原則

本專案預算很有限。每個階段只做該階段的事，不要預先實作未來階段，不要加額外功能，不做非必要的效能優化。遇到需要決定的事情，採用最簡單合理的做法，並在總結中說明。
