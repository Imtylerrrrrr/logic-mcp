import pytest

from logic_mcp.logic.modes import ModeDriver
from logic_mcp.logic.strips import StripKinds, StripUnsupported
from tests.fake_assign import Track, make_assign_logic


def test_strip_kinds_fills_cache_for_all_named_strips_once():
    surface, fake, logic = make_assign_logic([Track(1, "1"), Track(3, "StOu", kind="output"), Track(6, "Mast", kind="master")])
    d = ModeDriver(surface, sleep=logic.sleep)
    kinds = StripKinds()
    assert kinds.follows(d, surface.state, 0) is True
    assert kinds.cache == {(1, "1"): True, (3, "StOu"): False, (6, "Mast"): False}
    with pytest.raises(StripUnsupported) as e:
        kinds.ensure(d, surface.state, 1)
    assert "번호 3" in e.value.note and "출력" in e.value.note
    assert kinds.follows(d, surface.state, 5) is True          # 빈 스트립(번호·이름 없음)은 막지 않는다
    assert surface.state.view.kind == "pan" and logic.cs_param == 0
