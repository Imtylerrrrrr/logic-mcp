"""EQ 명령. Commands(스펙 1)의 주소 해석·결과 형식·락을 빌려 쓰고 ModeDriver로 뷰를 오간다.
모든 공개 메서드는 ToolResult를 돌려주고 Commands._guarded가 leave_safely()로 PAN·Flip off로 되돌린다."""
from __future__ import annotations

import math
from collections.abc import Callable
from typing import TYPE_CHECKING

from .modes import ModeError
from .setter import batch_verdict, run_changes, set_enum, set_numeric, verdict
from .strips import StripAux
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


def _change_problem(band: int, param: str, value) -> str | None:
    """set 입력 검사(band 1-8, param 이름, gain/slope 밴드 규칙, 값 형식). 문제가 있으면 이유를, 없으면 None."""
    if not 1 <= band <= 8:
        return "band는 1-8"
    if param not in EQ_PARAM_COL:
        return f"param은 {list(EQ_PARAM_COL)} 중 하나"
    if (band in SLOPE_BANDS) != (param == "slope") and param in ("gain", "slope"):
        return f"밴드 {band}는 {'slope' if band in SLOPE_BANDS else 'gain'}만 받음"
    return _eq_value_problem(param, value)


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
                kind = b.strips.kind(d, b.surface.state, ch)
                if kind == "aux":                                         # EQ 채널 뷰 진입이 직전 트랙에 Channel EQ를 넣을 수 있다(가정, 미측정)
                    s = b.surface.state.strips[ch]
                    raise StripAux(ch, s.number, s.name)
                if kind == "output":                                      # 출력·Master: E1 뷰의 유무만(실측 Z4)
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

    def _set_one(self, band: int, param: str, value) -> dict:
        """밴드 값 하나를 맞춘다(EQ 채널 뷰 안). set·set_many 공통. ok·verified·note·before·after를 돌려준다."""
        d = self.d
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
        ok, verified, note = verdict(out)
        return {"ok": ok, "verified": verified, "note": note, "before": before,
                "after": _value_dict(band, param, out.value)}

    def _in_channel(self, action: str, t0: int, ch: int, target: dict, allow_insert: bool,
                    work: Callable[[bool], "ToolResult"]) -> "ToolResult":
        """스트립 ch의 EQ 채널 뷰 안에서 work(inserted)를 돌린다(Aux 거절·Channel EQ 확인·삽입 허용 검사 포함). set·set_many 공통."""
        b, d = self.b, self.d
        inserted = False

        def body() -> "ToolResult":
            nonlocal inserted
            if b.strips.ensure(d, b.surface.state, ch) == "aux":     # EQ 채널 뷰가 Aux를 따라가지 않는다고 가정(미측정): 직전 트랙을 바꾸지 않게
                s = b.surface.state.strips[ch]
                raise StripAux(ch, s.number, s.name)
            d.focus(ch)
            if not self._has_eq(ch):
                if not allow_insert:
                    return b._result(action, False, "skipped", t0, target=target,
                                     note="Channel EQ 없음. allow_insert=true면 삽입하고 설정")
                inserted = True
            d.enter("eq_channel")                                    # 없던 트랙이면 여기서 삽입됨(실측)
            return work(inserted)

        def body_noting_insert() -> "ToolResult":                  # ModeError 에도 삽입 여부를 알린다
            try:
                return body()
            except ModeError as e:
                if not inserted:
                    raise
                return b._result(action, False, "unverified", t0, target=target, note="Channel EQ 삽입됨. " + str(e))
        return b._guarded(action, t0, target, body_noting_insert)

    def set(self, strip: int | None, number: int | None, band: int, param: str, value,
            allow_insert: bool = True) -> "ToolResult":
        b, action = self.b, "eq_set"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            if (why := _change_problem(band, param, value)) is not None:
                return b._result(action, False, "skipped", t0, note=why)
            ch = b._resolve(strip, number, action, t0)
            if not isinstance(ch, int):
                return ch
            target = b._target(ch)

            def work(inserted: bool) -> "ToolResult":
                r = self._set_one(band, param, value)
                verified, note = r["verified"], r["note"]
                if inserted:                                             # 삽입이 일어났으면 already여도 skipped가 아니다
                    verified, note = ("verified" if r["ok"] else "unverified"), "Channel EQ 삽입됨. " + note
                return b._result(action, r["ok"], verified, t0, target=target, before=r["before"], after=r["after"],
                                 note=note.strip())
            return self._in_channel(action, t0, ch, target, allow_insert, work)

    def set_many(self, strip: int | None, number: int | None, changes: list[dict],
                 allow_insert: bool = True) -> "ToolResult":
        """같은 트랙 Channel EQ의 값 여러 개를 EQ 뷰 한 번 진입으로 맞춘다. 받은 순서대로, 첫 실패에서 멈춘다(앞 값은 되돌리지 않음).
        보내기 전에 전부 검사하고, 하나라도 틀리면 아무것도 보내지 않는다."""
        b, action = self.b, "eq_set"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            seen: set[tuple[int, str]] = set()
            for k, c in enumerate(changes, 1):
                why = _change_problem(c["band"], c["param"], c["value"])
                if why is None and (c["band"], c["param"]) in seen:
                    why = f"밴드 {c['band']} {c['param']}가 두 번 나옴"
                if why is not None:
                    return b._result(action, False, "skipped", t0, note=f"changes {k}번째: {why}")
                seen.add((c["band"], c["param"]))
            ch = b._resolve(strip, number, action, t0)
            if not isinstance(ch, int):
                return ch
            target = b._target(ch)

            def work(inserted: bool) -> "ToolResult":
                d = self.d
                heads = [{"band": c["band"], "param": c["param"]} for c in changes]

                def between() -> None:                              # 직전 값 오버레이(≈2초)가 이웃 열을 덮으므로 만기까지 기다린다
                    d.settle_overlay()
                    d.flip(False)

                def one(k: int) -> dict:
                    c = changes[k]
                    r = self._set_one(c["band"], c["param"], c["value"])
                    return {**r, **{x: {"value": r[x]["value"], "text": r[x]["text"]} for x in ("before", "after")}}
                results = run_changes(heads, one, between)
                ok, verified, note = batch_verdict(len(changes), results, lambda r: f"밴드 {r['band']} {r['param']}")
                if inserted:
                    verified, note = ("verified" if ok else "unverified"), "Channel EQ 삽입됨. " + note
                done = sum(1 for r in results if r["ok"])
                return b._result(action, ok, verified, t0, target=target, note=note,
                                 after={"results": results, "done": done, "remaining": changes[len(results):]})
            return self._in_channel(action, t0, ch, target, allow_insert, work)
