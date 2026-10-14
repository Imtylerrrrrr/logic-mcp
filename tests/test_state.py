from pathlib import Path

from logic_mcp.mcu import protocol as P
from logic_mcp.mcu import state as S

FIXTURE = Path(__file__).parent / "fixtures" / "mcu" / "cap_raw6.log"


def replay(until: float, start: float = 0.0) -> S.SurfaceState:
    st = S.initial_state()
    for ts, direction, data in P.load_fixture(FIXTURE):
        if ts < start or direction != "RX":
            continue
        if ts > until:
            break
        st = S.tick(st, ts)
        st = S.reduce(st, P.decode(data), ts)
    return S.tick(st, until)


def test_parse_column():
    assert S.parse_column("1:1    ") == (1, "1")
    assert S.parse_column("2:StOu ") == (2, "StOu")
    assert S.parse_column("12:Aud ") == (12, "Aud")
    assert S.parse_column("St Out ") == (None, "St Out")
    assert S.parse_column("       ") == (None, "")


def test_lcd_write_updates_rows_and_strips():
    st = S.initial_state()
    st = S.reduce(st, P.LcdWrite(offset=0, text=b"1:1    2:StOu 5:Mast "), 10.0)
    st = S.reduce(st, P.LcdWrite(offset=56, text=b"+0.0 dB-5.8 dB"), 10.1)
    assert st.lcd[0].startswith("1:1    2:StOu 5:Mast")
    assert st.strips[0].number == 1 and st.strips[0].name == "1"
    assert st.strips[1].number == 2 and st.strips[1].name == "StOu"
    assert st.strips[2].number == 5
    assert st.strips[3].number is None and st.strips[3].name == ""
    assert st.strips[0].value_text == "+0.0 dB"
    assert st.strips[1].value_text == "-5.8 dB"
    assert st.connection.dirty_until == 10.1 + S.SETTLE_S
    assert st.connection.last_rx == 10.1


def test_led_maps_to_strips_transport_assignment():
    st = S.initial_state()
    st = S.reduce(st, P.Led(note=P.Note.MUTE + 2, on=True), 1.0)
    st = S.reduce(st, P.Led(note=P.Note.SOLO + 7, on=True), 1.0)
    st = S.reduce(st, P.Led(note=P.Note.REC + 0, on=True), 1.0)
    st = S.reduce(st, P.Led(note=P.Note.SELECT + 1, on=True), 1.0)
    st = S.reduce(st, P.Led(note=P.Note.PLAY, on=True), 1.0)
    st = S.reduce(st, P.Led(note=P.Note.STOP, on=False), 1.0)
    st = S.reduce(st, P.Led(note=P.Note.PAN, on=True), 1.0)
    st = S.reduce(st, P.Led(note=P.Note.FLIP, on=True), 1.0)
    st = S.reduce(st, P.Led(note=P.Note.BEATS_LED, on=True), 1.0)
    assert st.strips[2].mute and st.strips[7].solo and st.strips[0].rec and st.strips[1].select
    assert st.transport.play and not st.transport.stop
    assert st.assignment.mode == "pan" and st.assignment.flip
    assert st.time.mode == "beats"
    assert {P.Note.MUTE + 2, P.Note.PLAY, P.Note.PAN} <= st.leds_on
    st = S.reduce(st, P.Led(note=P.Note.PAN, on=False), 1.1)
    st = S.reduce(st, P.Led(note=P.Note.EQ, on=True), 1.1)
    assert st.assignment.mode == "eq"
    st = S.reduce(st, P.Led(note=P.Note.MUTE + 2, on=False), 1.2)
    assert not st.strips[2].mute and P.Note.MUTE + 2 not in st.leds_on


def test_fader_ring_meter():
    st = S.initial_state()
    st = S.reduce(st, P.FaderPos(channel=0, value=9990), 1.0)
    st = S.reduce(st, P.FaderPos(channel=8, value=12443), 1.0)
    st = S.reduce(st, P.VpotRing(channel=0, mode=1, pos=6, center=True), 1.0)
    st = S.reduce(st, P.Meter(channel=3, level=9), 1.0)
    assert st.strips[0].fader_raw == 9990
    assert st.master_fader == 12443
    assert st.strips[0].pan_ring == (1, 6, True)
    assert st.strips[3].meter == 9
    assert st.connection.last_display_change == 1.0  # 링은 표시 변화로 센다


def test_fixture_mute_feedback():
    st = replay(754.3)
    assert st.strips[0].mute is True
    assert st.lcd[1].startswith("Muted")
    st = replay(755.0)
    assert st.strips[0].mute is False


def test_fixture_numbers_and_values():
    st = replay(4563.6)
    assert [s.number for s in st.strips[:3]] == [1, 2, 5]
    assert st.strips[1].name == "StOu"
    st = replay(4570.6)
    assert st.strips[0].fader_raw == 9990
    assert st.strips[0].value_text == "-5.8 dB"
    st = replay(4631.0)
    assert st.strips[0].value_text == "+5"
    assert st.strips[0].pan_ring == (1, 6, False)
