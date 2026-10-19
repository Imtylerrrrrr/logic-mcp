from logic_mcp.logic.commands import Commands, ToolResult
from logic_mcp.logic.faders import FaderTable
from logic_mcp.mcu import protocol as P
from tests.fakes import make_surface

LCD_NUMBERED = bytes.fromhex("F0 00 00 66 14 12 00") + b"1:1    2:StOu 5:Mast                                    " + b"\xF7"


def make_commands(ready: bool = True):
    surface, fake = make_surface()
    cmds = Commands(surface, FaderTable.load(), sleep=lambda s: None, logic_running=lambda: True)
    if ready:
        fake.feed(LCD_NUMBERED)
        fake.feed(P.button_down(P.Note.PAN))      # PAN 모드 LED
        fake.feed(P.button_down(P.Note.BEATS_LED))
        surface.tick()
        assert surface.state.connection.state == "ready"
    return cmds, surface, fake


def echo_led(fake):
    """버튼 down을 받으면 같은 노트의 LED를 켜고, 이미 켜져 있으면 끄는 Logic 흉내."""
    lit: set[int] = set()

    def replies(data: bytes) -> list[bytes]:
        if len(data) == 3 and data[0] == 0x90 and data[2] == 0x7F:
            n = data[1]
            if n in lit:
                lit.discard(n)
                return [P.button_up(n)]
            lit.add(n)
            return [P.button_down(n)]
        return []
    fake.replies = replies
    return lit


def test_not_ready_refuses_without_sending():
    cmds, surface, fake = make_commands(ready=False)
    r = cmds.track("mute", strip=1)
    assert r.ok is False and fake.sent == []
    assert "wait_ready" in r.note


def test_address_validation():
    cmds, surface, fake = make_commands()
    assert cmds.track("mute").ok is False
    assert cmds.track("mute", strip=1, number=1).ok is False
    assert cmds.track("mute", strip=9).ok is False
    assert cmds.track("mute", strip=0).ok is False
    assert fake.sent == []
    r = cmds.track("mute", number=99)
    assert r.ok is False and "99" in r.note


def test_number_without_prefix_refused():
    cmds, surface, fake = make_commands(ready=False)
    fake.feed(bytes.fromhex("F0 00 00 66 14 12 00") + b"Audio 1St Out Master " + b"\xF7")
    surface.tick()
    r = cmds.track("mute", number=1)
    assert r.ok is False and "configure" in r.note and fake.sent == []


def test_mute_verified_then_skipped_then_unmute():
    cmds, surface, fake = make_commands()
    echo_led(fake)
    r = cmds.track("mute", strip=1)
    assert isinstance(r, ToolResult)
    assert r.ok and r.verified == "verified"
    assert r.target == {"strip": 1, "number": 1, "name": "1"}
    assert r.before["mute"] is False and r.after["mute"] is True
    assert fake.sent == [P.button_down(P.Note.MUTE), P.button_up(P.Note.MUTE)]
    r2 = cmds.track("mute", strip=1)
    assert r2.ok and r2.verified == "skipped" and len(fake.sent) == 2
    r3 = cmds.track("unmute", number=1)
    assert r3.ok and r3.verified == "verified" and r3.after["mute"] is False


def test_solo_arm_select_use_right_notes():
    cmds, surface, fake = make_commands()
    echo_led(fake)
    assert cmds.track("solo", strip=3).after["solo"] is True
    assert fake.sent[0] == P.button_down(P.Note.SOLO + 2)
    assert cmds.track("arm", strip=8).after["rec"] is True
    assert fake.sent[2] == P.button_down(P.Note.REC + 7)
    assert cmds.track("select", strip=2).after["select"] is True
    assert fake.sent[4] == P.button_down(P.Note.SELECT + 1)


def test_timeout_when_no_feedback():
    cmds, surface, fake = make_commands()
    r = cmds.track("mute", strip=1)
    assert r.ok is False and r.verified == "timeout"
    assert r.elapsed_ms >= 0


def test_status_fields():
    cmds, surface, fake = make_commands()
    s = cmds.status()
    assert s["state"] == "ready" and s["name_format_ok"] is True
    assert s["assignment_mode"] == "pan" and s["logic_running"] is True
    assert s["visible_numbers"] == [1, 2, 5]


import math


