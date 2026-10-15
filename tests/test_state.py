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


def test_time_display_parse_from_fixture():
    st = replay(755.7)
    assert st.transport.play is True and st.transport.stop is False
    assert st.time.mode == "beats"
    parsed = st.time.parsed()
    assert parsed is not None and parsed["bars"] == 1
    st = replay(757.2)
    assert st.transport.stop is True and st.transport.play is False
    assert st.time.parsed() == {"bars": 1, "beats": 4, "division": 1, "ticks": 66}


def test_connection_rebind_without_handshake_becomes_ready():
    # 픽스처 시작(183s)은 핸드셰이크 없이 LCD부터 온다(이름으로 재바인딩)
    st = replay(184.5)
    assert st.connection.state in ("animating", "ready")
    st = replay(200.0)
    assert st.connection.state == "ready"


def test_connection_handshake_animating_ready_from_fixture():
    st = replay(665.401)
    assert st.connection.state == "handshake"
    st = replay(666.5)  # 첫 LCD 쓰기는 666.122초
    assert st.connection.state == "animating"
    st = replay(700.0)
    assert st.connection.state == "animating"
    st = replay(745.0)
    assert st.connection.state == "animating"
    st = replay(747.5)
    assert st.connection.state == "ready"
    st = replay(754.3)
    assert st.connection.state == "ready" and st.strips[0].mute


def test_stale_flag():
    st = S.initial_state()
    st = S.reduce(st, P.LcdWrite(offset=0, text=b"1:1"), 100.0)
    st = S.tick(st, 101.5)
    assert st.connection.state == "ready" and not st.connection.stale
    st = S.tick(st, 131.0)
    assert st.connection.stale is True
    st = S.reduce(st, P.Led(note=P.Note.PLAY, on=True), 131.0)
    st = S.tick(st, 170.0)
    assert st.connection.stale is False  # 재생 중엔 stale 아님
    st = S.reduce(st, P.Led(note=P.Note.PLAY, on=False), 170.0)
    st = S.tick(st, 201.0)
    assert st.connection.stale is True


def test_install_requires_long_quiet():
    st = S.initial_state()
    st = S.reduce(st, P.DeviceQuery(device=P.DEVICE_ID), 100.0)
    st = S.reduce(st, P.LcdWrite(offset=0, text=b"1:1"), 101.0)
    st = S.tick(st, 103.0)
    assert st.connection.state == "animating" and st.connection.installing is True
    st = S.tick(st, 111.1)
    assert st.connection.state == "ready" and st.connection.installing is False


def test_requery_after_ready_requires_install_quiet_again():
    s = S.initial_state()
    s = S.reduce(s, P.LcdWrite(offset=0, text=b"hi"), 100.0)
    s = S.tick(s, 101.5)
    assert s.connection.state == "ready"
    s = S.reduce(s, P.DeviceQuery(device=P.DEVICE_ID), 200.0)
    assert S.tick(s, 201.0).connection.state == "handshake"
    assert S.tick(s, 209.0).connection.state != "ready"
    assert S.tick(s, 210.1).connection.state == "ready"


def lcd_ev(offset: int, text: str) -> P.LcdWrite:
    return P.LcdWrite(offset=offset, text=text.encode("latin1"))


def digit_evs(d: str) -> list[P.AssignDigit]:
    return [P.AssignDigit(index=0, char=d[0], dot=False), P.AssignDigit(index=1, char=d[1], dot=False)]


def apply(st: S.SurfaceState, evs, now: float = 100.0) -> S.SurfaceState:
    for ev in evs:
        st = S.reduce(st, ev, now)
    return st


ROW_NAMES = "15:DCl 16:DCl 17:DCl 18:DCl 19:DCl 20:DCl 21:SOu 24:Mas "
PAN_ROW2 = "0      0      0      0      0      0      0             "
EQ_ROW1 = "LoCutF LoCutS LoCutQ LCO/Of LoShF  LoShGa LoShQ  LSO/Of "
EQ_ROW2 = "20.0Hz 12     0.71   Off    75.0Hz 0.0 dB 1.00   On     "


def ready_pan() -> S.SurfaceState:
    return apply(S.initial_state(), [lcd_ev(0, ROW_NAMES + PAN_ROW2)] + digit_evs("PN"))


def test_view_pan_and_values():
    st = ready_pan()
    assert st.view.kind == "pan" and st.view.index is None
    assert st.strips[0].number == 15 and st.strips[0].value_text == "0"
    assert st.view.columns[7] == ("24:Mas ", "       ")


def test_view_eq_mixer_keeps_values_and_numbers_under_overlay():
    st = ready_pan()
    st = apply(st, digit_evs("E1") + [
        lcd_ev(0, ROW_NAMES + "20.0Hz" + " " * 50),
        lcd_ev(21, " EQ 1 Parameter: Low Cut Frequency"),
    ])
    assert (st.view.kind, st.view.index) == ("eq_mixer", 1)
    assert st.strips[0].value_text == "0"       # 2행은 EQ 값. 팬/볼륨 값으로 받지 않음
    assert st.strips[0].number == 15 and st.strips[4].number == 19   # 오버레이가 덮은 열은 이전 번호 유지
    assert st.view.columns[0] == ("15:DCl ", "20.0Hz ")


