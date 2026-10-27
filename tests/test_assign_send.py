import math

import pytest

from logic_mcp.logic.commands import Commands
from logic_mcp.logic.faders import FaderTable
from logic_mcp.mcu import protocol as P
from tests.fake_assign import Send, Track, make_assign_logic


def make(tracks=None):
    surface, fake, logic = make_assign_logic(tracks)
    cmds = Commands(surface, FaderTable.load(), sleep=logic.sleep, logic_running=lambda: True)
    return cmds, surface, fake, logic


def pushes(msgs: list[bytes]) -> list[int]:
    return [m[1] - P.Note.VPOT_PUSH for m in msgs if m[0] == 0x90 and P.Note.VPOT_PUSH <= m[1] < P.Note.VPOT_PUSH + 8 and m[2]]


def test_get_reads_all_eight_sends_by_column_position():
    cmds, surface, fake, logic = make()
    logic.tracks[0].sends[1] = Send("Bus 2", -6.0, 0, False)
    logic.tracks[0].sends[4] = Send("Bus 5", float("-inf"), 2, True)
    r = cmds.send.get(strip=1, number=None)
    assert r.verified == "verified" and r.action == "send_get" and r.target == {"strip": 1, "number": 15, "name": "DCl"}
    s = r.after["sends"]
    assert len(s) == 8
    assert s["1"] == {"send": 1, "present": True, "dest": "Bus 2", "bus": 2, "level_db": -6.0, "pos": "pre", "muted": False,
                      "text": ["Bus 2", "-6.0dB", "Pre", "active"]}
    assert s["4"]["bus"] == 5 and s["4"]["level_db"] == -math.inf and s["4"]["pos"] == "post_pan" and s["4"]["muted"] is True
    assert s["2"]["present"] is False and s["8"]["present"] is False
    assert surface.state.view.kind == "pan" and logic.selected == 0


def test_get_reads_from_remembered_page():                                          # Review Focus 4, 실측 S3
    cmds, surface, fake, logic = make()
    logic.tracks[0].se_page = 3
    logic.tracks[0].sends[1] = Send("Bus 1")
    r = cmds.send.get(strip=1, number=None)
    assert r.after["sends"]["1"]["bus"] == 1 and r.after["sends"]["5"]["present"] is False


def test_set_dest_bus_3_confirms_and_notes_aux_creation():                          # 실측 S4·S5
    cmds, surface, fake, logic = make()
    cmds.strips.follows(cmds.modes, surface.state, 0)           # 스트립 종류 판별(TRACK 메뉴 누름)은 미리 끝내 둔다
    n0 = len(fake.sent)
    r = cmds.send.set_dest(strip=1, number=None, send=1, dest="Bus 3")
    assert r.ok and r.verified == "verified" and r.action == "send_set_dest" and "Aux" in r.note
    s = logic.tracks[0].sends[1]
    assert s is not None and s.dest == "Bus 3" and s.level == -math.inf and s.pos == 2 and not s.muted
    assert r.before["present"] is False and r.after["bus"] == 3 and r.after["present"] is True
    assert pushes(fake.sent[n0:]) == [0] and surface.state.view.kind == "pan" and not logic.pre


@pytest.mark.parametrize("prefix", [[], ["1", "2", "3", "4"]])
def test_set_dest_adjusts_when_prefix_count_differs(prefix):                        # Review Focus 2
    cmds, surface, fake, logic = make()
    logic.dest_list = ["--"] + prefix + [f"Bus {i}" for i in range(1, 9)]
    r = cmds.send.set_dest(strip=1, number=None, send=2, dest=2)
    assert r.verified == "verified" and logic.tracks[0].sends[2].dest == "Bus 2"


def test_set_dest_does_not_press_when_overlay_mismatches():                         # Review Focus 2
    cmds, surface, fake, logic = make()
    logic.dest_list = ["--", "1", "2"] + [f"Bus {i}" for i in (1, 2, 3, 5, 6, 7, 8, 9)]   # Bus 4 없음
    cmds.strips.follows(cmds.modes, surface.state, 0)           # 스트립 종류 판별(TRACK 메뉴 누름)은 미리 끝내 둔다
    n0 = len(fake.sent)
    r = cmds.send.set_dest(strip=1, number=None, send=1, dest="Bus 4")
    assert r.verified == "unverified" and "확정하지 않음" in r.note
    assert pushes(fake.sent[n0:]) == [] and logic.tracks[0].sends[1] is None and not logic.pre
    assert surface.state.view.kind == "pan"