def test_transport_play_stop_cycle():
    cmds, surface, fake = make_commands()
    lit = echo_led(fake)
    r = cmds.transport("play")
    assert r.ok and r.verified == "verified" and r.after["play"] is True
    assert cmds.transport("play").verified == "skipped"
    r = cmds.transport("stop")
    assert r.ok and r.after["stop"] is True
    r = cmds.transport("cycle_on")
    assert r.ok and r.after["cycle"] is True
    r = cmds.transport("cycle_off")
    assert r.ok and r.after["cycle"] is False
    assert cmds.transport("dance").ok is False


def test_transport_rewind_verified_by_time_change():
    cmds, surface, fake = make_commands()
    fake.replies = lambda d: [bytes([0xB0, 0x47, 0x32])] if d == P.button_down(P.Note.REWIND) else []
    r = cmds.transport("rewind")
    assert r.ok and r.verified == "verified"
    assert fake.sent[:2] == [P.button_down(P.Note.REWIND), P.button_up(P.Note.REWIND)]


def fader_echo(fake, quantize=lambda v: v):
    def replies(data: bytes) -> list[bytes]:
        if data[0] & 0xF0 == 0xE0:
            ch = data[0] & 0x0F
            v = quantize(data[1] | (data[2] << 7))
            return [bytes([0xE0 | ch, v & 0x7F, v >> 7])]
        return []
    fake.replies = replies


def test_set_volume_verified_with_quantized_echo():
    cmds, surface, fake = make_commands()
    fader_echo(fake, quantize=lambda v: v - 10)
    r = cmds.mixer_volume(strip=1, number=None, db=-5.8)
    assert r.ok and r.verified == "verified"
    assert fake.sent == P.fader_move(0, 9990)
    assert r.after["fader_raw"] == 9980


def test_set_volume_clamps_and_notes():
    cmds, surface, fake = make_commands()
    fader_echo(fake)
    r = cmds.mixer_volume(strip=1, number=None, db=12.0)
    assert r.ok and "clamp" in r.note and fake.sent[1] == bytes([0xE0, 14845 & 0x7F, 14845 >> 7])
    r = cmds.mixer_volume(strip=1, number=None, db=-math.inf)
    assert r.ok and fake.sent[-2] == bytes([0xE0, 0x00, 0x00])
    r = cmds.mixer_volume(strip=1, number=None, db=math.nan)
    assert r.ok is False and "NaN" in r.note


def test_set_volume_unverified_when_echo_far():
    cmds, surface, fake = make_commands()
    fake.feed(bytes([0xE0, 0x1B, 0x61]))  # 페이더 1 = 12443 에서 시작
    fader_echo(fake, quantize=lambda v: 0)
    r = cmds.mixer_volume(strip=1, number=None, db=0.0)
    assert r.ok is False and r.verified == "unverified"


def lcd_row2(text: bytes) -> bytes:
    return bytes.fromhex("F0 00 00 66 14 12 38") + text + b"\xF7"


def test_set_pan_reads_lcd_and_sends_delta():
    cmds, surface, fake = make_commands()
    fake.feed(lcd_row2(b"0      "))
    fake.replies = lambda d: [lcd_row2(b"+10    ")] if d == P.vpot_turn(0, 10) else []
    r = cmds.mixer_pan(strip=1, number=None, pan=10)
    assert r.ok and r.verified == "verified" and r.after["value_text"] == "+10"
    assert fake.sent == [P.vpot_turn(0, 10)]
    assert cmds.mixer_pan(strip=1, number=None, pan=10).verified == "skipped"


def test_set_pan_second_nudge_then_unverified():
    cmds, surface, fake = make_commands()
    fake.feed(lcd_row2(b"0      "))
    fake.replies = lambda d: [lcd_row2(b"+7     ")]
    r = cmds.mixer_pan(strip=1, number=None, pan=10)
    assert r.ok is False and r.verified == "unverified"
    assert fake.sent == [P.vpot_turn(0, 10), P.vpot_turn(0, 3)]


def test_set_pan_refused_outside_pan_mode_or_bad_text():
    cmds, surface, fake = make_commands()
    fake.feed(lcd_row2(b"0      "))
    fake.feed(P.button_up(P.Note.PAN))
    fake.feed(P.button_down(P.Note.EQ))
    r = cmds.mixer_pan(strip=1, number=None, pan=5)
    assert r.ok is False and "eq" in r.note and fake.sent == []
    fake.feed(P.button_up(P.Note.EQ))
    fake.feed(P.button_down(P.Note.PAN))
    fake.feed(lcd_row2(b"-      "))
    r = cmds.mixer_pan(strip=1, number=None, pan=5)
    assert r.ok is False and "configure" in r.note and fake.sent == [P.vpot_turn(0, 1)]
    assert cmds.mixer_pan(strip=1, number=None, pan=64).ok is False


