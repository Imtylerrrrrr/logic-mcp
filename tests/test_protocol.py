from pathlib import Path

import pytest

from logic_mcp.mcu import protocol as P

FIXTURE = Path(__file__).parent / "fixtures" / "mcu" / "cap_raw6.log"


def test_parse_fixture_line():
    ts, d, data = P.parse_fixture_line("  754.235 RX 90 10 7F")
    assert ts == pytest.approx(754.235)
    assert d == "RX"
    assert data == bytes([0x90, 0x10, 0x7F])
    assert P.parse_fixture_line("") is None


def test_decode_device_query_and_version():
    assert P.decode(bytes.fromhex("F0 00 00 66 14 00 F7")) == P.DeviceQuery(device=0x14)
    assert P.decode(bytes.fromhex("F0 00 00 66 15 00 F7")) == P.DeviceQuery(device=0x15)
    assert P.decode(bytes.fromhex("F0 00 00 66 14 13 00 F7")) == P.VersionRequest(device=0x14)


def test_decode_lcd_write():
    ev = P.decode(bytes.fromhex("F0 00 00 66 14 12 38 4D 75 74 65 64 F7"))
    assert ev == P.LcdWrite(offset=56, text=b"Muted")


def test_decode_led_fader_ring_meter():
    assert P.decode(bytes([0x90, 0x10, 0x7F])) == P.Led(note=0x10, on=True)
    assert P.decode(bytes([0x90, 0x5D, 0x00])) == P.Led(note=0x5D, on=False)
    assert P.decode(bytes([0xE0, 0x06, 0x4E])) == P.FaderPos(channel=0, value=9990)
    assert P.decode(bytes([0xE8, 0x00, 0x00])) == P.FaderPos(channel=8, value=0)
    assert P.decode(bytes([0xB0, 0x30, 0x16])) == P.VpotRing(channel=0, mode=1, pos=6, center=False)
    assert P.decode(bytes([0xB0, 0x31, 0x56])) == P.VpotRing(channel=1, mode=1, pos=6, center=True)
    assert P.decode(bytes([0xD0, 0x2C])) == P.Meter(channel=2, level=12)


def test_decode_time_and_assign_digits():
    # CC 0x49가 맨 왼쪽(index 0), 0x40이 맨 오른쪽(index 9)
    assert P.decode(bytes([0xB0, 0x41, 0x34])) == P.TimeDigit(index=8, char="4", dot=False)
    assert P.decode(bytes([0xB0, 0x49, 0x20])) == P.TimeDigit(index=0, char=" ", dot=False)
    assert P.decode(bytes([0xB0, 0x40, 0x71])) == P.TimeDigit(index=9, char="1", dot=True)
    assert P.decode(bytes([0xB0, 0x4B, 0x10])) == P.AssignDigit(index=0, char="P", dot=False)


def test_decode_other_mcu_sysex_and_unknown():
    assert P.decode(bytes.fromhex("F0 00 00 66 14 0E 00 03 F7")) == P.McuSysex(command=0x0E, payload=bytes([0x00, 0x03]))
    assert P.decode(bytes.fromhex("F0 00 00 66 14 12 38 4D")) == P.Unknown(data=bytes.fromhex("F0 00 00 66 14 12 38 4D"))
    assert P.decode(b"") == P.Unknown(data=b"")
    assert P.decode(bytes([0xF0, 0x7E, 0x00])) == P.Unknown(data=bytes([0xF0, 0x7E, 0x00]))
    assert P.decode(bytes([0xB0, 0x3C, 0x01])) == P.Unknown(data=bytes([0xB0, 0x3C, 0x01]))


def test_seg_char():
    assert P.seg_char(0x34) == ("4", False)
    assert P.seg_char(0x74) == ("4", True)
    assert P.seg_char(0x10) == ("P", False)
    assert P.seg_char(0x20) == (" ", False)