def test_set_dest_already_and_remove():
    cmds, surface, fake, logic = make()
    logic.tracks[0].sends[3] = Send("Bus 2")
    r = cmds.send.set_dest(strip=1, number=None, send=3, dest="2")
    assert r.verified == "skipped" and r.note == "already"
    r = cmds.send.remove(strip=1, number=None, send=3)
    assert r.verified == "verified" and r.action == "send_remove" and logic.tracks[0].sends[3] is None
    assert r.after["present"] is False and r.before["bus"] == 2
    r = cmds.send.remove(strip=1, number=None, send=3)
    assert r.verified == "skipped" and r.note == "already"


def test_remove_non_bus_destination_is_verified_by_presence():                    # 리뷰 I1
    cmds, surface, fake, logic = make()
    logic.tracks[0].sends[1] = Send("1")                                              # 버스가 아닌 목적지(실측 S4 앞 항목)
    r = cmds.send.remove(strip=1, number=None, send=1)
    assert r.ok and r.verified == "verified" and r.action == "send_remove"
    assert logic.tracks[0].sends[1] is None and r.before["present"] is True and r.after["present"] is False


@pytest.mark.parametrize("existing,dest", [(None, "Bus 2"), (Send("Bus 1"), "Bus 2"), (Send("Bus 2"), "--")])
def test_set_dest_unverified_when_confirm_push_is_dropped(existing, dest):          # 리뷰 I2: 미리 선택 깜박임은 계속됨(S4)
    cmds, surface, fake, logic = make()
    logic.tracks[0].sends[1] = existing
    cmds.strips.follows(cmds.modes, surface.state, 0)           # 스트립 종류 판별(TRACK 메뉴 누름)은 미리 끝내 둔다
    logic.refuse = {P.Note.VPOT_PUSH + 0}                                             # dest 열 확정 누름 드롭
    r = cmds.send.set_dest(strip=1, number=None, send=1, dest=dest)
    assert not r.ok and r.verified == "unverified" and "깜박임" in r.note
    s = logic.tracks[0].sends[1]
    assert (s.dest if s else None) == (existing.dest if existing else None) and not logic.timers
    assert surface.state.view.kind == "pan" and not logic.pre


def test_set_dest_rejects_bad_dest_and_send():
    cmds, surface, fake, logic = make()
    r = cmds.send.set_dest(strip=1, number=None, send=1, dest="Aux 1")
    assert r.verified == "skipped" and "버스 번호" in r.note
    assert cmds.send.set_dest(strip=1, number=None, send=9, dest=1).verified == "skipped"
    assert cmds.send.set_dest(strip=1, number=None, send=1, dest=1).ok   # 정상 경로는 그대로
    assert surface.state.view.kind == "pan"


def test_set_dest_on_output_strip_is_skipped():                                     # Review Focus 1, 실측 Z4·S10
    cmds, surface, fake, logic = make([Track(1, "1"), Track(3, "StOu", kind="output")])
    r = cmds.send.set_dest(strip=2, number=None, send=1, dest=1)
    assert r.verified == "skipped" and "출력" in r.note
    assert all(s is None for t in logic.tracks for s in t.sends.values()) and surface.state.view.kind == "pan"
    assert cmds.send.get(strip=2, number=None).verified == "skipped"


def test_set_dest_on_aux_strip_is_skipped():                                        # 실전 F2·실측 Z19: SE가 Aux를 따라가지 않음
    cmds, surface, fake, logic = make([Track(1, "1"), Track(5, "Aux1", kind="aux")])
    r = cmds.send.set_dest(strip=2, number=None, send=1, dest=1)
    assert r.verified == "skipped" and "Z19" in r.note
    assert all(s is None for t in logic.tracks for s in t.sends.values()) and surface.state.view.kind == "pan"


def test_set_level_uses_flip_fader_with_volume_table_and_leaves_flip_off():       # 실측 S6
    cmds, surface, fake, logic = make()
    logic.tracks[0].sends[1] = Send("Bus 1")
    r = cmds.send.set_level(strip=1, number=None, send=1, db=-6.0)
    assert r.verified == "verified" and r.action == "send_set_level" and "fader" in r.note
    assert abs(logic.tracks[0].sends[1].level - -6.0) <= 0.1 and r.after["level_db"] == -6.0 and r.before["level_db"] == -math.inf
    assert surface.state.view.kind == "pan" and not surface.state.assignment.flip and not logic.flip
    assert cmds.send.set_level(strip=1, number=None, send=1, db=-6.0).note == "already"


