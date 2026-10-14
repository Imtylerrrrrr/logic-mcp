import sys

import pytest

from logic_mcp.mcu import protocol as P
from tests.fakes import make_surface


def test_handshake_reply_is_sent_and_state_updates():
    surface, fake = make_surface()
    fake.feed(bytes.fromhex("F0 00 00 66 14 00 F7"))
    assert fake.sent == [P.handshake_reply(P.DeviceQuery(device=0x14))]
    assert surface.state.connection.state == "handshake"
    fake.feed(bytes.fromhex("F0 00 00 66 15 00 F7"))
    assert len(fake.sent) == 1


def test_wait_for_returns_true_when_reply_arrives_during_send():
    surface, fake = make_surface()
    fake.replies = lambda data: [P.button_down(P.Note.MUTE)] if data == P.button_down(P.Note.MUTE) else []
    surface.send(P.button_down(P.Note.MUTE))
    assert surface.wait_for(lambda s: s.strips[0].mute, timeout=0.2) is True


def test_wait_for_times_out():
    surface, fake = make_surface()
    assert surface.wait_for(lambda s: s.strips[0].mute, timeout=0.05) is False


def test_wait_settled_uses_clock():
    surface, fake = make_surface()
    fake.feed(bytes.fromhex("F0 00 00 66 14 12 00 41 F7"))
    # clock = fake.now + 1.0 이므로 dirty_until(now+0.12)을 이미 지났다
    assert surface.wait_settled(timeout=0.1) is True


def test_tick_promotes_to_ready():
    surface, fake = make_surface()
    fake.feed(bytes.fromhex("F0 00 00 66 14 12 00 41 F7"))
    assert surface.state.connection.state == "animating"
    surface.tick()
    assert surface.state.connection.state == "ready"


def test_start_stop_opens_and_closes_transport():
    surface, fake = make_surface()
    surface.start()
    assert fake.opened
    surface.stop()
    assert fake.closed


@pytest.mark.skipif(sys.platform != "darwin", reason="CoreMIDI 가상 포트")
def test_rtmidi_virtual_port_opens_and_closes():
    from logic_mcp.mcu.transport import RtMidiTransport
    t = RtMidiTransport(port_name="LogicMCP-test")
    t.open()
    t.send(bytes([0x90, 0x5E, 0x00]))
    t.close()
