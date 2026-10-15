"""스트립 종류 판별. 출력(Stereo Out)·Master 채널 스트립은 PL·SE·EQ 채널 뷰가 따라가지 않아(실측 Z4) 그 스트립을 대상으로
한 명령이 직전 실제 트랙을 바꾼다. TRACK 모드 홀드 메뉴 Output 열이 빈칸인 스트립을 미지원으로 본다(실측 Z5).
(번호, 이름)별로 캐시해 뱅크당 한 번만 읽는다(번호가 밀리거나 이름이 바뀌면 자연히 다시 읽는다)."""
from __future__ import annotations

from ..mcu import state as S
from .modes import ModeDriver


class StripUnsupported(Exception):
    def __init__(self, ch: int, number: int | None, name: str) -> None:
        self.note = (f"스트립 {ch + 1}(번호 {number}, {name!r})은 출력·Master 채널 스트립이라 채널 뷰(PL·SE·EQ)가 "
                     "따라가지 않음(실측 Z4). 지원하지 않음")
        super().__init__(self.note)


class StripKinds:
    def __init__(self) -> None:
        self.cache: dict[tuple[int | None, str], bool] = {}     # (번호, 이름) → 채널 뷰가 따라가는가

    def follows(self, d: ModeDriver, state: S.SurfaceState, ch: int) -> bool:
        s = state.strips[ch]
        if not s.name and s.number is None:
            return True                                           # 빈 스트립: 판별할 것이 없다
        key = (s.number, s.name)
        if key not in self.cache:
            outs = d.read_strip_outputs()                         # TRACK 모드 Output 열 8개, 끝나면 PAN
            for i, st in enumerate(d.surface.state.strips):
                if st.name or st.number is not None:
                    self.cache[(st.number, st.name)] = bool(outs[i])
        return self.cache.get(key, True)

    def ensure(self, d: ModeDriver, state: S.SurfaceState, ch: int) -> None:
        if not self.follows(d, state, ch):
            s = state.strips[ch]
            raise StripUnsupported(ch, s.number, s.name)
