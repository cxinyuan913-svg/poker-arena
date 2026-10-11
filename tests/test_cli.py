import json

from poker_arena.__main__ import main


def test_cli_runs_and_writes_json(tmp_path, capsys) -> None:
    out = tmp_path / "match.json"
    main(["--hands", "3", "--seed", "1", "--iterations", "20", "--json", str(out)])
    text = capsys.readouterr().out
    assert "第 1 手" in text and "💭" in text and "最終籌碼" in text
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["players"]) == 4 and sum(data["final_stacks"]) == 4000
    assert data["hands"][0][0]["type"] == "hand_start"
