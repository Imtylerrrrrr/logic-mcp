import pytest

from logic_mcp.logic.modes import OVERLAY_S, ModeDriver
from logic_mcp.logic.setter import (SetOutcome, coerce, enum_matches, probe_mapping, set_enum, set_enum_index,
                                    set_numeric, set_option, verdict)
from logic_mcp.logic.values import Mapping, parse_value
from tests.fake_assign import Param, make_assign_logic


def eq_driver():
    surface, fake, logic = make_assign_logic()
    logic.tracks[0].insert(1, "Channel EQ")
    d = ModeDriver(surface, sleep=logic.sleep)
    d.focus(0)
    d.enter("eq_channel")
    return d, logic, logic.tracks[0].eq


def test_set_numeric_with_log_mapping_uses_fader_once():
    d, logic, eq = eq_driver()
    out = set_numeric(d, 0, 1000.0, Mapping("log", 20.0, 20000.0), tolerance=10.0)
    assert out.ok and out.rounds == 0 and out.note == "fader"
    assert abs(eq[0][0].value - 1000.0) <= 10 and out.value.unit == "Hz"


def test_set_numeric_linear_mapping_then_already():
    d, logic, eq = eq_driver()
    out = set_numeric(d, 5, -3.0, Mapping("linear", -24.0, 24.0), tolerance=0.1)
    assert out.ok and eq[1][1].value == -3.0
    again = set_numeric(d, 5, -3.0, Mapping("linear", -24.0, 24.0), tolerance=0.1)
    assert again.ok and again.note == "already" and again.rounds == 0


def test_set_numeric_without_mapping_ticks_in_log_domain():
    d, logic, eq = eq_driver()
    out = set_numeric(d, 0, 1000.0, None, tolerance=100.0)
    assert out.ok and out.rounds <= 3 and abs(eq[0][0].value - 1000.0) <= 100


def test_set_numeric_without_mapping_ticks_linear():
    d, logic, eq = eq_driver()
    out = set_numeric(d, 5, -3.0, None, tolerance=0.1)
    assert out.ok and out.rounds == 2 and eq[1][1].value == -3.0


def test_set_numeric_gives_up_after_ten_rounds():
    d, logic, eq = eq_driver()
    eq[1][1].step = 7.0                              # 틱이 너무 거칠어 0.1 안에 못 들어감
    out = set_numeric(d, 5, -3.0, None, tolerance=0.1)
    assert out.ok is False and out.rounds == 10 and "못 맞춤" in out.note and "10회" in out.note


def test_set_numeric_out_of_range_is_skipped_before_any_midi():          # 실기 11/11: GoldVerb Room Size 1500(10~200 m)이 페이더를 끝까지 밀고 실패
    d, logic, eq = eq_driver()
    n0 = len(logic.fake.sent)
    out = set_numeric(d, 0, 25000.0, Mapping("log", 20.0, 20000.0), tolerance=500.0)
    assert out == SetOutcome(False, d.read_value(0), 0, "skip:범위 밖: 20~20000 Hz")
    assert logic.fake.sent[n0:] == [] and eq[0][0].value == 20.0
    assert verdict(out) == (False, "skipped", "범위 밖: 20~20000 Hz")
    out = set_numeric(d, 5, -30.0, Mapping("linear", -24.0, 24.0), tolerance=0.2)
    assert out.note == "skip:범위 밖: -24~24 dB" and logic.fake.sent[n0:] == []


def test_set_numeric_at_the_range_end_proceeds():
    d, logic, eq = eq_driver()
    out = set_numeric(d, 0, 20000.0, Mapping("log", 20.0, 20000.0), tolerance=400.0)
    assert out.ok and eq[0][0].value == 20000.0


def test_set_numeric_range_check_skips_db_table():                     # db_table의 lo·hi는 기본값(0~1)이라 범위가 아니다
    from logic_mcp.logic.faders import FaderTable
    d, logic, eq = eq_driver()
    n0 = len(logic.fake.sent)
    out = set_numeric(d, 5, -3.0, Mapping("db_table"), tolerance=0.2, faders=FaderTable.load())
    assert not out.note.startswith("skip:") and [m for m in logic.fake.sent[n0:] if m[0] & 0xF0 == 0xE0]
    assert out.ok and abs(eq[1][1].value - -3.0) <= 0.2


