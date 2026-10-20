import math

import pytest

from logic_mcp.logic.faders import FaderTable
from logic_mcp.logic.values import Mapping, Value, infer_mapping, parse_value, raw_for, tolerance_for, within


@pytest.mark.parametrize("text,number,unit", [
    ("20.0Hz", 20.0, "Hz"), ("21.6 Hz", 21.6, "Hz"), ("1040Hz", 1040.0, "Hz"), ("625 Hz", 625.0, "Hz"),
    ("20000", 20000.0, None), ("2.5kHz", 2500.0, "Hz"),
    ("-78.4 d", -78.4, "dB"), ("-78.4 dB", -78.4, "dB"), ("+0.0 dB", 0.0, "dB"), ("0.0 dB", 0.0, "dB"),
    ("-oo dB", -math.inf, "dB"), ("-oodB", -math.inf, "dB"),
    ("36 dB/Oct", 36.0, "dB/Oct"), ("0.71", 0.71, None), ("12", 12.0, None), (" 1", 1.0, None),
    ("1100", 1100.0, None), ("-0.5", -0.5, None), ("50 %", 50.0, "%"), ("12.5 ms", 12.5, "ms"),
])
def test_parse_numbers(text, number, unit):
    v = parse_value(text)
    assert v.kind == "number" and v.unit == unit
    assert v.number == number


@pytest.mark.parametrize("text", ["On", "Off", "Post", "Post Pan", "active", "muted", "--", "* 1", "Control #1", "Cha EQ"])
def test_parse_enum(text):
    v = parse_value(text)
    assert v.kind == "enum" and v.text == text.strip() and v.number is None


def test_parse_none():
    assert parse_value("       ").kind == "none"
    assert parse_value("").kind == "none"


def test_raw_for_log_linear_enum():
    assert raw_for(Mapping("log", 20.0, 20000.0), 20.0) == 1          # raw 0은 보내지 않음
    assert abs(raw_for(Mapping("log", 20.0, 20000.0), 632.0) - 8192) <= 20
    assert raw_for(Mapping("log", 20.0, 20000.0), 20000.0) == 16383
    assert raw_for(Mapping("linear", -24.0, 24.0), 0.0) == 8192
    assert raw_for(Mapping("linear", -24.0, 24.0), 30.0) == 16383   # 클램프
    m = Mapping("enum", options=("6", "12", "18", "24", "36", "48"))
    assert raw_for(m, "12") == 3277 and raw_for(m, "24") == 9830 and raw_for(m, "48") == 16383
    assert raw_for(Mapping("enum", options=("Off", "On")), "Off") == 1
    assert raw_for(Mapping("db_table"), -6.0, FaderTable.load()) == FaderTable.load().db_to_raw(-6.0)
    with pytest.raises(ValueError):
        raw_for(m, "7")


def test_infer_mapping():
    assert infer_mapping(parse_value("20.0 Hz"), parse_value("20000 Hz")) == Mapping("log", 20.0, 20000.0)
    assert infer_mapping(parse_value("-24.0 dB"), parse_value("+24.0 dB")) == Mapping("linear", -24.0, 24.0)
    assert infer_mapping(parse_value("0.10"), parse_value("10.0")) == Mapping("linear", 0.1, 10.0)
    assert infer_mapping(parse_value("Off"), parse_value("On")) is None
    assert infer_mapping(parse_value("-oo dB"), parse_value("+6.0 dB")) is None   # 무한대는 선형 아님


def test_tolerance_and_within():
    assert tolerance_for(1000.0, "Hz") == 10.0
    assert tolerance_for(-3.0, "dB") == 0.1
    assert tolerance_for(0.5, None) == 0.01
    assert tolerance_for(2.0, None) == 0.04 and tolerance_for(50.0, None) == 1.0   # 단위 없는 숫자(Q)는 2 %
    assert within(1004.0, 1000.0, 10.0) and not within(1011.0, 1000.0, 10.0)
    assert not within(math.nan, 1.0, 1.0)


def test_parse_number_with_unknown_or_truncated_unit():       # 실측 R: `24 dB/O`가 enum이 되어 슬로프 매칭 실패
    v = parse_value("24 dB/O")
    assert v.kind == "number" and v.number == 24.0 and v.unit == "dB/Oct"
    v = parse_value("3 foo")
    assert v.kind == "number" and v.number == 3.0 and v.unit == "foo"


def test_parse_value_ratio_unit():                                    # Compressor Ratio `2.1:1`(실측 M)
    v = parse_value("2.1:1")
    assert v.kind == "number" and v.number == 2.1 and v.unit == ":1"


def test_parse_value_allows_at_most_one_space_before_unit():                       # 실측 2026-10-20: '1.00   High'(5열+6열)는 숫자가 아니다
    assert parse_value("1.00   High").kind == "enum"
    v = parse_value("-78.4 d")
    assert v.kind == "number" and v.number == -78.4 and v.unit == "dB"
    v = parse_value("18 dB/O")
    assert v.kind == "number" and v.number == 18.0 and v.unit == "dB/Oct"
    v = parse_value("0.0 dB        ")
    assert v.kind == "number" and v.number == 0.0 and v.unit == "dB"