def test_set_level_minus_inf_and_clamp():
    cmds, surface, fake, logic = make()
    logic.tracks[0].sends[2] = Send("Bus 1", -3.0)
    r = cmds.send.set_level(strip=1, number=None, send=2, db=float("-inf"))
    assert r.verified == "verified" and r.after["level_db"] == -math.inf and logic.tracks[0].sends[2].level <= -96
    r = cmds.send.set_level(strip=1, number=None, send=2, db=9.0)
    assert r.verified == "verified" and r.after["level_db"] == 6.0 and "clamped" in r.note
    assert cmds.send.set_level(strip=1, number=None, send=2, db=float("nan")).verified == "skipped"


def test_set_level_minus_inf_when_already_minus_inf_is_skipped():                 # 리뷰 M8
    cmds, surface, fake, logic = make()
    logic.tracks[0].sends[1] = Send("Bus 1")                                          # 새 센드 기본값 -∞(실측 S5)
    n0 = len(fake.sent)
    r = cmds.send.set_level(strip=1, number=None, send=1, db=float("-inf"))
    assert r.ok and r.verified == "skipped" and r.note == "already"
    assert not any(m[0] == 0x90 and m[1] == P.Note.FLIP for m in fake.sent[n0:])     # Flip을 켜지 않는다


def test_set_level_without_send_is_skipped():
    cmds, surface, fake, logic = make()
    r = cmds.send.set_level(strip=1, number=None, send=1, db=-6.0)
    assert r.verified == "skipped" and "set_dest" in r.note and surface.state.view.kind == "pan"


def test_set_level_mode_error_still_leaves_flip_off():                              # Review Focus 3
    cmds, surface, fake, logic = make()
    logic.tracks[0].sends[1] = Send("Bus 1")
    logic.drop_all_faders = True
    logic.drop_all_vpots = True
    r = cmds.send.set_level(strip=1, number=None, send=1, db=-6.0)
    assert r.verified == "unverified"
    assert not surface.state.assignment.flip and not logic.flip and surface.state.view.kind == "pan"


def test_set_level_mode_error_raised_inside_try_still_leaves_flip_off_and_pan():  # 리뷰 M1: 예외 경로
    cmds, surface, fake, logic = make()
    logic.tracks[0].sends[1] = Send("Bus 1")
    logic.drop_all_flips = True                                                       # flip(True)가 ModeError
    r = cmds.send.set_level(strip=1, number=None, send=1, db=-6.0)
    assert not r.ok and r.verified == "unverified" and "flip" in r.note
    assert not surface.state.assignment.flip and not logic.flip and surface.state.view.kind == "pan" and logic.view == "pan"
    assert logic.tracks[0].sends[1].level == -math.inf and logic.tracks[0].volume is None   # 볼륨도 센드도 안 바뀜


def test_set_pos_and_mute():                                                         # 실측 S8·S9
    cmds, surface, fake, logic = make()
    logic.tracks[0].sends[1] = Send("Bus 1")                                          # Post Pan, active
    r = cmds.send.set_pos(strip=1, number=None, send=1, pos="pre")
    assert r.verified == "verified" and r.action == "send_set_pos" and logic.tracks[0].sends[1].pos == 0 and r.after["pos"] == "pre"
    r = cmds.send.set_pos(strip=1, number=None, send=1, pos="post")
    assert r.verified == "verified" and logic.tracks[0].sends[1].pos == 1
    assert cmds.send.set_pos(strip=1, number=None, send=1, pos="post").note == "already"
    assert cmds.send.set_pos(strip=1, number=None, send=1, pos="sideways").verified == "skipped"
    r = cmds.send.mute(strip=1, number=None, send=1, on=True)
    assert r.verified == "verified" and r.action == "send_mute" and logic.tracks[0].sends[1].muted
    assert r.after["muted"] is True and r.after["dest"] == "Bus 1" and r.after["text"][0] == "*Bus 1"
    assert cmds.send.mute(strip=1, number=None, send=1, on=True).note == "already"
    r = cmds.send.mute(strip=1, number=None, send=1, on=False)
    assert r.verified == "verified" and not logic.tracks[0].sends[1].muted
    assert cmds.send.set_pos(strip=1, number=None, send=2, pos="pre").verified == "skipped"
    assert cmds.send.mute(strip=1, number=None, send=2, on=True).verified == "skipped"
    assert surface.state.view.kind == "pan"