def test_view_eq_channel_columns_preserve_strips():
    st = apply(ready_pan(), digit_evs("EQ") + [lcd_ev(0, EQ_ROW1 + EQ_ROW2)])
    assert st.view.kind == "eq_channel"
    assert st.view.columns[1] == ("LoCutS ", "12     ") and st.view.columns[5] == ("LoShGa ", "0.0 dB ")
    assert st.strips[0].number == 15 and st.strips[0].name == "DCl" and st.strips[0].value_text == "0"


def test_view_plugin_kinds():
    st = ready_pan()
    st = apply(st, digit_evs("P1") + [lcd_ev(0, ROW_NAMES + "Cha EQ --     --     --     --     --     --            ")])
    assert (st.view.kind, st.view.index) == ("plugin_mixer", 1)
    st = apply(st, digit_evs("PL") + [lcd_ev(0, "Ins1Pl Ins2Pl Ins3Pl Ins4Pl Ins5Pl Ins6Pl Ins7Pl Ins8Pl "
                                                "Cha EQ --     --     --     --     --     --     --     ")])
    assert st.view.kind == "plugin_channel"
    st = apply(st, digit_evs("P1") + [lcd_ev(0, "LoCutS LoShGa Pea1Ga Pea2Ga Pea3Ga Pea4Ga HiShGa HiCutS "
                                                "12     0.0 dB 0.0 dB 0.0 dB 0.0 dB 0.0 dB 0.0 dB 24     ")])
    assert (st.view.kind, st.view.index, st.view.page) == ("plugin_edit", 1, None)
    assert st.strips[0].number == 15                                  # 편집 뷰 1행은 채널명이 아님
    header = 'Track 15 "15:Deluxe Classic" Ins.1 "Channe      Page 2/6'      # 56칸
    st = apply(st, [lcd_ev(0, header + "LoCutF LoShF  Peak1F Peak2F Peak3F Peak4F HiShF  HiCutF ")])
    assert st.view.kind == "plugin_edit" and st.view.page == (2, 6)
    assert st.view.header.startswith('Track 15 "15:Deluxe Classic" Ins.1')
    st = apply(st, [lcd_ev(0, "-      " * 8 + " " * 56)])
    assert st.view.kind == "empty_edit"
    st = apply(st, digit_evs("M1"))
    assert (st.view.kind, st.view.index) == ("midi_fx", 1)
    st = apply(st, digit_evs("10") + [lcd_ev(0, ROW_NAMES + " " * 56)])
    assert (st.view.kind, st.view.index) == ("plugin_mixer", 10)


def test_view_send_kinds_and_menus():
    st = ready_pan()
    for d, kind, idx in [("S1", "send_mixer", 1), ("SE", "send_channel", None), ("D1", "send_destlevel", 1),
                         ("S_", "send_menu", None), ("E_", "eq_menu", None), ("PN", "pan", None)]:
        st = apply(st, digit_evs(d))
        assert (st.view.kind, st.view.index) == (kind, idx), d


def test_view_unknown_display_keeps_spec1_behaviour():
    st = apply(S.initial_state(), [lcd_ev(0, ROW_NAMES + PAN_ROW2)])      # 2자리 표시가 아직 없음
    assert st.view.kind == "pan" and st.strips[0].number == 15 and st.strips[0].value_text == "0"
    st = apply(st, digit_evs("tr") + [lcd_ev(56, "+0.0dB ")])
    assert st.view.kind == "unknown" and st.strips[0].value_text == "+0.0dB"


def test_fixture_assign1_view_kinds():
    seen, st = set(), S.initial_state()
    for ts, _, data in P.load_fixture(Path(__file__).parent / "fixtures" / "mcu" / "cap_assign1.log"):
        st = S.reduce(st, P.decode(data), ts)
        seen.add(st.view.kind)
    assert {"pan", "eq_mixer", "eq_channel", "eq_menu", "send_mixer", "send_channel", "send_menu",
            "plugin_mixer", "plugin_channel", "plugin_edit", "midi_fx"} <= seen
    assert st.view.kind == "pan"


def test_view_plugin_channel_by_code_only():                       # 실측 J
    st = ready_pan()
    overlay = "Insert 1 Plug-in     " + "Ins4Pl Ins5Pl Ins6Pl Ins7Pl Ins8Pl "   # 슬롯 1 오버레이가 1행 `Ins1Pl`을 덮음
    st = apply(st, digit_evs("PL") + [lcd_ev(0, overlay + "Parametric EQ (s/s)  --     --     --     --     --     ")])
    assert (st.view.kind, st.view.index) == ("plugin_channel", None)
    assert st.strips[0].number == 15                                  # PL 1행은 채널명이 아님
    st = apply(st, digit_evs("P1") + [lcd_ev(0, "Ins1Pl Ins2Pl Ins3Pl Ins4Pl Ins5Pl Ins6Pl Ins7Pl Ins8Pl "
                                                "ParEQ  --     --     --     --     --     --     --     ")])
    assert (st.view.kind, st.view.index) == ("plugin_edit", 1)        # `Ins1Pl` 1행이라도 P<n> 코드면 PL이 아님
