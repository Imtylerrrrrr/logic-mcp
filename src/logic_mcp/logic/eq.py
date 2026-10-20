"""EQ 명령. Commands(스펙 1)의 주소 해석·결과 형식·락을 빌려 쓰고 ModeDriver로 뷰를 오간다.
모든 공개 메서드는 ToolResult를 돌려주고 finally에서 leave_safely()로 PAN·Flip off로 돌아간다."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .modes import ModeError
from .setter import set_enum, set_numeric
from .values import Mapping, Value, parse_value, tolerance_for

if TYPE_CHECKING:
    from .commands import Commands, ToolResult

EQ_SHORT: dict[int, tuple[str, str, str, str]] = {   # 밴드 → (freq, gain|slope, q, on) 축약명. 1~6 실측, 7·8 라이브 체크로 확인
    1: ("LoCutF", "LoCutS", "LoCutQ", "LCO/Of"), 2: ("LoShF", "LoShGa", "LoShQ", "LSO/Of"),
    3: ("Peak1F", "Pea1Ga", "Peak1Q", "Pe1On/"), 4: ("Peak2F", "Pea2Ga", "Peak2Q", "Pe2On/"),
    5: ("Peak3F", "Pea3Ga", "Peak3Q", "Pe3On/"), 6: ("Peak4F", "Pea4Ga", "Peak4Q", "Pe4On/"),
    7: ("HiShF", "HiShGa", "HiShQ", "HSO/Of"), 8: ("HiCutF", "HiCutS", "HiCutQ", "HCO/Of"),
}
EQ_PARAM_COL = {"freq": 0, "gain": 1, "slope": 1, "q": 2, "on": 3}
# Q는 실측 T: Flip 페이더 raw에 ln Q가 선형(0.10~100). 밴드 1·8(컷)은 미측정이라 같은 범위로 가정(실측 V)
EQ_MAPPING = {"freq": Mapping("log", 20.0, 20000.0), "gain": Mapping("linear", -24.0, 24.0),
              "q": Mapping("log", 0.10, 100.0)}
SLOPES = ("6", "12", "18", "24", "36", "48")
SLOPE_BANDS = (1, 8)


def _band_dict(columns, band: int) -> dict:
    off = 0 if band % 2 == 1 else 4
    cols = columns[off:off + 4]
    vals = [parse_value(c[1]) for c in cols]
    out = {"band": band, "freq": vals[0].number, "q": vals[2].number, "on": vals[3].text == "On",
           "text": [c[1].strip() for c in cols], "names": [c[0].strip() for c in cols]}
    if band in SLOPE_BANDS:
        out["slope"] = int(vals[1].number) if vals[1].number is not None else None
    else:
        out["gain"] = vals[1].number
    return out


def _eq_value_problem(param: str, value) -> str | None:
    """EQ 값 검증. 문제가 있으면 이유를, 없으면 None."""
    if param == "on":
        return None if value in (0, 1) else "on은 true/false 또는 0/1"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{param} 값이 숫자가 아님: {value!r}"
    if not math.isfinite(v):
        return f"{param} 값이 유한하지 않음: {value!r}"
    if param in ("freq", "q") and v <= 0:
        return f"{param}는 0보다 커야 함: {value!r}"
    if param == "slope" and (not v.is_integer() or str(int(v)) not in SLOPES):
        return f"slope는 {SLOPES} 중 하나(정수)"
    return None


def _value_dict(band: int, param: str, v: Value) -> dict:
    return {"band": band, "param": param, "value": v.number, "text": v.text}


class EqCommands:
    def __init__(self, base: "Commands") -> None:
        self.b = base
        self.d = base.modes

    def _eq_page_of(self) -> int | None:
        """EQ 채널 뷰 1행 첫 열 이름으로 현재 페이지(1~4)를 판정한다. 마지막 페이지를 기억해 열리므로(실측 Q) 힌트를 쓰지 않는다."""
        first = self.d.view.columns[0][0].strip()
        return next((p for p in range(1, 5) if EQ_SHORT[2 * p - 1][0] == first), None)

    def _goto_page(self, band: int) -> None:
        page = (band + 1) // 2
        want = EQ_SHORT[2 * page - 1][0]
        cur = self._eq_page_of()
        if cur is None:
            raise ModeError("page", f"{want} 열(밴드 {2 * page - 1})을 찾을 현재 페이지", self.d.view.columns[0][0].strip() or "빈 열")
        if cur == page:
            return
        found = self.d.page_until(lambda v: v.columns[0][0].strip() == want, forward=page > cur, max_steps=abs(page - cur))
        if not found:
            raise ModeError("page", f"{want} 열(밴드 {2 * page - 1})", self.d.view.columns[0][0].strip() or "빈 열")

    def _has_eq(self, ch: int) -> bool:
        """E1(EQ Mixer view)에서 해당 스트립 2행이 비어 있으면 Channel EQ 없음. 삽입을 일으키지 않는다."""
        self.d.enter("eq_mixer")
        return self.d.read_column(ch)[1].kind != "none"

    def get(self, strip: int | None, number: int | None) -> "ToolResult":
        b, d, action = self.b, self.d, "eq_get"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = b._resolve(strip, number, action, t0)
            if not isinstance(ch, int):
                return ch
            target = b._target(ch)

            def body() -> "ToolResult":
                if not b.strips.follows(d, b.surface.state, ch):           # 출력·Master: E1 뷰의 유무만(실측 Z4)
                    d.focus(ch)
                    return b._result(action, True, "verified", t0, target=target,
                                     after={"has_eq": self._has_eq(ch), "bands": {}},
                                     note="출력·Master 스트립: EQ 채널 뷰가 따라가지 않아 밴드 값은 읽지 않음(실측 Z4)")
                d.focus(ch)
                if not self._has_eq(ch):
                    return b._result(action, True, "verified", t0, target=target, after={"has_eq": False, "bands": {}})
                d.enter("eq_channel")
                bands: dict[str, dict] = {}
                for band in (1, 3, 5, 7):
                    self._goto_page(band)
                    bands[str(band)] = _band_dict(d.view.columns, band)
                    bands[str(band + 1)] = _band_dict(d.view.columns, band + 1)
                return b._result(action, True, "verified", t0, target=target, after={"has_eq": True, "bands": bands})
            return b._guarded(action, t0, target, body)

    def set(self, strip: int | None, number: int | None, band: int, param: str, value,
            allow_insert: bool = True) -> "ToolResult":
        b, d, action = self.b, self.d, "eq_set"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            if not 1 <= band <= 8:
                return b._result(action, False, "skipped", t0, note="band는 1-8")
            if param not in EQ_PARAM_COL:
                return b._result(action, False, "skipped", t0, note=f"param은 {list(EQ_PARAM_COL)} 중 하나")
            if (band in SLOPE_BANDS) != (param == "slope") and param in ("gain", "slope"):
                return b._result(action, False, "skipped", t0,
                                 note=f"밴드 {band}는 {'slope' if band in SLOPE_BANDS else 'gain'}만 받음")
            if (why := _eq_value_problem(param, value)) is not None:
                return b._result(action, False, "skipped", t0, note=why)
            ch = b._resolve(strip, number, action, t0)
            if not isinstance(ch, int):
                return ch
            target = b._target(ch)
            inserted = False

            def body() -> "ToolResult":
                nonlocal inserted
                b.strips.ensure(d, b.surface.state, ch)
                d.focus(ch)
                if not self._has_eq(ch):
                    if not allow_insert:
                        return b._result(action, False, "skipped", t0, target=target,
                                         note="Channel EQ 없음. allow_insert=true면 삽입하고 설정")
                    inserted = True
                d.enter("eq_channel")                                    # 없던 트랙이면 여기서 삽입됨(실측)
                self._goto_page(band)
                col = (0 if band % 2 == 1 else 4) + EQ_PARAM_COL[param]
                before = _value_dict(band, param, d.read_column(col)[1])
                if param == "on":
                    want = "On" if value == 1 else "Off"
                    out = set_enum(d, col, want)
                elif param == "slope":
                    out = set_enum(d, col, str(int(value)))
                else:
                    unit = {"freq": "Hz", "gain": "dB"}.get(param)          # q는 단위 없음(실측 T 매핑, 프로빙 안 함)
                    out = set_numeric(d, col, float(value), EQ_MAPPING[param], tolerance_for(float(value), unit))
                after = _value_dict(band, param, out.value)
                note = ("Channel EQ 삽입됨. " if inserted else "") + out.note
                if out.ok and out.note == "already" and not inserted:
                    return b._result(action, True, "skipped", t0, target=target, before=before, after=after, note="already")
                return b._result(action, out.ok, "verified" if out.ok else "unverified", t0, target=target,
                                 before=before, after=after, note=note.strip())

            def body_noting_insert() -> "ToolResult":                  # ModeError 에도 삽입 여부를 알린다
                try:
                    return body()
                except ModeError as e:
                    if not inserted:
                        raise
                    return b._result(action, False, "unverified", t0, target=target, note="Channel EQ 삽입됨. " + str(e))
            return b._guarded(action, t0, target, body_noting_insert)
