from logic_mcp.logic.commands import Commands
from logic_mcp.logic.faders import FaderTable
from logic_mcp.logic.plugins.cache import PluginCache
from tests.fake_assign import PLUGIN_LIST, compressor, make_assign_logic


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
