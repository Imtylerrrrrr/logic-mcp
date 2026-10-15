import pytest

from logic_mcp.logic.modes import CONFIRM_S, EDIT_OPEN_S, ModeDriver, ModeError
from logic_mcp.mcu import protocol as P
from tests.fake_assign import make_assign_logic


def make():
    surface, fake, logic = make_assign_logic()
    return ModeDriver(surface, sleep=logic.sleep), surface, fake, logic


def test_focus_enter_eq_channel_and_leave_restores_pan_and_selection():
    d, surface, fake, logic = make()
    d.focus(2)
    assert surface.state.strips[2].select and logic.selected == 2
    d.enter("eq_channel")
    assert surface.state.view.kind == "eq_channel" and logic.view == "eq_channel"
    assert surface.state.view.columns[0][0] == "LoCutF "
    assert logic.tracks[2].eq is not None                       # 채널 뷰 진입이 Channel EQ를 삽입
    d.leave()
    assert surface.state.view.kind == "pan" and logic.view == "pan"
    assert logic.selected == 0 and surface.state.strips[0].select   # 이전 선택 복원


def test_enter_waits_out_mode_overlay():
    d, surface, fake, logic = make()
    d.enter("eq_mixer")
    assert "Parameter" not in surface.state.lcd[0]
    assert surface.state.view.columns[4][0] == "19:DCl "


def test_read_value_uses_overlay_then_column_after_redraw():    # Review Focus 1
    d, surface, fake, logic = make()
    d.focus(0)
    d.enter("eq_channel")
    assert d.tick(0, 1)
    v = d.read_value(0)
    assert v.number == 21.6 and v.unit == "Hz" and v.text == "21.6 Hz"
    assert surface.state.lcd[0].startswith("Low Cut Frequency")
    d.settle_overlay()
    name, v2 = d.read_column(0)
    assert name == "LoCutF" and v2.number == 21.6 and v2.text == "21.6Hz"


def test_read_column_retries_blank_blink():                     # Review Focus 2
    d, surface, fake, logic = make()
    d.focus(1)
    d.enter("plugin_mixer")
    d.tick(1, 2)
    d.settle_overlay()
    logic.blink_on = False
    logic.redraw()
    assert surface.state.view.columns[1][1].strip() == ""
    name, v = d.read_column(1)
    assert v.text == "ParEQ"                                     # 실측 축약("Parametric EQ")


def test_tick_splits_at_63_and_fader_never_sends_zero():        # Review Focus 5
    d, surface, fake, logic = make()
    d.focus(0)
    d.enter("eq_channel")
    fake.sent.clear()
    d.tick(1, 70)
    assert [m for m in fake.sent if m[0] == 0xB0] == [P.vpot_turn(1, 63), P.vpot_turn(1, 7)]
    d.flip(True)
    fake.sent.clear()
    d.fader(0, 0)
    assert bytes([0xE0, 1, 0]) in fake.sent and bytes([0xE0, 0, 0]) not in fake.sent


def test_flip_moves_faders_and_fader_sets_value():
    d, surface, fake, logic = make()
    d.focus(0)
    d.enter("eq_channel")
    d.flip(True)
    assert surface.state.assignment.flip
    assert surface.state.strips[0].fader_raw == 0 and surface.state.strips[7].fader_raw == 16383   # 20 Hz 최소, On 최대
    echoed = d.fader(0, 8192)
    assert echoed is not None and abs(logic.tracks[0].eq[0][0].value - 632.5) < 5
    assert d.read_value(0).unit == "Hz"
    d.leave()
    assert not surface.state.assignment.flip and surface.state.view.kind == "pan"


def test_enter_other_family_goes_through_pan_and_cancels_preselect():
    d, surface, fake, logic = make()
    d.focus(1)
    d.enter("plugin_mixer")
    d.tick(1, 2)
    assert logic.pre
    d.enter("eq_channel")
    assert P.button_down(P.Note.PAN) in fake.sent and not logic.pre
    assert surface.state.view.kind == "eq_channel"


def test_mode_error_when_logic_ignores_button_and_leave_safely():
    d, surface, fake, logic = make()
    logic.refuse.add(P.Note.EQ)
    with pytest.raises(ModeError):
        d.enter("eq_mixer")
    d.leave_safely()
    assert surface.state.view.kind == "pan" and d.last_leave_error == ""


def test_enter_eq_waits_out_hold_menu():                          # 실측 A
    d, surface, fake, logic = make()
    surface.send(P.button_down(P.Note.EQ))
    assert surface.state.view.kind == "eq_menu"                      # down 즉시 `E_`
    surface.send(P.button_up(P.Note.EQ))
    assert surface.state.view.kind == "eq_menu"                      # up의 응답은 기다리기 시작한 뒤에 온다
    d.leave()
    d.enter("eq_mixer")
    assert surface.state.view.kind == "eq_mixer" and surface.state.view.index == 1
    d.focus(0)
    d.enter("eq_channel")                                            # 두 번째 누름도 `E_`를 거친다
    assert surface.state.view.kind == "eq_channel"
    d.leave()
    assert surface.state.view.kind == "pan"


