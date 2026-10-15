import pytest

from logic_mcp.logic.commands import Commands
from logic_mcp.logic.faders import FaderTable
from logic_mcp.logic.plugins.cache import PluginCache
from logic_mcp.mcu import protocol as P
from tests.fake_assign import PLUGIN_LIST, make_assign_logic


def make(tmp_path):
    surface, fake, logic = make_assign_logic()
    cache = PluginCache("fake", list(PLUGIN_LIST), [], {}, {}, None, tmp_path / "plugins-fake.json")
    cmds = Commands(surface, FaderTable.load(), sleep=logic.sleep, logic_running=lambda: True, plugin_cache=cache)
    return cmds, surface, fake, logic, cache


def test_list_inventory_whole_bank(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(1, "Channel EQ")
    logic.tracks[2].insert(3, "Compressor")
    cache.learn_abbrev("Compre", "Compressor")
    r = cmds.plugin.list(None, None)
    assert r.verified == "verified"
    t = r.after["tracks"]
    assert t["15"]["1"] == {"text": "Channe", "name": None} and t["15"]["2"] is None
    assert t["17"]["3"] == {"text": "Compre", "name": "Compressor"}
    assert len(t) == 8 and len(t["15"]) == 15
    assert cmds.plugin.inventory == t and surface.state.view.kind == "pan"


def test_list_single_track(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[4].insert(2, "Limiter")
    r = cmds.plugin.list(None, 19)
    assert list(r.after["tracks"]) == ["19"] and r.after["tracks"]["19"]["2"]["text"] == "Limite"


def test_params_reads_all_pages_learns_and_keeps_values(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    r = cmds.plugin.params(strip=1, number=None, slot=2)
    assert r.verified == "verified" and r.after["plugin"] == "Compressor" and r.after["pages"] == 2
    ps = r.after["params"]
    assert len(ps) == 10
    assert ps[0] == {"index": 1, "short": "Thresh", "name": None, "value": -20.0, "text": "-20.0 d"}   # 7칸 잘림
    assert ps[9]["short"] == "Limit" and ps[9]["text"] == "Off" and ps[9]["value"] is None
    assert cache.abbrev["Compre"] == "Compressor" and cache.param_table("Compressor")["pages"] == 2
    assert cache.param_table("Compressor")["items"][9]["short"] == "Limit" and cache.path.exists()
    assert logic.tracks[0].params[2][0].value == -20.0           # 같은 플러그인 재확인이 값을 리셋하지 않음
    assert surface.state.view.kind == "pan" and logic.name_mode is False


def test_params_empty_slot_skipped(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    r = cmds.plugin.params(1, None, 3)
    assert r.verified == "skipped" and "비어" in r.note and surface.state.view.kind == "pan"


def test_params_cancels_stale_preselect_before_press(tmp_path):      # Review Focus 3
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(1, "Channel EQ")
    cmds.modes.enter("plugin_mixer")
    cmds.modes.tick(1, 6)                                           # 스트립 2에 미리 선택(3항목) 잔류
    assert logic.pre
    r = cmds.plugin.params(1, None, 1)
    assert r.verified == "verified" and r.after["plugin"] == "Channel EQ"
    assert logic.tracks[1].inserts[1] is None                       # 스트립 2에 아무것도 삽입되지 않음


def test_get_and_set_by_index_and_name(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    g = cmds.plugin.get(1, None, 2, 1)
    assert g.verified == "verified" and g.after["value"] == -20.0 and g.after["short"] == "Thresh"
    s = cmds.plugin.set(1, None, 2, "Thresh", -30.0)
    assert s.verified == "verified" and logic.tracks[0].params[2][0].value == -30.0
    assert s.before["value"] == -20.0 and s.after["value"] == -30.0
    assert cache.param_table("Compressor")["items"][0]["map"] == {"type": "linear", "lo": -60.0, "hi": 0.0}  # 프로빙 학습
    s2 = cmds.plugin.set(1, None, 2, 10, "On")                      # 2페이지 열거형(Limiter)
    assert s2.verified == "verified" and logic.tracks[0].params[2][9].value == 1 and s2.after["text"] == "On"
    assert surface.state.view.kind == "pan" and not surface.state.assignment.flip


def test_set_uses_known_mapping_without_probe(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    cache.params["Compressor"] = {"pages": 2, "items": [
        {"index": 1, "short": "Thresh", "name": "Threshold", "map": {"type": "linear", "lo": -60.0, "hi": 0.0}}]}
    logic.tracks[0].insert(2, "Compressor")
    n0 = len(fake.sent)
    s = cmds.plugin.set(1, None, 2, "Threshold", -12.0)
    assert s.ok and logic.tracks[0].params[2][0].value == -12.0 and s.after["name"] == "Threshold"
    assert len([m for m in fake.sent[n0:] if m[0] == 0xE0]) == 1   # 프로빙(2회) 없이 페이더 1회


def test_param_missing_or_ambiguous(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    r = cmds.plugin.set(1, None, 2, "Zzz", 1.0)
    assert r.verified == "skipped" and "Thresh" in r.note and surface.state.view.kind == "pan"
    assert cmds.plugin.get(1, None, 2, 11).verified == "skipped"     # 인덱스 범위 밖
    assert cmds.plugin.get(1, None, 16, 1).verified == "skipped"     # 슬롯 범위 밖


def test_insert_by_name_rewinds_and_confirms(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    r = cmds.plugin.insert(strip=2, number=None, slot=1, plugin="compressor")
    assert r.verified == "verified" and logic.tracks[1].inserts[1] == "Compressor"
    assert r.after == {"slot": 1, "plugin": "Compressor", "abbrev": "Compre", "replaced": None}
    assert cache.abbrev["Compre"] == "Compressor" and surface.state.view.kind == "pan" and logic.selected == 0


def test_insert_refuses_occupied_then_replaces_with_flag(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[1].insert(1, "Channel EQ")
    r = cmds.plugin.insert(2, None, 1, "Compressor")
    assert r.verified == "skipped" and "replace" in r.note and logic.tracks[1].inserts[1] == "Channel EQ"
    r = cmds.plugin.insert(2, None, 1, "Compressor", replace=True)
    assert r.verified == "verified" and logic.tracks[1].inserts[1] == "Compressor" and r.after["replaced"] == "Channe"


def test_insert_unknown_or_ambiguous_name_sends_nothing(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    n = len(fake.sent)
    r = cmds.plugin.insert(2, None, 1, "Zebra")
    assert r.verified == "skipped" and "scan" in r.note
    r = cmds.plugin.insert(2, None, 1, "EQ")
    assert r.verified == "skipped" and "Parametric EQ" in r.note and "Channel EQ" in r.note
    assert len(fake.sent) == n


def test_remove_and_bypass(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(1, "Channel EQ")
    r = cmds.plugin.bypass(1, None, 1, True)
    assert r.verified == "verified" and 1 in logic.tracks[0].bypassed and r.after["text"].startswith("*")
    assert cmds.plugin.bypass(1, None, 1, True).verified == "skipped"
    assert cmds.plugin.bypass(1, None, 1, False).verified == "verified" and not logic.tracks[0].bypassed
    r = cmds.plugin.remove(1, None, 1)
    assert r.verified == "verified" and logic.tracks[0].inserts[1] is None and logic.tracks[0].eq is None
    assert cmds.plugin.remove(1, None, 1).verified == "skipped"
    assert cmds.plugin.bypass(1, None, 1, True).verified == "skipped"
    assert surface.state.view.kind == "pan"


def test_scan_builds_list_without_inserting(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    r = cmds.plugin.scan()
    assert r.verified == "verified" and r.after["count"] == len(PLUGIN_LIST) and r.after["slot"] == 1
    assert cache.items == PLUGIN_LIST and cache.source == "scan" and cache.path.exists() and cache.scanned_at
    assert all(v is None for t in logic.tracks for v in t.inserts.values())
    assert surface.state.view.kind == "pan"
    assert cmds.plugin.scan().verified == "skipped"
    assert cmds.plugin.scan(force=True).verified == "verified"


def test_scan_needs_an_empty_slot(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    for t in logic.tracks:
        for i in range(1, 16):
            t.insert(i, "Tuner")
    r = cmds.plugin.scan()
    assert r.verified == "skipped" and "빈 슬롯" in r.note and surface.state.view.kind == "pan"