def test_tolerance_argument_overrides_default(tmp_path):                 # Review Focus 5: 사용자 tolerance가 새 기본값보다 우선
    from logic_mcp.logic.commands import Commands
    from logic_mcp.logic.faders import FaderTable
    from logic_mcp.logic.plugins.cache import PluginCache
    from tests.fake_assign import PLUGIN_LIST

    def run(tolerance):
        surface, fake, logic = make_assign_logic()
        cache = PluginCache("fake", list(PLUGIN_LIST), [], {}, {}, None, tmp_path / "plugins-fake.json")
        cache.params["Compressor"] = {"pages": 3, "items": [
            {"index": 7, "short": "MakeUp", "name": "Make Up", "map": {"type": "linear", "lo": -12.0, "hi": 40.0}}]}
        cmds = Commands(surface, FaderTable.load(), sleep=logic.sleep, logic_running=lambda: True, plugin_cache=cache)
        logic.tracks[0].insert(2, "Compressor")
        logic.drop_all_faders = True                   # 틱(0.5 dB)으로만 맞춘다: 3.1에는 3.0이 가장 가깝다
        return cmds.plugin.set(1, None, 2, "MakeUp", 3.1, tolerance), logic.tracks[0].params[2][6]
    r, p = run(None)
    assert r.ok and r.verified == "verified" and p.value == 3.0     # 기본 0.2 dB 안
    r, p = run(0.05)
    assert not r.ok and r.verified == "unverified" and "허용 오차 0.05" in r.note


def test_set_enum_forward_and_reverse():
    d, logic, eq = eq_driver()
    out = set_enum(d, 1, "36")                       # 슬로프 12 → 18 → 24 → 36
    assert out.ok and out.rounds == 3 and eq[0][1].value == 4
    out = set_enum(d, 1, "6")                        # 되돌아가기
    assert out.ok and eq[0][1].value == 0
    out = set_enum(d, 3, "On")
    assert out.ok and eq[0][3].value == 1
    assert set_enum(d, 3, "On").note == "already"
    bad = set_enum(d, 3, "Maybe", max_steps=4)
    assert bad.ok is False and "Maybe" in bad.note


def test_enum_matches():
    assert enum_matches(parse_value("36 dB/Oct"), "36")
    assert enum_matches(parse_value("On"), "On") and not enum_matches(parse_value("Off"), "On")
    assert enum_matches(parse_value("Post Pan"), "Post Pan") and not enum_matches(parse_value("Post Pan"), "Post")


def test_probe_mapping_reads_min_max():
    d, logic, eq = eq_driver()
    d.flip(True)
    m, lo, hi = probe_mapping(d, 5)
    assert m == Mapping("linear", -24.0, 24.0) and lo.text == "-24.0 dB" and hi.text == "+24.0 dB"
    m2, lo2, hi2 = probe_mapping(d, 0)
    assert m2 == Mapping("log", 20.0, 20000.0)


def test_enum_matches_truncated_slope_unit():
    assert enum_matches(parse_value("24 dB/O"), "24") is True
    assert enum_matches(parse_value("18 dB/O"), "24") is False


def test_set_numeric_log_q_converges_from_2_8_to_2_0():
    """실측 T·U: Q는 log 0.10~100, 틱당 ×1.06. 틱을 로그 영역에서 추정해야 2.8 → 2.0에 수렴한다."""
    d, logic, eq = eq_driver()
    q = eq[0][2]                                                   # 밴드 1 Q = 열 2
    assert set_numeric(d, 2, 2.8, Mapping("log", 0.10, 100.0), tolerance=0.06).ok     # 시작점 2.8
    out = set_numeric(d, 2, 2.0, Mapping("log", 0.10, 100.0), tolerance=0.04)
    assert out.ok and abs(q.value - 2.0) <= 0.04
    # 매핑 범위가 틀려 페이더가 빗나가도(시컨트 뒤 틱 보정) 로그 영역 틱 추정으로 수렴
    assert set_numeric(d, 2, 2.8, Mapping("log", 0.10, 100.0), tolerance=0.06).ok
    out = set_numeric(d, 2, 2.0, Mapping("log", 0.30, 30.0), tolerance=0.05)   # 틱 1칸 ≈ 6 %라 허용 오차에 여유
    assert out.ok and abs(q.value - 2.0) <= 0.05 and out.rounds <= 4


