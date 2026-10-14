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