def test_plugin_channel_view_edit_page_name_value_and_restore():
    d, surface, fake, logic = make()
    logic.tracks[0].insert(2, "Compressor")
    d.focus(0)
    d.enter("plugin_channel")
    assert surface.state.view.kind == "plugin_channel" and surface.state.view.columns[1][1] == "Comprs "
    fake.sent.clear()
    assert d.press_vpot_until(1, lambda v: v.kind == "plugin_edit" and v.index == 2, EDIT_OPEN_S)
    assert not [m for m in fake.sent if m[0] == 0xB0] and not logic.pre       # 틱 없이 누름 = 값 보존 편집 뷰(실측 F)
    d.toggle_name_value()
    assert surface.state.view.page == (1, 3) and 'Ins.2 "Compressor (s/s)"' in surface.state.view.header
    assert d.probe_pages() == 3                                      # 헤더에 보이면 그대로
    d.page_to(2)
    assert surface.state.view.page == (2, 3)
    d.toggle_name_value()
    assert surface.state.view.columns[0] == ("Knee   ", "0.7    ")
    d.toggle_name_value()
    d.leave()
    assert surface.state.view.kind == "pan" and logic.name_mode is False   # NAME 모드도 되돌림


def test_probe_pages_with_truncated_page1_header():                 # 실측 L
    d, surface, fake, logic = make()
    logic.tracks[0].name = "Deluxe Classic"
    logic.tracks[0].insert(1, "Compressor")
    d.focus(0)
    d.enter("plugin_channel")
    assert d.press_vpot_until(0, lambda v: v.kind == "plugin_edit", EDIT_OPEN_S)
    d.toggle_name_value()
    assert surface.state.view.page is None and 'Ins.1 "Compressor (s/s)"' in surface.state.lcd[0]
    assert d.probe_pages() == 3 and logic.page == 1                  # 2페이지에서 읽고 1페이지로 돌아옴
    logic.tracks[0].insert(2, "Tuner")
    d.leave()
    d.enter("plugin_channel")
    assert d.press_vpot_until(1, lambda v: v.kind == "plugin_edit" and v.index == 2, EDIT_OPEN_S)
    d.toggle_name_value()
    assert d.probe_pages() == 1                                      # ▶에 반응 없으면 1페이지
    d.leave()


def test_preselect_ceil_model_reveal_minus_one_is_current_plus_one_is_next():   # 실측 E
    d, surface, fake, logic = make()
    logic.tracks[0].insert(1, "Parametric EQ")
    d.focus(0)
    d.enter("plugin_channel")
    d.tick(0, -1)
    assert d.read_overlay_name(0) == "Insert 1 Plug-in" and d.read_overlay_text(0) == "Parametric EQ (s/s)"
    d.leave(keep_select=True)
    d.enter("plugin_channel")
    d.tick(0, 1)
    assert d.read_overlay_text(0) == "Low Pass Filter (s/s)"         # +1은 다음 항목(누르면 교체됨)
    d.leave(keep_select=True)
    d.enter("plugin_channel")
    d.tick(1, -1)
    assert d.read_overlay_text(1) == "--"                            # 빈 슬롯은 0에서 포화
    for steps, want in ((1, "Parametric EQ (s/s)"), (1, "Parametric EQ (s/s)"), (1, "Low Pass Filter (s/s)"),
                        (-1, "Parametric EQ (s/s)")):
        d.tick(1, steps)
        assert d.read_overlay_text(1) == want
    d.leave()
    assert logic.tracks[0].inserts[1] == "Parametric EQ" and logic.tracks[0].inserts[2] is None


@pytest.mark.parametrize("vpot", [5, 6, 7])
def test_overlay_slots_6_to_8_share_columns_35_to_55(vpot):         # 실측 D
    d, surface, fake, logic = make()
    d.focus(0)
    d.enter("plugin_channel")
    d.tick(vpot, 2)
    assert d.read_overlay_name(vpot) == f"Insert {vpot + 1} Plug-in"
    assert d.read_overlay_text(vpot) == "Parametric EQ (s/s)"
    if vpot >= 6:
        assert surface.state.lcd[1][35:56] == " Parametric EQ (s/s) "   # 오른쪽 정렬 + 끝 공백 1
    d.leave()


def test_confirm_press_edit_view_arrives_after_overlay():          # 실측 K
    d, surface, fake, logic = make()
    d.focus(0)
    d.enter("plugin_channel")
    d.tick(2, 2)
    assert not d.press_vpot_until(2, lambda v: v.kind == "plugin_edit", 0.6)   # 0.6초에는 아직 PL
    assert surface.state.view.kind == "plugin_channel"
    assert d.wait_view(lambda v: v.kind == "plugin_edit" and v.index == 3, CONFIRM_S)
    assert logic.tracks[0].inserts[3] == "Parametric EQ"
    d.leave()