def test_probe_mapping_reads_min_max_with_lagging_lcd():             # 실측 X
    surface, fake, logic = make_assign_logic()
    logic.tracks[0].insert(1, "Compressor")
    logic.lcd_lag = True
    d = ModeDriver(surface, sleep=logic.sleep)
    d.focus(0)
    d.enter("plugin_channel")
    assert d.press_vpot_until(0, lambda v: v.kind == "plugin_edit", 3.0)
    d.flip(True)
    m, lo, hi = probe_mapping(d, 1)
    assert lo.number == -60.0 and hi.number == 0.0 and m == Mapping("linear", -60.0, 0.0)


def test_set_numeric_q_succeeds_when_first_fader_move_is_dropped():       # 실측 Z1
    d, logic, eq = eq_driver()
    logic.drop_first_fader = True
    out = set_numeric(d, 2, 2.0, Mapping("log", 0.10, 100.0), tolerance=0.04)
    assert out.ok and abs(eq[0][2].value - 2.0) <= 0.04


def test_set_numeric_skips_secant_when_fader_has_no_effect():            # 실측 Z1: 이동 전 값으로 보정하지 않는다
    d, logic, eq = eq_driver()
    logic.drop_all_faders = True
    fake = logic.fake
    fake.sent.clear()
    out = set_numeric(d, 2, 2.0, Mapping("log", 0.10, 100.0), tolerance=0.04)
    assert out.ok and abs(eq[0][2].value - 2.0) <= 0.04
    moves = [m for m in fake.sent if m[0] & 0xF0 == 0xE0]
    assert len(moves) == 2 and len(set(moves)) == 1                      # fader()의 같은 이동 재전송뿐, 시컨트 이동 없음


CIRCUIT = ("PltDig", "Studio", "Studio", "Classc", "Vintag", "Vintag", "VinOpt")   # 축약이 겹치는 표(가정). 10/27 Circuit Type의 겹침은 오버레이를 읽은 것(10/28)


def recorded_ticks(d):
    sent = []
    real = d.tick

    def tick(ch, steps):
        sent.append(steps)
        return real(ch, steps)
    d.tick = tick
    return sent


def test_set_enum_index_rewinds_then_counts_forward():
    d, logic, eq = eq_driver()
    eq[0][3] = Param("CirTyp", "Circuit Type", "enum", options=CIRCUIT, value=2)
    sent = recorded_ticks(d)
    out = set_enum_index(d, 3, 6, list(CIRCUIT))
    assert out.ok and out.value.text == "Vintag" and eq[0][3].value == 5
    assert sent == [-1] * 16 + [1] * 5                                  # 끝까지 되감은 뒤 n-1틱


def test_set_enum_index_out_of_range_and_without_options():
    d, logic, eq = eq_driver()
    eq[0][3] = Param("CirTyp", "Circuit Type", "enum", options=CIRCUIT, value=2)
    sent = recorded_ticks(d)
    bad = set_enum_index(d, 3, 8, list(CIRCUIT))
    assert bad.ok is False and "범위 밖" in bad.note and sent == [] and eq[0][3].value == 2
    out = set_enum_index(d, 3, 2, None)
    assert out.ok and out.note == "no_options" and out.value.text == "Studio" and eq[0][3].value == 1


def test_set_enum_index_waits_for_the_overlay_only_before_reading():          # 읽지 않는 틱 사이 오버레이 대기(≈2 s)를 뺀다
    d, logic, eq = eq_driver()
    eq[0][3] = Param("CirTyp", "Circuit Type", "enum", options=CIRCUIT, value=2)
    t0 = logic.fake.now
    out = set_enum_index(d, 3, 6, list(CIRCUIT))
    assert out.ok and out.value.text == "Vintag" and eq[0][3].value == 5
    assert logic.fake.now - t0 < 15                                           # 틱마다 settle_overlay면 ≈43 s


def test_set_enum_index_already_on_unique_option_sends_no_ticks():
    d, logic, eq = eq_driver()
    eq[0][3] = Param("CirTyp", "Circuit Type", "enum", options=CIRCUIT, value=3)
    logic.redraw()
    sent = recorded_ticks(d)
    out = set_enum_index(d, 3, 4, list(CIRCUIT))                              # 'Classc'는 표에서 하나뿐 → already
    assert out.ok and out.note == "already" and out.rounds == 0 and sent == []
    eq[0][3].value = 2
    logic.redraw()
    out = set_enum_index(d, 3, 2, list(CIRCUIT))                              # 'Studio'는 둘 → 같은 텍스트여도 번호로 돌린다
    assert out.ok and out.note == "" and eq[0][3].value == 1 and sent == [-1] * 16 + [1]