def test_fixture_decodes_without_error():
    rows = P.load_fixture(FIXTURE)
    assert len(rows) > 4000
    kinds = set()
    for _ts, direction, data in rows:
        if direction != "RX":
            continue
        kinds.add(type(P.decode(data)).__name__)
    assert {"LcdWrite", "Led", "FaderPos", "TimeDigit", "VpotRing", "DeviceQuery", "VersionRequest"} <= kinds


def test_handshake_reply_only_for_0x14():
    reply = P.handshake_reply(P.DeviceQuery(device=0x14))
    assert reply == bytes.fromhex("F0 00 00 66 14 01 4C 47 43 4D 43 50 31 01 02 03 04 F7")
    assert P.handshake_reply(P.DeviceQuery(device=0x15)) is None
    assert P.handshake_reply(P.DeviceQuery(device=0x10)) is None
    assert P.handshake_reply(P.VersionRequest(device=0x14)) == bytes.fromhex("F0 00 00 66 14 14 56 31 2E 30 30 F7")
    assert P.handshake_reply(P.VersionRequest(device=0x11)) is None
    assert P.handshake_reply(P.Led(note=1, on=True)) is None


def test_handshake_reply_matches_fixture_tx():
    rows = P.load_fixture(FIXTURE)
    pairs = [(rows[i][2], rows[i + 1][2]) for i in range(len(rows) - 1)
             if rows[i][1] == "RX" and rows[i + 1][1] == "TX"]
    checked = 0
    for rx, tx in pairs:
        ev = P.decode(rx)
        if isinstance(ev, (P.DeviceQuery, P.VersionRequest)) and ev.device == 0x14:
            assert P.handshake_reply(ev) == tx
            checked += 1
    assert checked >= 2


def test_button_and_fader_and_vpot_encoders():
    assert P.button_down(P.Note.PLAY) == bytes([0x90, 0x5E, 0x7F])
    assert P.button_up(P.Note.PLAY) == bytes([0x90, 0x5E, 0x00])
    assert P.fader_move(0, 10000) == [bytes([0x90, 0x68, 0x7F]), bytes([0xE0, 0x10, 0x4E]), bytes([0x90, 0x68, 0x00])]
    assert P.fader_move(7, 0)[1] == bytes([0xE7, 0x00, 0x00])
    assert P.vpot_turn(0, 5) == bytes([0xB0, 0x10, 0x05])
    assert P.vpot_turn(0, -5) == bytes([0xB0, 0x10, 0x45])
    assert P.vpot_turn(3, 63) == bytes([0xB0, 0x13, 0x3F])
    assert P.vpot_turn(3, 99) == bytes([0xB0, 0x13, 0x3F])
    with pytest.raises(ValueError):
        P.vpot_turn(0, 0)
    with pytest.raises(ValueError):
        P.fader_move(0, 16384)
    with pytest.raises(ValueError):
        P.fader_move(9, 0)


def test_cursor_and_function_notes():
    assert (P.Note.CURSOR_UP, P.Note.CURSOR_DOWN, P.Note.CURSOR_LEFT, P.Note.CURSOR_RIGHT) == (0x60, 0x61, 0x62, 0x63)
    assert P.Note.ZOOM == 0x64 and P.Note.F1 == 0x36
    assert P.NOTE_NAMES[0x62] == "CURSOR_LEFT"


def test_vpot_turn_messages_split_at_63():
    assert P.vpot_turn_messages(0, 100) == [P.vpot_turn(0, 63), P.vpot_turn(0, 37)]
    assert P.vpot_turn_messages(2, -130) == [P.vpot_turn(2, -63), P.vpot_turn(2, -63), P.vpot_turn(2, -4)]
    assert P.vpot_turn_messages(0, 5) == [P.vpot_turn(0, 5)]
    assert P.vpot_turn_messages(0, 0) == []


def test_assign_fixtures_load():
    rows = P.load_fixture(Path(__file__).parent / "fixtures" / "mcu" / "cap_assign2.log")
    assert len(rows) > 800 and rows[0][1] == "RX"
    kinds = {type(P.decode(data)).__name__ for _, _, data in rows}
    assert {"LcdWrite", "AssignDigit", "FaderPos", "Led", "VpotRing"} <= kinds
