import pytest

from logic_mcp.logic.commands import Commands
from logic_mcp.logic.faders import FaderTable
from logic_mcp.mcu import protocol as P
from tests.fake_assign import make_assign_logic


def make():
    surface, fake, logic = make_assign_logic()
    cmds = Commands(surface, FaderTable.load(), sleep=logic.sleep, logic_running=lambda: True)
    return cmds, surface, fake, logic


def test_eq_get_without_eq_does_not_insert():
    cmds, surface, fake, logic = make()
    r = cmds.eq.get(strip=2, number=None)
    assert r.ok and r.verified == "verified" and r.after == {"has_eq": False, "bands": {}}
    assert logic.tracks[1].eq is None and surface.state.view.kind == "pan"
    assert r.target == {"strip": 2, "number": 16, "name": "DCl"}


def test_eq_get_reads_all_bands_and_leaves():
    cmds, surface, fake, logic = make()
    logic.tracks[0].insert(1, "Channel EQ")
    r = cmds.eq.get(strip=1, number=None)
    assert r.verified == "verified" and r.after["has_eq"]
    b = r.after["bands"]
    assert len(b) == 8
    assert b["1"]["freq"] == 20.0 and b["1"]["slope"] == 12 and b["1"]["on"] is False and b["1"]["q"] == 0.71
    assert b["2"]["gain"] == 0.0 and b["5"]["freq"] == 1040.0 and b["8"]["slope"] == 24
    assert b["3"]["text"] == ["100 Hz", "0.0 dB", "0.60", "On"]
    assert surface.state.view.kind == "pan" and logic.selected == 0


def test_eq_set_freq_inserts_when_allowed_and_verifies():
    cmds, surface, fake, logic = make()
    r = cmds.eq.set(strip=1, number=None, band=3, param="freq", value=1000.0)
    assert r.ok and r.verified == "verified" and "Channel EQ 삽입됨" in r.note
    assert abs(logic.tracks[0].eq[2][0].value - 1000.0) <= 10
    assert r.before["text"] == "100 Hz" and r.after["value"] == pytest.approx(1000.0, abs=10)
    assert surface.state.view.kind == "pan" and not surface.state.assignment.flip


def test_eq_set_refuses_insert_when_not_allowed():
    cmds, surface, fake, logic = make()
    r = cmds.eq.set(strip=1, number=None, band=3, param="gain", value=-3.0, allow_insert=False)
    assert r.verified == "skipped" and "allow_insert" in r.note
    assert logic.tracks[0].eq is None and surface.state.view.kind == "pan"


def test_eq_set_gain_slope_on_q():
    cmds, surface, fake, logic = make()
    logic.tracks[0].insert(1, "Channel EQ")
    eq = logic.tracks[0].eq
    assert cmds.eq.set(1, None, 2, "gain", -3.0).after["value"] == -3.0 and eq[1][1].value == -3.0
    r = cmds.eq.set(1, None, 1, "slope", 36)
    assert r.verified == "verified" and r.after["text"].startswith("36") and eq[0][1].value == 4
    r = cmds.eq.set(1, None, 1, "on", True)
    assert r.verified == "verified" and r.after["text"] == "On" and eq[0][3].value == 1
    assert cmds.eq.set(1, None, 1, "on", True).verified == "skipped"            # already
    r = cmds.eq.set(1, None, 4, "q", 2.0)
    assert r.ok and abs(eq[3][2].value - 2.0) <= 0.05
    assert surface.state.view.kind == "pan" and not surface.state.assignment.flip


def test_eq_set_by_number_other_strip():
    cmds, surface, fake, logic = make()
    r = cmds.eq.set(None, 19, 2, "gain", 2.0)
    assert r.ok and logic.tracks[4].eq[1][1].value == 2.0 and r.target["strip"] == 5
    assert logic.selected == 0                                                   # 선택 복원


