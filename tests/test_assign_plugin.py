import pytest

from logic_mcp.logic.commands import Commands
from logic_mcp.logic.faders import FaderTable
from logic_mcp.logic.plugins.cache import PluginCache
from logic_mcp.mcu import protocol as P
from tests.fake_assign import PLUGIN_LIST, Param, Track, make_assign_logic


def make(tmp_path, tracks=None):
    surface, fake, logic = make_assign_logic(tracks)
    cache = PluginCache("fake", list(PLUGIN_LIST), [], {}, {}, None, tmp_path / "plugins-fake.json")
    cmds = Commands(surface, FaderTable.load(), sleep=logic.sleep, logic_running=lambda: True, plugin_cache=cache)
    return cmds, surface, fake, logic, cache


def turns(msgs: list[bytes]) -> list[bytes]:
    return [m for m in msgs if m[0] == 0xB0 and 0x10 <= m[1] <= 0x17]


def pushes(msgs: list[bytes]) -> list[int]:
    return [i for i, m in enumerate(msgs) if m[0] == 0x90 and P.Note.VPOT_PUSH <= m[1] < P.Note.VPOT_PUSH + 8 and m[2]]


def test_list_inventory_whole_bank(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(1, "Channel EQ")
    logic.tracks[2].insert(3, "Compressor")
    cache.learn_abbrev("Comprs", "Compressor")
    cmds.strips.follows(cmds.modes, surface.state, 0)           # 스트립 종류 판별(TRACK 메뉴 누름)은 미리 끝내 둔다
    n0 = len(fake.sent)
    r = cmds.plugin.list(None, None)
    assert r.verified == "verified"
    t = r.after["tracks"]
    assert t["15"]["1"] == {"text": "Cha EQ", "name": "Channel EQ"} and t["15"]["2"] is None   # 모르는 축약은 -1 틱으로 드러냄
    assert t["17"]["3"] == {"text": "Comprs", "name": "Compressor"}
    assert len(t) == 8 and all(len(row) == 8 for row in t.values())
    assert cache.abbrev["Cha EQ"] == "Channel EQ" and cache.path.exists()
    assert turns(fake.sent[n0:]) == [P.vpot_turn(0, -1)] and not pushes(fake.sent[n0:])          # +1(다음 항목)은 보내지 않음
    assert logic.tracks[0].inserts[1] == "Channel EQ" and logic.tracks[2].inserts[3] == "Compressor"
    assert not logic.pre and cmds.plugin.inventory == t and surface.state.view.kind == "pan" and logic.selected == 0


def test_list_single_track(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[4].insert(2, "Limiter")
    r = cmds.plugin.list(None, 19)
    assert list(r.after["tracks"]) == ["19"]
    assert r.after["tracks"]["19"]["2"] == {"text": "Limite", "name": "Limiter"}
    assert logic.tracks[4].inserts[2] == "Limiter" and surface.state.view.kind == "pan"


def test_params_reads_all_pages_learns_and_keeps_values(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    n0 = len(fake.sent)
    r = cmds.plugin.params(strip=1, number=None, slot=2)
    assert r.verified == "verified" and r.after["plugin"] == "Compressor" and r.after["pages"] == 3
    assert r.after["abbrev"] == "Comprs"
    ps = r.after["params"]
    assert len(ps) == 20
    assert ps[1] == {"index": 2, "short": "Thrs", "name": None, "value": -20.0, "text": "-20.0"}
    assert ps[10]["short"] == "LimrOn" and ps[10]["text"] == "Off" and ps[10]["value"] is None
    assert cache.abbrev["Comprs"] == "Compressor" and cache.param_table("Compressor")["pages"] == 3
    assert cache.param_table("Compressor")["items"][10]["short"] == "LimrOn" and cache.path.exists()
    assert turns(fake.sent[n0:]) == []                              # 편집 뷰 열기는 틱 없이 누르기만
    assert logic.tracks[0].params[2][1].value == -20.0              # 값 보존
    assert surface.state.view.kind == "pan" and logic.name_mode is False


def test_params_long_track_name_reads_name_from_page1_and_pages_from_page2(tmp_path):   # 실측 L
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].name = "Deluxe Classic"
    logic.tracks[0].insert(2, "Compressor")
    r = cmds.plugin.params(1, None, 2)
    assert r.verified == "verified" and r.after["plugin"] == "Compressor" and r.after["pages"] == 3
    assert len(r.after["params"]) == 20 and r.after["params"][10]["short"] == "LimrOn"


def test_params_single_page_plugin_with_truncated_header(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].name = "Deluxe Classic"
    logic.tracks[0].insert(1, "Tuner")
    r = cmds.plugin.params(1, None, 1)
    assert r.verified == "verified" and r.after["plugin"] == "Tuner" and r.after["pages"] == 1
    assert [p["short"] for p in r.after["params"]] == ["Drive", "Tone", "Output"]


def test_params_empty_slot_skipped(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    r = cmds.plugin.params(1, None, 3)
    assert r.verified == "skipped" and "비어" in r.note and surface.state.view.kind == "pan"


def test_params_cancels_stale_preselect_before_press(tmp_path):      # Review Focus 3(믹서 뷰 잔류)
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(1, "Channel EQ")
    cmds.modes.enter("plugin_mixer")
    cmds.modes.tick(1, 6)                                           # 스트립 2에 미리 선택(3항목) 잔류
    assert logic.pre
    r = cmds.plugin.params(1, None, 1)
    assert r.verified == "verified" and r.after["plugin"] == "Channel EQ"
    assert logic.tracks[1].inserts[1] is None                       # 스트립 2에 아무것도 삽입되지 않음


def test_params_cancels_stale_preselect_in_channel_view_via_pan(tmp_path):   # Review Focus 3(PL 잔류)
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(1, "Channel EQ")
    cmds.modes.focus(0)
    cmds.modes.enter("plugin_channel")
    cmds.modes.tick(1, 6)                                           # 같은 트랙 슬롯 2에 미리 선택 잔류(SELECT로는 취소 안 됨)
    assert logic.pre == {1: 6}
    n0 = len(fake.sent)
    r = cmds.plugin.params(1, None, 1)
    assert r.verified == "verified" and r.after["plugin"] == "Channel EQ"
    sent = fake.sent[n0:]
    first_pan = sent.index(P.button_down(P.Note.PAN))
    assert first_pan < pushes(sent)[0]                              # PAN 경유로 취소한 뒤에 누름
    assert logic.tracks[0].inserts[2] is None


def test_get_and_set_by_index_and_name(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    g = cmds.plugin.get(1, None, 2, 2)
    assert g.verified == "verified" and g.after["value"] == -20.0 and g.after["short"] == "Thrs"
    s = cmds.plugin.set(1, None, 2, "Thrs", -30.0)
    assert s.verified == "verified" and logic.tracks[0].params[2][1].value == -30.0
    assert s.before["value"] == -20.0 and s.after["value"] == -30.0
    assert cache.param_table("Compressor")["items"][1]["map"] == {"type": "linear", "lo": -60.0, "hi": 0.0}  # 프로빙 학습
    s2 = cmds.plugin.set(1, None, 2, 11, "On")                      # 2페이지 열거형(LimrOn)
    assert s2.verified == "verified" and logic.tracks[0].params[2][10].value == 1 and s2.after["text"] == "On"
    assert surface.state.view.kind == "pan" and not surface.state.assignment.flip


def test_set_uses_known_mapping_without_probe(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    cache.params["Compressor"] = {"pages": 3, "items": [
        {"index": 2, "short": "Thrs", "name": "Threshold", "map": {"type": "linear", "lo": -60.0, "hi": 0.0}}]}
    logic.tracks[0].insert(2, "Compressor")
    n0 = len(fake.sent)
    s = cmds.plugin.set(1, None, 2, "Threshold", -12.0)
    assert s.ok and logic.tracks[0].params[2][1].value == -12.0 and s.after["name"] == "Threshold"
    assert len([m for m in fake.sent[n0:] if m[0] & 0xF0 == 0xE0]) == 1   # 프로빙(2회) 없이 페이더 1회


def test_param_missing_or_ambiguous(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    r = cmds.plugin.set(1, None, 2, "Zzz", 1.0)
    assert r.verified == "skipped" and "Thrs" in r.note and surface.state.view.kind == "pan"
    assert cmds.plugin.get(1, None, 2, 25).verified == "skipped"     # 인덱스 범위 밖


def test_slot_range_is_1_to_8(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    n = len(fake.sent)
    for call in (lambda: cmds.plugin.get(1, None, 9, 1), lambda: cmds.plugin.insert(1, None, 9, "Compressor"),
                 lambda: cmds.plugin.remove(1, None, 0), lambda: cmds.plugin.bypass(1, None, 15, True)):
        r = call()
        assert r.verified == "skipped" and "1-8" in r.note
    assert len(fake.sent) == n


def test_insert_by_name_rewinds_and_confirms(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    t0 = fake.now
    r = cmds.plugin.insert(strip=2, number=None, slot=1, plugin="compressor")
    assert r.verified == "verified" and logic.tracks[1].inserts[1] == "Compressor"
    assert r.after == {"slot": 1, "plugin": "Compressor", "abbrev": "Comprs", "replaced": None}
    assert cache.abbrev["Comprs"] == "Compressor" and surface.state.view.kind == "pan" and logic.selected == 0
    assert fake.now - t0 > 2.0                                       # 확정 뒤 ≈2초 늦게 뜨는 편집 뷰를 기다림(실측 K)


def test_insert_slot_8_reads_right_aligned_overlay(tmp_path):        # 실측 D: 7·8은 열 35~55에 오른쪽 정렬
    cmds, surface, fake, logic, cache = make(tmp_path)
    r = cmds.plugin.insert(1, None, 8, "Low Pass Filter")
    assert r.verified == "verified" and logic.tracks[0].inserts[8] == "Low Pass Filter"
    r = cmds.plugin.insert(1, None, 7, "Chorus")
    assert r.verified == "verified" and logic.tracks[0].inserts[7] == "Chorus"
    assert [k for k, v in logic.tracks[0].inserts.items() if v] == [7, 8]


def test_insert_refuses_occupied_then_replaces_with_flag(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[1].insert(1, "Channel EQ")
    r = cmds.plugin.insert(2, None, 1, "Compressor")
    assert r.verified == "skipped" and "replace" in r.note and logic.tracks[1].inserts[1] == "Channel EQ"
    r = cmds.plugin.insert(2, None, 1, "Compressor", replace=True)
    assert r.verified == "verified" and logic.tracks[1].inserts[1] == "Compressor" and r.after["replaced"] == "Cha EQ"


def test_insert_overlay_mismatch_never_presses(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.plugin_list = ["--", "Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta"]   # 설치 목록이 캐시와 다름
    cmds.strips.follows(cmds.modes, surface.state, 0)           # 스트립 종류 판별(TRACK 메뉴 누름)은 미리 끝내 둔다
    n0 = len(fake.sent)
    r = cmds.plugin.insert(1, None, 1, "Compressor")
    assert r.verified == "unverified" and "Zeta" in r.note and "scan" in r.note
    assert not pushes(fake.sent[n0:])                                # 확정 누름 없음
    assert all(v is None for v in logic.tracks[0].inserts.values())
    assert not logic.pre and surface.state.view.kind == "pan"       # leave가 미리 선택을 취소


def test_insert_steps_past_a_name_missing_from_the_cache_list(tmp_path):   # 재수집: 목록 위치 53에 'Rotor Cabinet'
    cmds, surface, fake, logic, cache = make(tmp_path)
    i = PLUGIN_LIST.index("Compressor")
    logic.plugin_list = PLUGIN_LIST[:i] + ["Rotor Cabinet"] + PLUGIN_LIST[i:]   # 캐시 목록에 빠진 항목이 목표 바로 앞
    r = cmds.plugin.insert(2, None, 1, "Compressor")
    assert r.verified == "verified" and logic.tracks[1].inserts[1] == "Compressor" and r.after["plugin"] == "Compressor"
    assert surface.state.view.kind == "pan"


def test_insert_unknown_or_ambiguous_name_sends_nothing(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    n = len(fake.sent)
    r = cmds.plugin.insert(2, None, 1, "EQ")
    assert r.verified == "skipped" and "Parametric EQ" in r.note and "Channel EQ" in r.note
    assert len(fake.sent) == n                                       # 모르는 이름은 접두 이름 탐색으로 감(아래 prefix_scan 테스트)


def test_insert_falls_back_to_name_scan_when_cache_order_differs(tmp_path):   # 실전 F1: 캐시 위치 58에 'Tremolo'
    cmds, surface, fake, logic, cache = make(tmp_path)
    i, j = PLUGIN_LIST.index("Channel EQ"), PLUGIN_LIST.index("Tuner")
    swapped = list(PLUGIN_LIST)
    swapped[i], swapped[j] = swapped[j], swapped[i]                  # 캐시의 Channel EQ 위치에 실제로는 다른 이름
    cache.bundled_list = swapped
    r = cmds.plugin.insert(1, None, 4, "Channel EQ")
    assert r.ok and r.verified == "verified" and r.note.startswith("name_scan:")
    assert logic.tracks[0].inserts[4] == "Channel EQ" and r.after["plugin"] == "Channel EQ"
    assert [k for k, v in logic.tracks[0].inserts.items() if v] == [4] and surface.state.view.kind == "pan"


def test_insert_name_scan_gives_up_without_pressing(tmp_path):        # Review Focus 1
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.plugin_list = [n for n in PLUGIN_LIST if n != "Channel EQ"]   # 캐시에는 있고 설치 목록에는 없음
    cmds.strips.follows(cmds.modes, surface.state, 0)           # 스트립 종류 판별(TRACK 메뉴 누름)은 미리 끝내 둔다
    n0 = len(fake.sent)
    r = cmds.plugin.insert(1, None, 4, "Channel EQ")
    assert not r.ok and r.verified == "unverified" and "이름 탐색" in r.note and "scan" in r.note
    assert not pushes(fake.sent[n0:])                                # 되감기·탐색 뒤에도 확정 누름 없음
    assert all(v is None for v in logic.tracks[0].inserts.values())
    assert not logic.pre and surface.state.view.kind == "pan"


def test_insert_unknown_name_uses_prefix_scan(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.plugin_list = PLUGIN_LIST + ["Tape Delay"]                 # 캐시 목록에 없는 플러그인
    r = cmds.plugin.insert(1, None, 4, "Tape De")
    assert r.ok and r.verified == "verified" and r.note.startswith("name_scan:")
    assert r.after["plugin"] == "Tape Delay" and logic.tracks[0].inserts[4] == "Tape Delay"
    cmds.strips.follows(cmds.modes, surface.state, 1)
    n0 = len(fake.sent)
    r = cmds.plugin.insert(2, None, 1, "Zebra")                      # 어디에도 없는 이름: 탐색은 하되 누르지 않는다
    assert r.verified == "unverified" and "scan" in r.note and "Zebra" in r.note
    assert not pushes(fake.sent[n0:]) and all(v is None for v in logic.tracks[1].inserts.values())
    assert surface.state.view.kind == "pan"


def test_remove_and_bypass(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(1, "Channel EQ")
    r = cmds.plugin.bypass(1, None, 1, True)
    assert r.verified == "verified" and 1 in logic.tracks[0].bypassed and r.after["text"] == "*Cha E"   # `*` + 5자(실측 N)
    assert cmds.plugin.bypass(1, None, 1, True).verified == "skipped"
    assert cmds.plugin.bypass(1, None, 1, False).verified == "verified" and not logic.tracks[0].bypassed
    r = cmds.plugin.remove(1, None, 1)
    assert r.verified == "verified" and logic.tracks[0].inserts[1] is None and logic.tracks[0].eq is None
    assert r.before == {"slot": 1, "text": "Cha EQ"} and r.after == {"slot": 1, "text": "--"}
    assert cmds.plugin.remove(1, None, 1).verified == "skipped"
    assert cmds.plugin.bypass(1, None, 1, True).verified == "skipped"
    assert surface.state.view.kind == "pan"


def test_scan_builds_list_without_inserting(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    r = cmds.plugin.scan()
    assert r.verified == "verified" and r.after["count"] == len(PLUGIN_LIST) and r.after["slot"] == 1
    assert cache.items == PLUGIN_LIST and cache.source == "scan" and cache.path.exists() and cache.scanned_at   # `(s/s)` 접미는 뗌
    assert all(v is None for t in logic.tracks for v in t.inserts.values())
    assert surface.state.view.kind == "pan"
    assert cmds.plugin.scan().verified == "skipped"
    assert cmds.plugin.scan(force=True).verified == "verified"


def test_scan_rereads_in_place_when_overlay_is_late(tmp_path):        # 재수집: 오버레이가 늦은 항목이 목록에서 빠졌다
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.late_preselect_items = {7, 11}                            # Channel EQ, Space Designer
    r = cmds.plugin.scan(force=True)
    assert r.verified == "verified" and cache.items == PLUGIN_LIST and not logic.late_preselect_items
    assert all(v is None for t in logic.tracks for v in t.inserts.values())


def test_scan_survives_dropped_overlay_writes(tmp_path):              # 실측 scan_diag: 틱 하나의 오버레이 쓰기가 안 온다
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.drop_preselect_at = {13, 20, 21}                          # Channel EQ 첫 위치, Noise Gate 둘째 위치 + Space Designer 첫 위치(연속 무변화 2틱)
    r = cmds.plugin.scan(force=True)
    assert r.verified == "verified" and cache.items == PLUGIN_LIST and r.after["count"] == len(PLUGIN_LIST)
    assert all(v is None for t in logic.tracks for v in t.inserts.values()) and surface.state.view.kind == "pan"


def test_scan_needs_an_empty_slot(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    for t in logic.tracks:
        for i in range(1, 16):
            t.insert(i, "Tuner")
    r = cmds.plugin.scan()
    assert r.verified == "skipped" and "빈 슬롯" in r.note and surface.state.view.kind == "pan"


def test_params_last_page_overlap_removed(tmp_path):                 # 실측 W
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    r = cmds.plugin.params(1, None, 2)
    ps = r.after["params"]
    assert len(ps) == 20 and [p["index"] for p in ps] == list(range(1, 17)) + [21, 22, 23, 24]
    pairs = [(p["short"], p["text"]) for p in ps]
    assert all(a != b for a, b in zip(pairs, pairs[1:]))
    assert [p["short"] for p in ps[16:]] == ["Mode", "Freq", "Q", "Gain"]


def test_get_mix_is_unique_after_overlap_removal(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    g = cmds.plugin.get(1, None, 2, "Mix")
    assert g.verified == "verified" and g.after["index"] == 14 and g.after["text"] == "100.0%"


def test_get_index_21_moves_to_page_3(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    g = cmds.plugin.get(1, None, 2, 21)
    assert g.verified == "verified" and g.after["short"] == "Mode" and g.after["text"] == "LP"


def test_params_drops_stale_overlap_entries_keeps_learned_map(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    thrs_map = {"type": "linear", "lo": -60.0, "hi": 0.0}
    cache.params["Compressor"] = {"pages": 3, "items": [
        {"index": i, "short": f"S{i}", "name": None, "map": thrs_map if i == 2 else None} for i in range(1, 25)]}
    r = cmds.plugin.params(1, None, 2)
    items = cache.param_table("Compressor")["items"]
    assert [x["index"] for x in items] == list(range(1, 17)) + [21, 22, 23, 24]
    assert items[1]["short"] == "Thrs" and items[1]["map"] == thrs_map
    assert len(r.after["params"]) == 20


@pytest.mark.parametrize("value", [24, "24", 24.0])
def test_set_numeric_input_on_enum_param_takes_enum_path(tmp_path, value):       # 리뷰 I3: 번들 Channel EQ LoCutS는 enum 맵
    cmds, surface, fake, logic, cache = make(tmp_path)
    cache.params.update(PluginCache.load(version="t", user_dir=tmp_path).params)
    logic.tracks[0].insert(1, "Channel EQ")
    s = cmds.plugin.set(1, None, 1, "LoCutS", value)
    assert s.ok and s.verified == "verified" and s.after["text"].startswith("24")
    assert logic.tracks[0].eq[0][1].options[int(logic.tracks[0].eq[0][1].value)] == "24"


def test_plugin_value_error_returns_skipped_not_exception(tmp_path):               # 리뷰 I3
    cmds, surface, fake, logic, cache = make(tmp_path)
    cache.params.update(PluginCache.load(version="t", user_dir=tmp_path).params)
    logic.tracks[0].insert(1, "Channel EQ")
    s = cmds.plugin.set(1, None, 1, "LoCutS", "13")                                # 선택지 밖
    assert not s.ok and surface.state.view.kind == "pan"


def test_failed_probe_restores_original_position(tmp_path):                        # 리뷰 I4: 양 끝이 숫자가 아닌 파라미터
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    thr = Param("Thrs", "Threshold", "linear", -60.0, 0.0, -20.0, unit="n1", step=0.5, ends=("Min", "Max"))
    logic.tracks[0].params[2][1] = thr
    raw0 = thr.raw()
    n0 = len(fake.sent)
    s = cmds.plugin.set(1, None, 2, "Thrs", -30.0)
    assert not s.ok and s.verified == "unverified" and "복원" in s.note
    assert thr.value == -20.0
    bends = [m for m in fake.sent[n0:] if m[0] & 0xF0 == 0xE0]
    assert bends[-1] == [m for m in P.fader_move(1, raw0) if m[0] & 0xF0 == 0xE0][0]   # 마지막 페이더 송신 = 원래 위치
    assert [it["map"] for it in cache.param_table("Compressor")["items"] if it["index"] == 2] == [None]
    assert surface.state.view.kind == "pan" and not surface.state.assignment.flip


def test_map_is_cleared_and_saved_when_numeric_set_fails(tmp_path):                  # 리뷰 m5
    import json
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    logic.tracks[0].params[2][1] = Param("Thrs", "Threshold", "linear", -60.0, 0.0, -20.0, unit="n1", step=0.0)
    cache.params["Compressor"] = {"pages": 3, "items": [
        {"index": 2, "short": "Thrs", "name": "Threshold", "map": {"type": "linear", "lo": -60.0, "hi": -30.0}}]}
    s = cmds.plugin.set(1, None, 2, "Thrs", -50.0)
    assert not s.ok and s.verified == "unverified"
    assert [it["map"] for it in cache.param_table("Compressor")["items"] if it["index"] == 2] == [None]
    saved = json.loads(cache.path.read_text())
    assert [it["map"] for it in saved["params"]["Compressor"]["items"] if it["index"] == 2] == [None]


def test_list_bank_reenters_pl_per_track(tmp_path):
    """실기 8차: PL 안에서 SELECT 만 누르면 2행이 새 트랙을 따라오지 않는다 → 트랙마다 PAN 에서 재진입해야 인벤토리가 맞다."""
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.pl_select_stale = True
    logic.tracks[0].insert(1, "Channel EQ")
    logic.tracks[2].insert(3, "Compressor")
    cache.learn_abbrev("Cha EQ", "Channel EQ")
    cache.learn_abbrev("Comprs", "Compressor")
    n0 = len(fake.sent)
    r = cmds.plugin.list(None, None)
    assert r.verified == "verified"
    t = r.after["tracks"]
    assert t["15"]["1"] == {"text": "Cha EQ", "name": "Channel EQ"}
    assert t["16"]["1"] is None and all(v is None for v in t["16"].values())
    assert t["17"]["3"] == {"text": "Comprs", "name": "Compressor"}
    pan_presses = [m for m in fake.sent[n0:] if m[0] == 0x90 and m[1] == P.Note.PAN and m[2]]
    assert len(pan_presses) >= 8                       # 트랙마다 PAN 으로 나갔다 (재진입)
    assert surface.state.view.kind == "pan" and logic.selected == 0


def out_tracks():
    return [Track(1, "1"), Track(2, "DeCl"), Track(3, "StOu", kind="output"), Track(6, "Mast", kind="master")]


def track_presses(msgs: list[bytes]) -> int:
    return sum(1 for m in msgs if m[0] == 0x90 and m[1] == P.Note.TRACK and m[2])


def test_insert_on_output_strip_is_skipped_and_touches_nothing(tmp_path):      # Review Focus 1, 실측 Z4
    cmds, surface, fake, logic, cache = make(tmp_path, out_tracks())
    logic.tracks[1].insert(1, "Channel EQ")
    r = cmds.plugin.insert(strip=3, number=None, slot=1, plugin="Compressor")
    assert r.verified == "skipped" and "출력" in r.note and "번호 3" in r.note
    assert [t.inserts[1] for t in logic.tracks] == [None, "Channel EQ", None, None]
    assert logic.view == "pan" and surface.state.view.kind == "pan" and not logic.pre and logic.cs_param == 0
    for name, fn in (("params", lambda: cmds.plugin.params(None, 6, 1)), ("remove", lambda: cmds.plugin.remove(None, 6, 1)),
                     ("bypass", lambda: cmds.plugin.bypass(None, 6, 1, True)), ("list", lambda: cmds.plugin.list(None, 6))):
        r = fn()
        assert r.verified == "skipped" and "출력" in r.note, name


def test_insert_on_output_strip_fails_closed_when_output_push_is_dropped(tmp_path):   # 리뷰 C1
    cmds, surface, fake, logic, cache = make(tmp_path, out_tracks())
    logic.tracks[1].insert(1, "Channel EQ")
    logic.refuse = {P.Note.VPOT_PUSH + 4}                       # TRACK 메뉴 Output 누름 드롭 → CS 2행은 Volume 그대로
    r = cmds.plugin.insert(strip=3, number=None, slot=1, plugin="Compressor")
    assert not r.ok and r.verified in ("unverified", "skipped") and "Output" in r.note
    assert [t.inserts[1] for t in logic.tracks] == [None, "Channel EQ", None, None]
    assert cmds.strips.cache == {}
    assert logic.view == "pan" and surface.state.view.kind == "pan" and logic.cs_param == 0


def test_list_bank_marks_output_and_master_unsupported_and_caches_kinds(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path, out_tracks())
    logic.tracks[1].insert(1, "Channel EQ")
    r = cmds.plugin.list(None, None)
    assert r.verified == "verified"
    t = r.after["tracks"]
    assert t["1"]["1"] is None and t["2"]["1"] == {"text": "Cha EQ", "name": "Channel EQ"}
    assert t["3"] is None and t["6"] is None and r.after["unsupported"] == [3, 6]
    assert cmds.plugin.inventory["3"] is None
    n = track_presses(fake.sent)
    assert n >= 1
    r2 = cmds.plugin.list(None, None)
    assert r2.after["unsupported"] == [3, 6] and track_presses(fake.sent) == n     # (번호, 이름) 캐시: TRACK 모드 재진입 없음
    assert surface.state.view.kind == "pan" and logic.selected == 0


def test_strip_kinds_cache_invalidates_when_name_changes(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path, out_tracks())
    cmds.plugin.list(None, None)
    n = track_presses(fake.sent)
    logic.tracks[2] = Track(3, "Aux1", kind="track")             # 같은 번호에 다른 스트립(버스 센드가 Aux를 만들어 번호가 밀린 경우)
    logic.redraw()
    r = cmds.plugin.list(None, None)
    assert r.after["unsupported"] == [6] and r.after["tracks"]["3"] == {str(i): None for i in range(1, 9)}
    assert track_presses(fake.sent) > n


def aux_tracks():
    return [Track(1, "1"), Track(5, "Aux1", kind="aux"), Track(3, "StOu", kind="output")]


def make_aux(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path, aux_tracks())
    logic.plugin_list = PLUGIN_LIST + ["Tape Delay"]                 # 캐시 목록에 없는 이름도 Mixer 경로에서 이름 탐색으로
    return cmds, surface, fake, logic, cache


def test_aux_insert_slot1_uses_mixer_view(tmp_path):                  # 실전 F2: PL은 Aux를 따라가지 않는다
    cmds, surface, fake, logic, cache = make_aux(tmp_path)
    logic.tracks[0].insert(2, "Channel EQ")
    r = cmds.plugin.insert(2, None, 1, "Tape Delay")
    assert r.ok and r.verified == "verified" and r.after["path"] == "mixer" and r.after["plugin"] == "Tape Delay"
    assert logic.tracks[1].inserts[1] == "Tape Delay"
    assert {k: v for k, v in logic.tracks[0].inserts.items() if v} == {2: "Channel EQ"}   # 선택 트랙은 그대로
    assert surface.state.view.kind == "pan" and not logic.pre


def test_aux_insert_slot1_occupied_is_skipped(tmp_path):              # Review Focus 2
    cmds, surface, fake, logic, cache = make_aux(tmp_path)
    logic.tracks[1].insert(1, "Compressor")
    cmds.strips.follows(cmds.modes, surface.state, 1)
    n0 = len(fake.sent)
    for replace in (False, True):
        r = cmds.plugin.insert(2, None, 1, "Tape Delay", replace=replace)
        assert not r.ok and r.verified == "skipped" and "슬롯 1에" in r.note
    assert not turns(fake.sent[n0:]) and not pushes(fake.sent[n0:])
    assert {k: v for k, v in logic.tracks[1].inserts.items() if v} == {1: "Compressor"}
    assert all(v is None for v in logic.tracks[0].inserts.values()) and surface.state.view.kind == "pan"


def test_aux_insert_slot2_is_skipped_with_z19_note(tmp_path):
    cmds, surface, fake, logic, cache = make_aux(tmp_path)
    r = cmds.plugin.insert(2, None, 2, "Chorus")
    assert not r.ok and r.verified == "skipped" and "Z19" in r.note and "번호 5" in r.note
    assert all(v is None for t in logic.tracks for v in t.inserts.values())
    assert surface.state.view.kind == "pan" and logic.cs_param == 0


def test_aux_insert_refuses_when_mixer_shows_another_slot(tmp_path):  # 실측 O: Mixer 뷰는 마지막 편집 슬롯(P<n>)을 따른다
    cmds, surface, fake, logic, cache = make_aux(tmp_path)
    logic.slot = 3
    r = cmds.plugin.insert(2, None, 1, "Tape Delay")
    assert not r.ok and r.verified == "unverified" and "슬롯이 3" in r.note
    assert all(v is None for t in logic.tracks for v in t.inserts.values())


def test_aux_remove_slot1_uses_mixer_view(tmp_path):
    cmds, surface, fake, logic, cache = make_aux(tmp_path)
    logic.tracks[0].insert(1, "Channel EQ")
    logic.tracks[1].insert(1, "Compressor")
    r = cmds.plugin.remove(2, None, 1)
    assert r.ok and r.verified == "verified" and r.after["path"] == "mixer"
    assert r.before == {"slot": 1, "text": "Comprs"} and r.after["text"] == "--"
    assert logic.tracks[1].inserts[1] is None and logic.tracks[0].inserts[1] == "Channel EQ"
    assert cmds.plugin.remove(2, None, 1).verified == "skipped"     # 이미 비어 있음(already)
    assert surface.state.view.kind == "pan" and not logic.pre


def test_list_reports_aux_slot1_only(tmp_path):
    cmds, surface, fake, logic, cache = make_aux(tmp_path)
    logic.tracks[0].insert(1, "Channel EQ")
    logic.tracks[0].insert(2, "Compressor")
    logic.tracks[1].insert(1, "Compressor")
    cache.learn_abbrev("Comprs", "Compressor")
    r = cmds.plugin.list(None, None)
    assert r.verified == "verified"
    t = r.after["tracks"]
    assert t["5"] == {"1": {"text": "Comprs", "name": "Compressor"}, **{str(i): None for i in range(2, 9)}}
    assert t["5"] != t["1"] and t["1"]["1"] == {"text": "Cha EQ", "name": "Channel EQ"}
    assert r.after["aux"] == [5] and r.after["unsupported"] == [3] and t["3"] is None
    single = cmds.plugin.list(None, 5)
    assert single.after == {"tracks": {"5": t["5"]}, "aux": [5]}
    assert surface.state.view.kind == "pan" and not logic.pre


def test_params_on_aux_is_skipped(tmp_path):
    cmds, surface, fake, logic, cache = make_aux(tmp_path)
    logic.tracks[1].insert(1, "Compressor")
    r = cmds.plugin.params(2, None, 1)
    assert not r.ok and r.verified == "skipped" and "Z19" in r.note
    assert surface.state.view.kind == "pan"


def test_move_removes_and_reinserts_into_empty_slot(tmp_path):        # 스펙 4 F5
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    r = cmds.plugin.move(1, None, 2, 6)
    assert r.ok and r.verified == "verified"
    assert r.after == {"from": 2, "to": 6, "plugin": "Compressor", "note_path": "remove+insert"}
    assert r.note == "설정값은 초기화됨(MCU에 이동 명령이 없어 제거+재삽입)"
    assert logic.tracks[0].inserts[2] is None and logic.tracks[0].inserts[6] == "Compressor"
    assert surface.state.view.kind == "pan" and logic.name_mode is False and not logic.pre


def test_move_target_occupied_is_skipped(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    logic.tracks[0].insert(6, "Chorus")
    r = cmds.plugin.move(1, None, 2, 6)
    assert not r.ok and r.verified == "skipped" and "슬롯 6에" in r.note
    assert {k: v for k, v in logic.tracks[0].inserts.items() if v} == {2: "Compressor", 6: "Chorus"}
    assert surface.state.view.kind == "pan"


def test_move_source_empty_is_skipped(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    r = cmds.plugin.move(1, None, 2, 6)
    assert not r.ok and r.verified == "skipped" and "슬롯 2이 비어 있음" in r.note
    assert all(v is None for v in logic.tracks[0].inserts.values())


def test_move_reports_when_reinsert_fails(tmp_path):                   # Review Focus 3
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    i = PLUGIN_LIST.index("Compressor")
    logic.drop_preselect_at = {2 * i - 1, 2 * i}                     # Compressor 두 위치의 오버레이가 안 온다 → 이름으로 못 찾음
    r = cmds.plugin.move(1, None, 2, 6)
    assert not r.ok and r.verified == "unverified"
    assert "제거는 됐으나 재삽입 실패" in r.note and "Compressor" in r.note
    assert all(v is None for v in logic.tracks[0].inserts.values())   # 되돌리지 않는다(되돌리기도 삽입이라 같은 실패 가능)
    assert surface.state.view.kind == "pan" and not logic.pre


def test_move_on_aux_is_skipped(tmp_path):
    cmds, surface, fake, logic, cache = make_aux(tmp_path)
    logic.tracks[1].insert(1, "Compressor")
    r = cmds.plugin.move(2, None, 1, 2)
    assert not r.ok and r.verified == "skipped" and "Z19" in r.note
    assert {k: v for k, v in logic.tracks[1].inserts.items() if v} == {1: "Compressor"}
    assert all(v is None for v in logic.tracks[0].inserts.values())


def test_move_does_not_trust_a_wrong_abbrev_for_a_truncated_header(tmp_path):   # 실전 F6: `TO3000`→`Splice Sounds Listene` 오학습
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].name = "Deluxe Classic"                          # 헤더가 56칸에서 잘려 닫는 따옴표가 안 보인다(실측 G)
    logic.tracks[0].insert(2, "Space Designer")
    cache.learn_abbrev("SpaceD", "Limiter")                         # 틀린 축약 학습(그것도 설치된 다른 플러그인)
    r = cmds.plugin.move(1, None, 2, 6)
    assert r.verified == "verified" and r.after["plugin"] == "Space Designer"
    assert logic.tracks[0].inserts[6] == "Space Designer" and "Limiter" not in logic.tracks[0].inserts.values()
    assert cache.abbrev["SpaceD"] == "Space Designer"               # 헤더와 맞는 이름으로 고쳐 배운다


def test_move_skips_when_the_name_is_not_in_the_list(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.plugin_list = PLUGIN_LIST + ["Tape Delay"]
    logic.tracks[0].insert(2, "Tape Delay")                          # 캐시 목록에 없는 이름: 재삽입 이름을 확정할 수 없다
    r = cmds.plugin.move(1, None, 2, 6)
    assert not r.ok and r.verified == "skipped" and "이름을 확정하지 못해" in r.note
    assert logic.tracks[0].inserts[2] == "Tape Delay" and logic.tracks[0].inserts[6] is None
    assert surface.state.view.kind == "pan"