CIRCUIT_SHORT = ("PltDig", "StudoA", "StudoT", "ClsscA", "VintgA", "VintgT", "VinOpt")    # 실측 2026-10-28 재수집(정착 열)
CIRCUIT_LONG = ("Platinum Digital", "Studio VCA", "Studio FET", "Classic VCA",             # 오버레이 전체 이름('Vintage Opto'만 실측, 나머지는 같은 꼴로 가정)
                "Vintage VCA", "Vintage FET", "Vintage Opto")


def test_set_enum_reads_settled_text_after_the_value_overlay():     # 실측 2026-10-28: 틱 뒤 2초간 21칸 오버레이가 열을 덮어 'Vintage'를 읽고 끝으로 오인
    d, logic, eq = eq_driver()
    eq[0][3] = Param("CirTyp", "Circuit Type", "enum", options=CIRCUIT_SHORT, labels=CIRCUIT_LONG, value=5)
    logic.redraw()
    t0 = logic.fake.now
    out = set_enum(d, 3, "StudoT")                                  # VintgT → VinOpt → (끝) → 되돌아 StudoT
    assert out.ok and out.value.text == "StudoT" and eq[0][3].value == 2
    assert logic.fake.now - t0 >= out.rounds * OVERLAY_S              # 틱마다 오버레이가 걷힐 때까지 기다린 뒤 읽음


def test_set_enum_index_ticks_the_difference_when_start_is_known():
    d, logic, eq = eq_driver()
    eq[0][3] = Param("CirTyp", "Circuit Type", "enum", options=CIRCUIT_SHORT, labels=CIRCUIT_LONG, value=5)
    logic.redraw()
    sent = recorded_ticks(d)
    out = set_enum_index(d, 3, 3, list(CIRCUIT_SHORT), start=6)       # #6 VintgT → #3 StudoT: 되감기 없이 -1 세 번
    assert out.ok and out.value.text == "StudoT" and eq[0][3].value == 2 and sent == [-1] * 3
    out = set_enum_index(d, 3, 7, list(CIRCUIT_SHORT), start=3)
    assert out.ok and out.value.text == "VinOpt" and eq[0][3].value == 6 and sent == [-1] * 3 + [1] * 4


NUM, OPT = parse_value("20.0Hz"), parse_value("On")


def test_coerce_bool_number_and_text():
    assert coerce(True, NUM, None) == (False, "On") and coerce(False, NUM, None) == (False, "Off")
    assert coerce(3, NUM, None) == (True, 3.0) and coerce(2.5, NUM, Mapping("log", 20.0, 20000.0)) == (True, 2.5)
    assert coerce("1.5", NUM, None) == (True, 1.5)
    assert coerce("Vintage", NUM, None) == (False, "Vintage")


def test_coerce_falls_back_to_option_text_for_enum():
    enum = Mapping("enum", options=("6", "12"))
    assert coerce(2, NUM, enum) == (False, "2") and coerce(2.5, NUM, enum) == (False, "2.5")
    assert coerce("3", NUM, enum) == (False, "3")
    assert coerce(1, OPT, None) == (False, "1")                               # 매핑 없음 + 지금 값이 숫자가 아님
    assert coerce(1, OPT, Mapping("linear", 0.0, 10.0)) == (True, 1.0)       # 숫자 매핑이 있으면 지금 값 종류와 무관


def test_coerce_maps_0_and_1_to_off_on_for_an_off_on_enum():                # 1이 `1`이 되어 `On`과 안 맞던 것
    onoff = Mapping("enum", options=("Off", "On"))
    assert coerce(0, OPT, onoff) == (False, "Off") and coerce(1, OPT, onoff) == (False, "On")
    assert coerce("1", OPT, onoff) == (False, "On") and coerce(1.0, OPT, onoff) == (False, "On")
    assert coerce(0.0, OPT, onoff) == (False, "Off") and coerce("0", OPT, onoff) == (False, "Off")
    assert coerce(2, OPT, onoff) == (False, "2")                               # 다른 숫자는 그대로
    other = Mapping("enum", options=("Off", "Max"))
    assert coerce(1, OPT, other) == (False, "1") and coerce(0, OPT, other) == (False, "0")


