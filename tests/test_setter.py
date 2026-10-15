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
