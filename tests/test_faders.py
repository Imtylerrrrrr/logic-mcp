import math

import pytest

from logic_mcp.logic import faders as F


def test_spot_points():
    t = F.FaderTable.load()
    assert t.db_to_raw(0.0) == 12443
    assert t.db_to_raw(-5.8) == 9990
    assert t.db_to_raw(6.0) == 14845
    assert t.db_to_raw(math.inf * -1) == 0
    assert t.raw_to_db(12443) == pytest.approx(0.0)
    assert t.raw_to_db(0) == -math.inf


def test_clamp_and_monotonic():
    t = F.FaderTable.load()
    assert t.db_to_raw(20.0) == F.MAX_RAW
    assert t.db_to_raw(-200.0) == 0
    prev = -1
    for db10 in range(-600, 61):
        raw = t.db_to_raw(db10 / 10)
        assert raw >= prev
        prev = raw
    with pytest.raises(ValueError):
        t.db_to_raw(math.nan)


def test_interpolation_between_points():
    t = F.FaderTable.load()
    mid = t.db_to_raw(-2.9)
    assert 9990 < mid < 12443


def test_parse_db_text():
    assert F.parse_db_text("+0.0 dB") == 0.0
    assert F.parse_db_text("-5.8 dB") == -5.8
    assert F.parse_db_text("-oo dB") == -math.inf
    assert F.parse_db_text("-10.5dB") == -10.5
    assert F.parse_db_text("Muted") is None
    assert F.parse_db_text("") is None


def test_parse_pan_text():
    assert F.parse_pan_text("+5") == 5
    assert F.parse_pan_text("0") == 0
    assert F.parse_pan_text("-12") == -12
    assert F.parse_pan_text("-") is None
    assert F.parse_pan_text("+0.0 dB") is None
    assert F.parse_pan_text("") is None
