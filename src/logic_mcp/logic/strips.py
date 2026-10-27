"""스트립 종류 판별. 출력(Stereo Out)·Master 채널 스트립은 PL·SE·EQ 채널 뷰가 따라가지 않아(실측 Z4) 그 스트립을 대상으로
한 명령이 직전 실제 트랙을 바꾼다. TRACK 모드 홀드 메뉴 Output 열이 빈칸인 스트립을 미지원으로 본다(실측 Z5).
트랙이 없는 Aux도 채널 뷰가 따라가지 않는다(실전 F2): Input 열이 `Bus…`인 스트립을 Aux로 본다(실측 Z19).
(번호, 이름)별로 캐시해 뱅크당 한 번만 읽는다(번호가 밀리거나 이름이 바뀌면 자연히 다시 읽는다)."""
from __future__ import annotations

from typing import Literal

from ..mcu import state as S
from .modes import ModeDriver

StripKind = Literal["track", "aux", "output"]


class StripUnsupported(Exception):
    def __init__(self, ch: int, number: int | None, name: str) -> None:
        self.note = (f"스트립 {ch + 1}(번호 {number}, {name!r})은 출력·Master 채널 스트립이라 채널 뷰(PL·SE·EQ)가 "
                     "따라가지 않음(실측 Z4). 지원하지 않음")
        super().__init__(self.note)


class StripAux(Exception):
    def __init__(self, ch: int, number: int | None, name: str) -> None:
        self.note = (f"스트립 {ch + 1}(번호 {number}, {name!r})은 Aux 채널 스트립이라 채널 뷰가 따라가지 않음(PL은 실측 Z19, SE·EQ는 가정). "
                     "플러그인은 슬롯 1 삽입·제거만 Plug-in Mixer 뷰로 지원")
        super().__init__(self.note)


class StripKinds:
    def __init__(self) -> None:
        self.cache: dict[tuple[int | None, str], StripKind] = {}     # (번호, 이름) → 스트립 종류

    def kind(self, d: ModeDriver, state: S.SurfaceState, ch: int) -> StripKind:
        s = state.strips[ch]
        if not s.name and s.number is None:
            return "track"                                        # 빈 스트립: 판별할 것이 없다
        key = (s.number, s.name)
        if s.number is not None and key in self.cache:
            return self.cache[key]
        kinds = d.read_strip_kinds()                              # TRACK 모드 Input·Output 열 8개, 끝나면 PAN. 실패하면 예외(캐시 없음)
        for i, st in enumerate(d.surface.state.strips):
            if st.number is not None:                             # 번호가 없으면 같은 이름끼리 충돌하므로 캐시하지 않는다(리뷰 M4)
                self.cache[(st.number, st.name)] = kinds[i]
        return kinds[ch]

    def follows(self, d: ModeDriver, state: S.SurfaceState, ch: int) -> bool:
        """출력·Master가 아닌가(Aux도 True, 스펙 4 이전 의미 유지). Aux 구분은 kind()로."""
        return self.kind(d, state, ch) != "output"

    def ensure(self, d: ModeDriver, state: S.SurfaceState, ch: int) -> StripKind:
        k = self.kind(d, state, ch)
        if k == "output":
            s = state.strips[ch]
            raise StripUnsupported(ch, s.number, s.name)
        return k