def test_eq_set_validation_sends_nothing():
    cmds, surface, fake, logic = make()
    n = len(fake.sent)
    assert cmds.eq.set(1, None, 9, "freq", 100.0).verified == "skipped"
    assert cmds.eq.set(1, None, 1, "gain", 1.0).verified == "skipped"        # 밴드 1은 slope
    assert cmds.eq.set(1, None, 3, "slope", 12).verified == "skipped"
    assert cmds.eq.set(1, None, 1, "slope", 7).verified == "skipped"
    assert cmds.eq.set(1, None, 3, "hue", 1.0).verified == "skipped"
    assert len(fake.sent) == n


def test_eq_set_mode_error_still_leaves():            # Review Focus 4
    cmds, surface, fake, logic = make()
    logic.tracks[0].insert(1, "Channel EQ")
    logic.refuse.add(P.Note.CURSOR_RIGHT)
    r = cmds.eq.set(1, None, 5, "gain", -2.0)
    assert r.ok is False and r.verified == "unverified" and "page" in r.note
    assert surface.state.view.kind == "pan" and not surface.state.assignment.flip


def test_eq_set_band_from_remembered_last_page():             # 실측 Q: EQ 채널 뷰는 마지막 페이지(4)로 열린다
    cmds, surface, fake, logic = make()
    logic.tracks[0].insert(1, "Channel EQ")
    logic.tracks[0].eq_page = 4
    r = cmds.eq.set(strip=1, number=None, band=3, param="freq", value=1000.0)
    assert r.ok and r.verified == "verified", r.note
    assert abs(logic.tracks[0].eq[2][0].value - 1000.0) <= 10
    assert logic.tracks[0].eq_page == 2                       # 밴드 3은 2페이지, 가짜가 마지막 위치를 기억
    assert surface.state.view.kind == "pan"


@pytest.mark.parametrize("start", [1, 2, 3, 4])
def test_eq_get_reads_all_pages_from_any_start_page(start):
    cmds, surface, fake, logic = make()
    logic.tracks[0].insert(1, "Channel EQ")
    logic.tracks[0].eq_page = start
    r = cmds.eq.get(strip=1, number=None)
    assert r.verified == "verified" and len(r.after["bands"]) == 8, r.note
    b = r.after["bands"]
    assert b["1"]["freq"] == 20.0 and b["5"]["freq"] == 1040.0 and b["8"]["slope"] == 24


def test_eq_set_q_uses_log_mapping_without_probe(monkeypatch):
    """Q는 고정 log 0.10~100 매핑(실측 T): probe_mapping(Flip 페이더를 극값으로 보냄)을 부르지 않는다."""
    from logic_mcp.logic import eq as eq_mod, setter

    def boom(*a, **k):
        raise AssertionError("Q 설정에서 probe_mapping을 부름")
    monkeypatch.setattr(setter, "probe_mapping", boom)
    monkeypatch.setattr(eq_mod, "probe_mapping", boom, raising=False)   # eq가 나중에 직접 import해 부르는 회귀도 잡는다
    cmds, surface, fake, logic = make()
    logic.tracks[0].insert(1, "Channel EQ")
    eq = logic.tracks[0].eq
    r = cmds.eq.set(1, None, 4, "q", 2.0)
    assert r.ok and r.verified == "verified" and abs(eq[3][2].value - 2.0) <= 0.04


def test_eq_set_q_survives_dropped_first_fader():       # 실측 Z1
    cmds, surface, fake, logic = make()
    logic.tracks[0].insert(1, "Channel EQ")
    eq = logic.tracks[0].eq
    logic.drop_first_fader = True
    r = cmds.eq.set(1, None, 4, "q", 2.0)
    assert r.ok and r.verified == "verified" and abs(eq[3][2].value - 2.0) <= 0.04


def test_eq_set_with_dropped_flip_press_fails_without_touching_anything():   # 실측 Z2 → 리뷰 C1: 재누름 없음
    cmds, surface, fake, logic = make()
    logic.tracks[0].insert(1, "Channel EQ")
    eq = logic.tracks[0].eq
    logic.drop_first_flip = True
    r = cmds.eq.set(1, None, 4, "q", 2.0)
    assert not r.ok and r.verified == "unverified" and "flip" in r.note
    assert eq[3][2].value == 0.30 and [t.volume for t in logic.tracks] == [None] * len(logic.tracks)


