"""EQ·플러그인 명령. Commands(스펙 1)의 주소 해석·결과 형식·락을 빌려 쓰고 ModeDriver로 뷰를 오간다.
모든 공개 메서드는 ToolResult를 돌려주고 finally에서 leave_safely()로 PAN·Flip off로 돌아간다."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .modes import ModeError
from .setter import probe_mapping, set_enum, set_numeric
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
EQ_MAPPING = {"freq": Mapping("log", 20.0, 20000.0), "gain": Mapping("linear", -24.0, 24.0)}
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


def _value_dict(band: int, param: str, v: Value) -> dict:
    return {"band": band, "param": param, "value": v.number, "text": v.text}


class EqCommands:
    def __init__(self, base: "Commands") -> None:
        self.b = base
        self.d = base.modes

    def _goto_page(self, band: int) -> None:
        page = (band + 1) // 2
        want = EQ_SHORT[2 * page - 1][0]
        self.d.page_to(page)
        if self.d.view.columns[0][0].strip() != want:
            found = (self.d.page_until(lambda v: v.columns[0][0].strip() == want, forward=True, max_steps=4)
                     or self.d.page_until(lambda v: v.columns[0][0].strip() == want, forward=False, max_steps=4))
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
            try:
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
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
            finally:
                d.leave_safely()

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
            if param == "slope" and str(int(value)) not in SLOPES:
                return b._result(action, False, "skipped", t0, note=f"slope는 {SLOPES} 중 하나")
            ch = b._resolve(strip, number, action, t0)
            if not isinstance(ch, int):
                return ch
            target = b._target(ch)
            inserted = False
            try:
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
                    want = "On" if (value is True or str(value).lower() in ("on", "true", "1")) else "Off"
                    out = set_enum(d, col, want)
                elif param == "slope":
                    out = set_enum(d, col, str(int(value)))
                elif param == "q":
                    d.flip(True)
                    mapping, _lo, _hi = probe_mapping(d, col)             # Q 범위는 밴드마다 달라 프로빙(실측)
                    out = set_numeric(d, col, float(value), mapping, tolerance_for(float(value), None))
                else:
                    unit = "Hz" if param == "freq" else "dB"
                    out = set_numeric(d, col, float(value), EQ_MAPPING[param], tolerance_for(float(value), unit))
                after = _value_dict(band, param, out.value)
                note = ("Channel EQ 삽입됨. " if inserted else "") + out.note
                if out.ok and out.note == "already" and not inserted:
                    return b._result(action, True, "skipped", t0, target=target, before=before, after=after, note="already")
                return b._result(action, out.ok, "verified" if out.ok else "unverified", t0, target=target,
                                 before=before, after=after, note=note.strip())
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target,
                                 note=("Channel EQ 삽입됨. " if inserted else "") + str(e))
            finally:
                d.leave_safely()


class PluginCommands:
    def __init__(self, base: "Commands") -> None:
        self.b = base
        self.d = base.modes
