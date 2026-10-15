import pytest

from logic_mcp.logic.modes import ModeDriver, ModeError
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
    assert v.text == "Parame"                                    # 가짜의 6자 축약("Parametric EQ")


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


def test_slot_page_name_value_navigation_and_restore():
    d, surface, fake, logic = make()
    logic.tracks[0].insert(2, "Compressor")
    d.focus(0)
    d.enter("plugin_mixer")
    d.slot_to(2)
    assert surface.state.view.index == 2 and surface.state.view.columns[0][1] == "Compre "
    assert d.press_vpot(0) and surface.state.view.kind == "plugin_edit"
    d.toggle_name_value()
    assert surface.state.view.page == (1, 2) and 'Ins.2 "Compressor (s/s)"' in surface.state.view.header
    d.page_to(2)
    assert surface.state.view.page == (2, 2)
    d.toggle_name_value()
    assert surface.state.view.columns[0] == ("AutoGa ", "Off    ")
    d.toggle_name_value()
    d.leave()
    assert surface.state.view.kind == "pan" and logic.name_mode is False   # NAME 모드도 되돌림


def test_slot_up_from_one_reaches_midi_fx_and_back():
    d, surface, fake, logic = make()
    d.enter("plugin_mixer")
    with pytest.raises(ModeError):
        d.slot_to(0)
    assert surface.state.view.kind == "midi_fx"
    d.leave()
    assert surface.state.view.kind == "pan"
