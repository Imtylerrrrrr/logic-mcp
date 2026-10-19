from logic_mcp.logic.assign import overlay_param_name
from logic_mcp.logic.commands import Commands
from logic_mcp.logic.faders import FaderTable
from logic_mcp.logic.plugins.cache import PluginCache
from tests.fake_assign import PLUGIN_LIST, compressor, make_assign_logic, with_dash_cells


def make(tmp_path):
    surface, fake, logic = make_assign_logic()
    cache = PluginCache("fake", list(PLUGIN_LIST), [], {}, {}, None, tmp_path / "plugins-fake.json")
    cmds = Commands(surface, FaderTable.load(), sleep=logic.sleep, logic_running=lambda: True, plugin_cache=cache)
    return cmds, surface, fake, logic, cache


def test_calibrate_collects_names_maps_and_options(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    r = cmds.plugin.calibrate(strip=1, number=None, slot=2)
    assert r.verified == "verified" and r.after["plugin"] == "Compressor" and r.after["pages"] == 3
    items = {it["index"]: it for it in r.after["items"]}
    assert len(items) == 20 and all(it["name"] for it in items.values())
    assert items[2]["name"] == "Threshold" and items[2]["map"]["type"] == "linear"
    assert abs(items[2]["map"]["lo"] - -60.0) < 0.5 and abs(items[2]["map"]["hi"] - 0.0) < 0.5
    assert items[3]["map"]["type"] == "linear" and abs(items[3]["map"]["lo"] - 1.0) < 0.1          # Ratio `2.1:1`
    assert items[1] == {"index": 1, "short": "CirTyp", "name": "Circuit Type",
                        "map": {"type": "enum", "options": ["PltDig", "StdVCA", "StdFET", "ClsVCA"]}}
    assert items[6]["map"] == {"type": "enum", "options": ["Off", "On"]}                           # 시작값 On이어도 처음부터
    assert items[8]["map"] is None                                                                 # AutGai: `Off`/`-12dB`/`0dB` 혼합은 매핑 못 함
    assert r.after["enums"] == 8 and r.after["probed"] >= 10
    assert cache.param_table("Compressor")["items"][1]["name"] == "Threshold" and cache.path.exists()
    assert surface.state.view.kind == "pan" and not surface.state.assignment.flip and logic.name_mode is False


def test_calibrate_on_empty_slot_is_skipped(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    r = cmds.plugin.calibrate(strip=1, number=None, slot=3)
    assert r.verified == "skipped" and "비어" in r.note and surface.state.view.kind == "pan"


def test_calibrate_names_come_only_from_ticks_that_changed_the_lcd(tmp_path):       # 리뷰 I3
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    logic.no_overlay_on_nochange = True                     # 끝값 무변화 틱은 오버레이를 그리지 않는다
    params = logic.tracks[0].params[2]
    assert params[0].value == 0 and params[13].value == params[13].hi   # CirTyp 첫 선택지, Mix 최댓값
    r = cmds.plugin.calibrate(strip=1, number=None, slot=2)
    assert r.verified == "verified"
    items = {it["index"]: it for it in r.after["items"]}
    assert items[1]["name"] == "Circuit Type"                 # 첫 선택지: -1 무반응 → +1 틱의 오버레이에서(정착 1행 조각 아님)
    assert items[14]["name"] == "Mix"                          # 최댓값: +1 무반응 → -1 틱의 오버레이에서
    true_names = {p.short: p.name for p in compressor()}              # 3페이지는 오른쪽 정렬이라 index가 아니라 축약명으로 맞춘다
    for it in items.values():
        assert it["name"] in (true_names[it["short"]], None), it


def test_dash_cells_are_not_params(tmp_path):                        # 실기 10차: 빈 칸을 1행 `-`(2행 공백)로 보이는 플러그인
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Chorus")
    logic.tracks[0].params[2] = with_dash_cells(logic.tracks[0].params[2], 2)      # 열 3·4가 `-`
    r = cmds.plugin.params(1, None, 2)
    assert r.verified == "verified" and [p["index"] for p in r.after["params"]] == [1, 2, 3]
    r = cmds.plugin.calibrate(strip=1, number=None, slot=2)
    assert r.verified == "verified" and [it["index"] for it in r.after["items"]] == [1, 2, 3]
    assert [it["short"] for it in cache.param_table("Chorus")["items"]] == ["Drive", "Tone", "Output"]


def test_calibrate_names_drop_neighbor_shorts_under_narrow_overlay(tmp_path):    # 실기 10차: 이름 오버레이는 1행 2~3열만 덮는다
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    logic.narrow_name_overlay = True
    r = cmds.plugin.calibrate(strip=1, number=None, slot=2)
    assert r.verified == "verified"
    items = {it["index"]: it for it in r.after["items"]}
    assert items[1]["name"] == "Circuit Type" and items[2]["name"] == "Threshold"      # 옛 21칸 창: `Circuit Type  Ratio`
    assert items[7]["name"] == "Make Up" and items[8]["name"] == "Auto Gain"           # 열 7·8: 창 앞의 `AutRel`이 섞이던 곳
    true_names = {p.short: p.name for p in compressor()}
    assert {it["short"]: it["name"] for it in items.values()} == true_names            # 모든 이름이 그 파라미터의 이름 그대로


def _row(shorts: str) -> str:
    return "".join(x.ljust(7) for x in shorts.split())


EQ1 = _row("LoCutS LoShGa Pea1Ga Pea2Ga Pea3Ga Pea4Ga HiShGa HiCutS")
EQ2 = _row("LoCutF LoShF Peak1F Peak2F Peak3F Peak4F HiShF HiCutF")
CMP = _row("CirTyp Thrs Ratio Attack Rel AutRel MakeUp AutGai")


def test_overlay_param_name_cases():                                   # 실기 10차 관찰: (1행, 열, 덧쓴 위치, 덧쓴 글자, 옛 21칸 창이 읽은 값, 기대)
    cases = [
        (EQ1, 0, 0, "Low Cut Slope".ljust(14), "Low Cut Slope Pea1Ga", "Low Cut Slope"),
        (EQ1, 1, 7, "Low Shelf Gain".ljust(21), "Low Shelf Gain", "Low Shelf Gain"),
        (CMP, 0, 0, "Circuit Type".ljust(14), "Circuit Type  Ratio", "Circuit Type"),
        (CMP, 1, 7, "Threshold".ljust(14), "Threshold     Attack", "Threshold"),
        (CMP, 3, 21, "Attack".ljust(14), "Attack        AutRel", "Attack"),
        (CMP, 6, 42, "Make Up".ljust(14), "AutRel Make Up", "Make Up"),
        (CMP, 7, 42, "    Auto Gain ", "AutRel     Auto Gain", "Auto Gain"),       # 오른쪽 끝: 46~54칸
        (EQ2, 6, 35, "High Shelf Frequency ", "High Shelf Frequency", "High Shelf Frequency"),
    ]
    for header, col, at, text, seen, want in cases:
        assert len(header) == 56
        row = header[:at] + text + header[at + len(text):]
        start = min(col * 7, 35)
        assert row[start:start + 21].strip() == seen, (col, seen)          # 관찰을 재현하는 행인지
        assert overlay_param_name(header, row, col) == want, (col, want)
    assert overlay_param_name(CMP, CMP, 2) == ""                        # 무변화
