"""페이더 raw 값을 훑어 LCD의 dB 텍스트를 읽고 fader_db.json을 만든다. 값 표시 모드 필요.
사용: uv run python scripts/calibrate_fader.py"""
import json
from pathlib import Path

from logic_mcp.logic.faders import MAX_RAW, parse_db_text
from logic_mcp.mcu import protocol as P
from logic_mcp.server.main import build

OUT = Path("src/logic_mcp/logic/fader_db.json")
commands, surface = build()
surface.start()
try:
    assert commands.wait_ready(60).ok, "Logic이 서피스를 설치하지 않음"
    assert commands.configure().ok, "configure 실패"
    original = surface.state.strips[0].fader_raw
    points: list[list] = []
    for raw in list(range(0, MAX_RAW, 64)) + [MAX_RAW]:
        for msg in P.fader_move(0, raw):
            surface.send(msg)
        surface.wait_for(lambda s: abs(s.strips[0].fader_raw - raw) <= 32, 0.8)
        surface.wait_settled(0.5)
        db = parse_db_text(surface.state.strips[0].value_text)
        echoed = surface.state.strips[0].fader_raw
        print(raw, echoed, db)
        if db is not None:
            points.append([echoed, None if db == float("-inf") else db])
    for msg in P.fader_move(0, original):
        surface.send(msg)
    dedup = {}
    for r, d in points:
        dedup[r] = d
    OUT.write_text(json.dumps({"source": "scripts/calibrate_fader.py, Logic Pro 12.0.1",
                               "points": [[r, dedup[r]] for r in sorted(dedup)]}, indent=0))
    print(f"{len(dedup)}점 → {OUT}")
finally:
    surface.stop()