def lcd_row1(text: bytes) -> bytes:
    return bytes.fromhex("F0 00 00 66 14 12 00") + text.ljust(56) + b"\xF7"


class BankSim:
    """번호 1..n 트랙을 8개씩 보여주는 Logic 흉내. OPTION+BANK◀=첫 세트, BANK▶=+8(끝에서 클램프)."""

    def __init__(self, fake, n: int):
        self.fake, self.n, self.start, self.option = fake, n, 1, False
        fake.replies = self.replies

    def row(self) -> bytes:
        cols = [f"{i}:T{i}".ljust(7)[:7].encode() for i in range(self.start, self.start + 8) if i <= self.n]
        return b"".join(cols)

    def replies(self, data: bytes) -> list[bytes]:
        if data == P.button_down(P.Note.OPTION):
            self.option = True
            return []
        if data == P.button_up(P.Note.OPTION):
            self.option = False
            return []
        if data == P.button_down(P.Note.BANK_RIGHT):
            new = min(self.start + 8, max(1, self.n - 7)) if self.n > 8 else 1
            if self.option:
                new = max(1, self.n - 7)
        elif data == P.button_down(P.Note.BANK_LEFT):
            new = 1 if self.option else max(1, self.start - 8)
        elif data == P.button_down(P.Note.CHANNEL_RIGHT):
            new = min(self.start + 1, max(1, self.n - 7))
        elif data == P.button_down(P.Note.CHANNEL_LEFT):
            new = max(1, self.start - 1)
        else:
            return []
        if new == self.start:
            return []
        self.start = new
        return [lcd_row1(self.row())]


def test_bank_right_left_first_last():
    cmds, surface, fake = make_commands()
    sim = BankSim(fake, 19)
    fake.feed(lcd_row1(sim.row()))
    r = cmds.bank("right")
    assert r.ok and r.verified == "verified" and r.after["visible_numbers"][0] == 9
    r = cmds.bank("right")
    assert r.after["visible_numbers"] == list(range(12, 20))
    r = cmds.bank("right")
    assert r.ok is False and r.verified == "unverified" and "변화 없음" in r.note
    r = cmds.bank("first")
    assert r.ok and r.after["visible_numbers"][0] == 1
    assert fake.sent[-3:] == [P.button_down(P.Note.BANK_LEFT), P.button_up(P.Note.BANK_LEFT), P.button_up(P.Note.OPTION)]
    r = cmds.bank("last")
    assert r.after["visible_numbers"][-1] == 19
    r = cmds.bank("channel_left")
    assert r.after["visible_numbers"][0] == 11


def test_show_number_navigates_and_track_by_number_in_other_bank():
    cmds, surface, fake = make_commands()
    sim = BankSim(fake, 19)
    fake.feed(lcd_row1(sim.row()))
    r = cmds.bank("show", number=14)
    assert r.ok and 14 in r.after["visible_numbers"]
    r = cmds.bank("show", number=14)
    assert r.verified == "skipped"
    r = cmds.bank("show", number=40)
    assert r.ok is False and "40" in r.note
    # number 주소가 다른 뱅크에 있어도 track이 알아서 옮긴다
    old = fake.replies
    def replies(data: bytes) -> list[bytes]:
        out = old(data)
        if data == P.button_down(P.Note.MUTE + 2) and sim.start == 9:
            out.append(P.button_down(P.Note.MUTE + 2))
        return out
    fake.replies = replies
    r = cmds.track("mute", number=11)
    assert r.ok and r.target == {"strip": 3, "number": 11, "name": "T11"}


