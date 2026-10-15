import pytest

from logic_mcp.logic.modes import ModeDriver
from logic_mcp.logic.setter import enum_matches, probe_mapping, set_enum, set_numeric
from logic_mcp.logic.values import Mapping, parse_value
from tests.fake_assign import make_assign_logic


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


def test_set_numeric_gives_up_after_six_rounds():
    d, logic, eq = eq_driver()
    eq[1][1].step = 7.0                              # 틱이 너무 거칠어 0.1 안에 못 들어감
    out = set_numeric(d, 5, -3.0, None, tolerance=0.1)
    assert out.ok is False and out.rounds == 6 and "못 맞춤" in out.note


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