def test_cursor_does_nothing_in_plugin_mixer_and_channel_views():  # 실측 B·C
    d, surface, fake, logic = make()
    for kind in ("plugin_mixer", "plugin_channel"):
        d.enter(kind)
        before = (surface.state.view, surface.state.assignment.display)
        for note in (P.Note.CURSOR_DOWN, P.Note.CURSOR_UP, P.Note.CURSOR_RIGHT, P.Note.CURSOR_LEFT):
            d._press(note)
        assert (surface.state.view, surface.state.assignment.display) == before
    d.leave()


def test_tick_waits_quiet_before_return():                 # 실측 S: 틱 뒤 마지막 LCD 쓰기에서 0.4초 조용해져야 읽는다
    d, surface, fake, logic = make()
    d.focus(0)
    d.enter("plugin_channel")
    t0 = fake.now
    assert d.tick(0, 2) is True
    assert fake.now - t0 >= 0.4
    d.leave()


def _pitchbends(fake):
    return [m for m in fake.sent if m[0] & 0xF0 == 0xE0]


def test_fader_resends_when_first_move_is_dropped():            # 실측 Z1
    d, surface, fake, logic = make()
    logic.drop_first_fader = True
    d.focus(0)
    d.enter("eq_channel")
    d.flip(True)
    raw = logic.tracks[0].eq[0][0].raw()
    target = raw + 500
    fake.sent.clear()
    assert d.fader(0, target) == surface.state.strips[0].fader_raw != raw
    assert len(_pitchbends(fake)) == 2


def test_flip_does_not_press_again_when_first_press_is_dropped():    # 실측 Z2 → 리뷰 C1: 재누름 제거, 1.0초 뒤 ModeError
    d, surface, fake, logic = make()
    logic.drop_first_flip = True
    d.focus(0)
    d.enter("eq_channel")
    fake.sent.clear()
    with pytest.raises(ModeError):
        d.flip(True)
    assert sum(1 for m in fake.sent if m == P.button_down(P.Note.FLIP)) == 1
    assert not logic.flip and not surface.state.assignment.flip


def test_fader_refuses_to_send_while_flip_is_off():             # 리뷰 C1: Flip 꺼진 채 페이더는 트랙 볼륨을 움직인다
    d, surface, fake, logic = make()
    d.focus(0)
    d.enter("eq_channel")
    fake.sent.clear()
    with pytest.raises(ModeError):
        d.fader(0, 5000)
    assert _pitchbends(fake) == []
    assert logic.tracks[0].volume is None


def test_fader_does_not_resend_when_target_equals_current_raw():     # 리뷰 m2: 에코가 올 이유가 없다
    d, surface, fake, logic = make()
    d.focus(0)
    d.enter("eq_channel")
    d.flip(True)
    raw = surface.state.strips[1].fader_raw
    fake.sent.clear()
    d.fader(1, raw)
    assert len(_pitchbends(fake)) == 1


def test_leave_tries_every_step_even_when_name_toggle_fails():    # 리뷰 I2
    d, surface, fake, logic = make()
    d.focus(2)
    d.enter("eq_channel")
    d.toggle_name_value()
    d.flip(True)
    logic.drop_all_name_value = True
    with pytest.raises(ModeError) as ei:
        d.leave()
    assert "name" in str(ei.value)
    assert not logic.flip and not surface.state.assignment.flip
    assert surface.state.view.kind == "pan" and logic.view == "pan"
    assert logic.selected == 0 and d._focused is False


def test_enter_track_reads_outputs_and_restores_volume():               # 실측 Z5
    from tests.fake_assign import Track
    tracks = [Track(1, "1"), Track(2, "DeCl"), Track(3, "StOu", kind="output"), Track(6, "Mast", kind="master")]
    surface, fake, logic = make_assign_logic(tracks)
    d = ModeDriver(surface, sleep=logic.sleep)
    outs = d.read_strip_outputs()
    assert outs == ["St Out", "St Out", "", "", "", "", "", ""]
    assert logic.cs_param == 0 and surface.state.view.kind == "pan" and logic.view == "pan"
    pushes = [m for m in fake.sent if m[0] == 0x90 and P.Note.VPOT_PUSH <= m[1] < P.Note.VPOT_PUSH + 8 and m[2]]
    assert [m[1] - P.Note.VPOT_PUSH for m in pushes] == [4, 0]           # Output 선택 → Volume 복원, 그 밖은 누르지 않음


def test_track_param_refuses_when_menu_label_differs():                 # Review Focus 5
    from tests.fake_assign import Track
    surface, fake, logic = make_assign_logic([Track(1, "1"), Track(2, "DeCl")])
    logic.menu_labels = ["Volume", "Pan", "TrkFmt", "Input", "DisplP", "Auto", "Output", "Setup"]   # 다른 Logic 버전 흉내
    d = ModeDriver(surface, sleep=logic.sleep)
    with pytest.raises(ModeError):
        d.read_strip_outputs()
    pushes = [m for m in fake.sent if m[0] == 0x90 and P.Note.VPOT_PUSH <= m[1] < P.Note.VPOT_PUSH + 8 and m[2]]
    assert pushes == [] and logic.cs_param == 0
    assert not logic.track_held                                          # 버튼을 놓고 나온다
    d.leave_safely()
    assert surface.state.view.kind == "pan"