@pytest.mark.parametrize("drop_first", [False, True])
def test_eq_set_late_flip_led_never_moves_a_track_volume(drop_first):    # 리뷰 C1: 재누름이 늦은 LED와 겹치면 Flip이 꺼진 채 페이더가 볼륨을 움직인다
    cmds, surface, fake, logic = make()
    logic.tracks[0].insert(1, "Channel EQ")
    logic.flip_led_lag = True
    logic.drop_first_flip = drop_first
    cmds.eq.set(1, None, 3, "gain", -3.0)           # ok 여부는 상관없다
    assert [t.volume for t in logic.tracks] == [None] * len(logic.tracks)


def test_mixer_volume_turns_flip_off_first():                  # 리뷰 I1
    cmds, surface, fake, logic = make()
    cmds.modes.flip(True)
    assert logic.flip
    r = cmds.mixer_volume(2, None, -6.0)
    assert r.ok and r.verified == "verified"
    assert not logic.flip and logic.tracks[1].volume == cmds.faders.db_to_raw(-6.0)


def test_mixer_volume_refuses_when_flip_cannot_be_turned_off():    # 리뷰 I1
    cmds, surface, fake, logic = make()
    cmds.modes.flip(True)
    logic.drop_all_flips = True
    eq_before = [t.volume for t in logic.tracks]
    r = cmds.mixer_volume(2, None, -6.0)
    assert not r.ok and r.verified == "unverified" and "Flip" in r.note
    assert [t.volume for t in logic.tracks] == eq_before == [None] * len(logic.tracks)


@pytest.mark.parametrize("band,param,value", [(3, "freq", 0), (3, "freq", float("inf")), (3, "q", -1),
                                              (3, "gain", float("nan")), (1, "slope", 12.7), (3, "on", 2)])
def test_eq_set_rejects_invalid_values_as_skipped(band, param, value):          # 리뷰 I3
    cmds, surface, fake, logic = make()
    r = cmds.eq.set(1, None, band, param, value)
    assert not r.ok and r.verified == "skipped" and r.note
    assert logic.tracks[0].eq is None and surface.state.view.kind == "pan"


def test_eq_set_on_accepts_one_and_bool():                                      # 리뷰 I3
    cmds, surface, fake, logic = make()
    logic.tracks[0].insert(1, "Channel EQ")
    eq = logic.tracks[0].eq
    assert eq[2][3].value == 1
    r = cmds.eq.set(1, None, 3, "on", 0.0)
    assert r.ok and eq[2][3].value == 0
    r = cmds.eq.set(1, None, 3, "on", 1)
    assert r.ok and eq[2][3].value == 1


def test_eq_get_on_output_strip_reports_has_eq_only_and_set_is_skipped():     # 실측 Z4
    from tests.fake_assign import Track
    surface, fake, logic = make_assign_logic([Track(1, "1"), Track(3, "StOu", kind="output")])
    cmds = Commands(surface, FaderTable.load(), sleep=logic.sleep, logic_running=lambda: True)
    r = cmds.eq.get(strip=2, number=None)
    assert r.verified == "verified" and r.after == {"has_eq": False, "bands": {}} and "출력" in r.note
    r = cmds.eq.set(strip=2, number=None, band=3, param="gain", value=-3.0)
    assert r.verified == "skipped" and "출력" in r.note
    assert logic.tracks[0].eq is None and logic.tracks[1].eq is None and surface.state.view.kind == "pan"


def test_eq_get_turns_strip_unsupported_into_skipped_result(monkeypatch):
    # 출력 스트립은 follows 검사에서 먼저 걸러져 eq.get 안에서 StripUnsupported 가 실제로 나올 길이 없다 → 예외를 주입해 변환만 고정
    from logic_mcp.logic.strips import StripUnsupported
    cmds, surface, fake, logic = make()
    err = StripUnsupported(0, 1, "StOu")

    def boom(ch):
        raise err
    monkeypatch.setattr(cmds.eq, "_has_eq", boom)
    r = cmds.eq.get(strip=1, number=None)
    assert r.ok is False and r.verified == "skipped" and err.note in r.note
    assert surface.state.view.kind == "pan"