def test_set_option_index_skips_numeric_parameter_without_table():
    d, logic, eq = eq_driver()
    before = d.read_value(0)
    sent = recorded_ticks(d)
    out = set_option(d, 0, "#2", None, before)
    assert out == SetOutcome(False, before, 0, "skip:#n은 enum 파라미터에만 쓸 수 있음") and sent == []


def test_set_option_index_rewinds_with_or_without_table():
    d, logic, eq = eq_driver()
    eq[0][3] = Param("CirTyp", "Circuit Type", "enum", options=CIRCUIT, value=0)   # 시작값 PltDig는 표에서 하나뿐
    logic.redraw()
    sent = recorded_ticks(d)
    out = set_option(d, 3, "#6", list(CIRCUIT), d.read_value(3))            # #n은 지금 위치가 하나뿐이어도 되감기
    assert out.ok and eq[0][3].value == 5 and sent == [-1] * 16 + [1] * 5
    sent.clear()
    out = set_option(d, 3, "#2", None, d.read_value(3))                      # 표 없음 + enum 값 → 번호 경로(no_options)
    assert out.ok and out.note == "no_options" and eq[0][3].value == 1 and sent == [-1] * 16 + [1]


def test_set_option_duplicate_text_is_skipped():
    d, logic, eq = eq_driver()
    eq[0][3] = Param("CirTyp", "Circuit Type", "enum", options=CIRCUIT, value=0)
    logic.redraw()
    before = d.read_value(3)
    sent = recorded_ticks(d)
    out = set_option(d, 3, "Studio", list(CIRCUIT), before)
    assert out == SetOutcome(False, before, 0, "skip:'Studio'가 2개(#2, #3): 번호로 지정")
    assert sent == [] and eq[0][3].value == 0


def test_set_option_unique_text_uses_start_only_when_current_is_unique():
    d, logic, eq = eq_driver()
    eq[0][3] = Param("CirTyp", "Circuit Type", "enum", options=CIRCUIT_SHORT, value=5)
    logic.redraw()
    sent = recorded_ticks(d)
    out = set_option(d, 3, "StudoT", list(CIRCUIT_SHORT), d.read_value(3))  # VintgT(#6) → StudoT(#3): 차이만큼
    assert out.ok and eq[0][3].value == 2 and sent == [-1] * 3
    eq[0][3] = Param("CirTyp", "Circuit Type", "enum", options=CIRCUIT, value=1)
    logic.redraw()
    sent.clear()
    out = set_option(d, 3, "Classc", list(CIRCUIT), d.read_value(3))        # 지금 'Studio'는 표에 둘 → 되감기
    assert out.ok and eq[0][3].value == 3 and sent == [-1] * 16 + [1] * 3


def test_set_option_falls_back_to_text_path():
    d, logic, eq = eq_driver()
    out = set_option(d, 3, "On", None, d.read_value(3))                      # 표 없음
    assert out.ok and eq[0][3].value == 1
    eq[0][3] = Param("CirTyp", "Circuit Type", "enum", options=CIRCUIT_SHORT, value=5)
    logic.redraw()
    out = set_option(d, 3, "StudoT", list(CIRCUIT), d.read_value(3))        # 표에 없는 이름(낡은 표)
    assert out.ok and out.value.text == "StudoT" and eq[0][3].value == 2


def test_verdict_maps_each_outcome():
    v = parse_value("1.0")
    assert verdict(SetOutcome(True, v, 0, "already")) == (True, "skipped", "already")
    assert verdict(SetOutcome(True, v, 2, "no_options")) == (True, "unverified", "선택지 표 없음(calibrate 전): 도착 텍스트만 보고")
    assert verdict(SetOutcome(False, v, 0, "skip:#n은 enum 파라미터에만 쓸 수 있음")) == (False, "skipped", "#n은 enum 파라미터에만 쓸 수 있음")
    assert verdict(SetOutcome(True, v, 1, "fader")) == (True, "verified", "fader")
    assert verdict(SetOutcome(False, v, 10, "못 맞춤")) == (False, "unverified", "못 맞춤")