def test_configure_turns_on_numbers_and_value_mode_and_beats():
    cmds, surface, fake = make_commands(ready=False)
    fake.feed(lcd_row1(b"Audio 1St Out Master "))
    fake.feed(P.button_down(P.Note.SMPTE_LED))
    fake.feed(bytes([0xE0, 0x00, 0x60]))      # 페이더 1 위치 수신
    surface.tick()
    state = {"numbers": False, "value": False, "beats": False}

    def replies(data: bytes) -> list[bytes]:
        if data == P.button_down(P.Note.NAME_VALUE) and P.button_down(P.Note.OPTION) in fake.sent[-2:]:
            state["numbers"] = True
            return [lcd_row1(b"1:Audio2:St Ou3:Maste")]
        if data == P.button_down(P.Note.NAME_VALUE):
            state["value"] = True
            return []
        if data[0] & 0xF0 == 0xE0:
            return [lcd_row2(b"+0.0 dB" if state["value"] else b"Volume ")]
        if data == P.button_down(P.Note.SMPTE_BEATS):
            state["beats"] = True
            return [P.button_up(P.Note.SMPTE_LED), P.button_down(P.Note.BEATS_LED)]
        return []
    fake.replies = replies
    r = cmds.configure()
    assert r.ok and state == {"numbers": True, "value": True, "beats": True}
    assert cmds.status()["configured"] is True and cmds.status()["name_format_ok"] is True
    r2 = cmds.configure()
    assert r2.ok and r2.verified == "skipped"


def test_configure_without_known_fader_skips_probe():
    cmds, surface, fake = make_commands()        # 번호 켜짐, FaderPos 없음
    assert surface.state.strips[0].fader_known is False
    r = cmds.configure()
    assert r.verified == "unverified" and "페이더 1" in r.note
    assert not any(m[0] & 0xF0 == 0xE0 for m in fake.sent)
    assert P.button_down(P.Note.NAME_VALUE) not in fake.sent


def test_configure_requires_ready():
    cmds, surface, fake = make_commands(ready=False)
    fake.feed(lcd_row1(b"1:Audio2:St Ou3:Maste"))
    assert surface.state.connection.state == "animating"
    r = cmds.configure()
    assert r.verified == "skipped" and "wait_ready" in r.note
    assert fake.sent == []


def test_configure_restores_name_value_toggle_on_failure():
    cmds, surface, fake = make_commands()
    fake.feed(bytes([0xE0, 0x00, 0x60]))
    surface.tick()
    r = cmds.configure()                         # dB 텍스트가 끝내 안 뜸
    assert r.verified == "unverified" and "되돌려 눌렀음" in r.note
    assert fake.sent.count(P.button_down(P.Note.NAME_VALUE)) == 2


def test_wait_ready():
    cmds, surface, fake = make_commands(ready=False)
    r = cmds.wait_ready(0.05)
    assert r.ok is False and r.verified == "timeout"
    assert "모달 대화상자" in r.note  # logic_running=True: Z10 힌트
    fake.feed(lcd_row1(b"1:1"))
    surface.tick()
    assert cmds.wait_ready(0.05).ok is True


def _reveal_setup():
    cmds, surface, fake = make_commands()
    fake.feed(lcd_row2(b"+0.0 dB"))
    return cmds, surface, fake


def test_set_pan_reveals_value_when_lcd_shows_db():
    cmds, surface, fake = _reveal_setup()

    def replies(d: bytes) -> list[bytes]:
        if d == P.vpot_turn(0, 1):
            return [lcd_row2(b"+1     ")]
        if d == P.vpot_turn(0, 9):
            return [lcd_row2(b"+10    ")]
        return []
    fake.replies = replies
    r = cmds.mixer_pan(1, None, 10)
    assert r.ok is True and r.verified == "verified" and "드러내려고" in r.note
    assert fake.sent.index(P.vpot_turn(0, 1)) < fake.sent.index(P.vpot_turn(0, 9))


def test_set_pan_skipped_when_reveal_shows_no_pan_text():
    cmds, surface, fake = _reveal_setup()
    fake.replies = lambda d: []
    r = cmds.mixer_pan(1, None, 10)
    assert r.verified == "skipped" and "LCD 2행이 팬 값이 아님" in r.note
    assert fake.sent.count(P.vpot_turn(0, 1)) == 1 and len(fake.sent) == 1


from tests.fake_assign import make_assign_logic


def test_mixer_pan_leaves_assign_mode_and_flip_first():
    surface, fake, logic = make_assign_logic()
    cmds = Commands(surface, FaderTable.load(), sleep=logic.sleep, logic_running=lambda: True)
    cmds.modes.enter("eq_channel")
    cmds.modes.flip(True)
    r = cmds.mixer_pan(1, None, 0)
    assert P.button_down(P.Note.FLIP) in fake.sent and P.button_down(P.Note.PAN) in fake.sent
    assert surface.state.view.kind == "pan" and not surface.state.assignment.flip
    assert r.verified == "skipped" and r.note == "already"        # 가짜의 팬 값 0
