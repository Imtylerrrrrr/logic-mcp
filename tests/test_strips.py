import pytest

from logic_mcp.logic.modes import ModeDriver, ModeError
from logic_mcp.logic.strips import StripKinds, StripUnsupported
from tests.fake_assign import Track, make_assign_logic


def test_strip_kinds_fills_cache_for_all_named_strips_once():
    surface, fake, logic = make_assign_logic([Track(1, "1"), Track(3, "StOu", kind="output"), Track(6, "Mast", kind="master")])
    d = ModeDriver(surface, sleep=logic.sleep)
    kinds = StripKinds()
    assert kinds.follows(d, surface.state, 0) is True
    assert kinds.cache == {(1, "1"): "track", (3, "StOu"): "output", (6, "Mast"): "output"}
    with pytest.raises(StripUnsupported) as e:
        kinds.ensure(d, surface.state, 1)
    assert "번호 3" in e.value.note and "출력" in e.value.note
    assert kinds.follows(d, surface.state, 5) is True          # 빈 스트립(번호·이름 없음)은 막지 않는다
    assert surface.state.view.kind == "pan" and logic.cs_param == 0


def test_strip_kinds_aux_is_cached_and_follows_is_true():               # 실측 Z19
    surface, fake, logic = make_assign_logic([Track(1, "1"), Track(5, "Aux1", kind="aux"), Track(3, "StOu", kind="output")])
    d = ModeDriver(surface, sleep=logic.sleep)
    kinds = StripKinds()
    assert kinds.kind(d, surface.state, 1) == "aux"
    assert kinds.follows(d, surface.state, 1) is True                   # follows는 출력·Master만 거른다(기존 의미 유지)
    assert kinds.cache == {(1, "1"): "track", (5, "Aux1"): "aux", (3, "StOu"): "output"}
    assert kinds.ensure(d, surface.state, 1) == "aux"
    assert surface.state.view.kind == "pan" and logic.cs_param == 0


def test_strip_kinds_does_not_cache_strips_without_number():          # 리뷰 M4: 번호 표시가 꺼지면 (None, 이름)이 충돌
    from types import SimpleNamespace

    from logic_mcp.mcu.state import Strip
    strips = (Strip(None, "Aud"), Strip(None, "Aud"), Strip(3, "StOu")) + tuple(Strip() for _ in range(5))
    calls: list[int] = []

    def read() -> list[str]:
        calls.append(1)
        return ["track", "output", "output"] + ["output"] * 5
    d = SimpleNamespace(read_strip_kinds=read, surface=SimpleNamespace(state=SimpleNamespace(strips=strips)))
    kinds = StripKinds()
    assert kinds.follows(d, d.surface.state, 0) is True and kinds.follows(d, d.surface.state, 1) is False
    assert kinds.cache == {(3, "StOu"): "output"} and len(calls) == 2    # 번호 없는 스트립은 매번 다시 읽는다
    assert kinds.follows(d, d.surface.state, 2) is False and len(calls) == 2


def test_strip_kinds_caches_nothing_when_read_fails():                # 리뷰 C1
    from logic_mcp.mcu import protocol as P
    surface, fake, logic = make_assign_logic([Track(1, "1"), Track(3, "StOu", kind="output")])
    logic.refuse = {P.Note.VPOT_PUSH + 4}
    d = ModeDriver(surface, sleep=logic.sleep)
    kinds = StripKinds()
    with pytest.raises(ModeError):
        kinds.ensure(d, surface.state, 1)
    assert kinds.cache == {} and surface.state.view.kind == "pan" and logic.cs_param == 0
