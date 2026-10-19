"""EQ·플러그인 명령. Commands(스펙 1)의 주소 해석·결과 형식·락을 빌려 쓰고 ModeDriver로 뷰를 오간다.
모든 공개 메서드는 ToolResult를 돌려주고 finally에서 leave_safely()로 PAN·Flip off로 돌아간다."""
from __future__ import annotations

import math
import re
from datetime import datetime
from typing import TYPE_CHECKING

from .modes import CONFIRM_S, EDIT_OPEN_S, ModeError
from .plugins.cache import PluginCache
from .plugins.scan import rewind_to_empty, scan_list
from .plugins.match import find, normalize, strip_suffix
from .strips import StripUnsupported
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
            try:
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
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
            except ValueError as e:
                return b._result(action, False, "skipped", t0, target=target, note=f"값 오류: {e}")
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
            if (why := _eq_value_problem(param, value)) is not None:
                return b._result(action, False, "skipped", t0, note=why)
            ch = b._resolve(strip, number, action, t0)
            if not isinstance(ch, int):
                return ch
            target = b._target(ch)
            inserted = False
            try:
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
            except StripUnsupported as e:
                return b._result(action, False, "skipped", t0, target=target, note=e.note)
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target,
                                 note=("Channel EQ 삽입됨. " if inserted else "") + str(e))
            except ValueError as e:
                return b._result(action, False, "skipped", t0, target=target, note=f"값 오류: {e}")
            finally:
                d.leave_safely()


MAX_SLOT = 8            # 2a는 Plug-in Channel 뷰(PL)의 슬롯 1~8만(실측 C: 9~15 접근 경로 미확인)
MAX_OPTIONS = 16        # 열거형 선택지 수집 상한(캘리브레이션)
EMPTY_TEXTS = ("", "--")  # PL·Mixer 2행에서 빈 슬롯(`--` 또는 갱신 전 공백, 실측 C·H)
EMPTY_SHORTS = ("", "-")  # 편집 뷰 빈 파라미터 칸(공백 또는 1행 `-`, 실기 10차: Adaptive Limiter·Overdrive·Distortion)
_HEADER_RE = re.compile(r'Ins\.(\d+) "([^"]*)("?)')
_PAGE_TAIL_RE = re.compile(r"\s*Page\s*\d+/\d+.*$")


def _header_name(row1: str) -> tuple[int | None, str, bool]:
    """NAME 모드 1행 → (인서트 번호, 이름, 닫는 따옴표까지 보였는지). 56자 잘림으로 따옴표·`(s/s)`·Page가
    빠지거나 이름이 잘릴 수 있다(실측 G·L)."""
    m = _HEADER_RE.search(row1)
    if not m:
        return None, "", False
    text = _PAGE_TAIL_RE.sub("", m.group(2))
    return int(m.group(1)), strip_suffix(text).rstrip(" ("), m.group(3) == '"'


class SlotEmpty(Exception):
    pass


class ParamNotFound(Exception):
    def __init__(self, note: str) -> None:
        super().__init__(note)
        self.note = note


def _map_from(d: dict | None) -> Mapping | None:
    if not d:
        return None
    return Mapping(d["type"], d.get("lo", 0.0), d.get("hi", 1.0), tuple(d.get("options", ())))


def _map_to(m: Mapping) -> dict:
    out: dict = {"type": m.type}
    if m.type in ("log", "linear"):
        out.update(lo=m.lo, hi=m.hi)
    if m.type == "enum":
        out["options"] = list(m.options)
    return out


class PluginCommands:
    def __init__(self, base: "Commands", cache: PluginCache | None = None) -> None:
        self.b = base
        self.d = base.modes
        self.cache = cache or PluginCache.load()
        self.inventory: dict[str, dict[str, dict | None] | None] = {}

    # ---------- 공통 ----------
    def _fresh(self) -> None:
        """남은 미리 선택·Flip·NAME 모드를 지우고 PAN에서 시작한다."""
        if self.d.view.kind != "pan" or self.b.surface.state.assignment.flip:
            self.d.leave(keep_select=True)

    def _slot_text(self, slot: int) -> str:
        """PL 2행의 슬롯 열(축약). `--`·공백은 빈 슬롯."""
        return self.d.read_column(slot - 1)[1].text

    def _channel(self, ch: int) -> None:
        """대상 트랙을 선택하고 Plug-in Channel 뷰(PL)로 간다. 2행 = 선택 트랙의 슬롯 1~8, V-Pot n = 슬롯 n(실측 C·D).
        PL 안에서 SELECT 만 눌러 트랙을 바꾸면 2행이 그 트랙의 슬롯으로 바뀌지 않는다(실기 8차: 트랙 이름 조각이 읽힘, 실측 Z3)
        → 이미 PL 이고 다른 스트립이면 PAN 으로 나가 다시 들어간다. 출력·Master 스트립은 PL이 아예 따라가지 않으므로
        먼저 막는다(실측 Z4, 수정 8)."""
        self.b.strips.ensure(self.d, self.b.surface.state, ch)
        if self.d.view.kind != "pan" and not self.b.surface.state.strips[ch].select:
            self.d.leave(keep_select=True)
        self.d.focus(ch)
        self.d.enter("plugin_channel")

    def _complete(self, name: str) -> str:
        """잘렸을 수 있는 이름(오버레이 21칸·헤더 56칸)을 목록의 전체 이름으로 채운다. 못 채우면 그대로."""
        j, _c = find(self.cache.items, name)
        if j is not None and normalize(self.cache.items[j]).startswith(normalize(name)):
            return self.cache.items[j]
        return name

    def _open_edit(self, ch: int, slot: int) -> tuple[str, str, int]:
        """PL에서 틱 없이 슬롯 V-Pot을 눌러 값이 보존된 편집 뷰를 연다(실측 F(2)). NAME 모드로 두고
        (전체 이름, 축약, 페이지 수)를 돌려준다. 틱을 보내지 않으므로 미리 선택·교체가 생기지 않는다."""
        d = self.d
        self._channel(ch)
        abbrev = self._slot_text(slot)
        if abbrev in EMPTY_TEXTS:
            raise SlotEmpty(slot)
        if not d.press_vpot_until(slot - 1, lambda v: v.kind == "plugin_edit" and v.index == slot, EDIT_OPEN_S):
            raise ModeError("edit", f"plugin_edit 슬롯 {slot}", f"{d.view.kind} {d.view.index or ''}".strip())
        d.settle_smart()
        d.toggle_name_value()                           # NAME 모드: 1행 헤더(1페이지에 전체 이름), 2행 축약명
        row1 = self.b.surface.state.lcd[0]
        num, name, complete = _header_name(row1)
        if num != slot or not name:
            raise ModeError("header", f'Ins.{slot} "이름"', row1.strip()[:48] or "빈 헤더")
        key = abbrev.lstrip("*")
        full = name if complete else (self.cache.abbrev.get(key) or self._complete(name))
        self.cache.learn_abbrev(key, full)
        pages = d.probe_pages()
        return full, abbrev, pages

    def _read_pages(self, pages: int) -> list[dict]:
        """NAME 모드에서 시작. 페이지마다 축약명(NAME)과 값(VALUE)을 읽고 NAME 모드로 돌아온다."""
        d, items = self.d, []
        prev: list[tuple[str, str]] = []
        for page in range(1, pages + 1):
            d.page_to(page)
            shorts = [c[1].strip() for c in d.view.columns]
            d.toggle_name_value()
            cols = [c[1] for c in d.view.columns]
            values = [parse_value(t) for t in cols]
            d.toggle_name_value()
            pairs = [(sh, t.strip()) for sh, t in zip(shorts, cols)]
            skip = 0
            if page == pages and pages >= 2:     # 마지막 페이지는 오른쪽 정렬이라 앞 k열이 직전 페이지와 겹친다(실측 W)
                skip = next((k for k in range(7, 0, -1) if prev[8 - k:] == pairs[:k]), 0)
            for i, short in enumerate(shorts):
                if short not in EMPTY_SHORTS and i >= skip:
                    items.append({"index": (page - 1) * 8 + i + 1, "short": short, "value": values[i].number,
                                  "text": values[i].text})
            prev = pairs
        return items

    def _table(self, full: str, pages: int) -> dict:
        return self.cache.params.setdefault(full, {"pages": pages, "items": []})

    def _merge_items(self, full: str, pages: int, observed: list[dict]) -> None:
        table = self._table(full, pages)
        table["pages"] = pages
        seen = {ob["index"] for ob in observed}
        table["items"] = [it for it in table["items"] if it["index"] in seen]   # observed는 전체 읽기: 없는 항목(겹침 잔재)은 제거
        by_index = {it["index"]: it for it in table["items"]}
        for ob in observed:
            it = by_index.get(ob["index"])
            if it is None:
                it = {"index": ob["index"], "short": ob["short"], "name": None, "map": None}
                table["items"].append(it)
                by_index[ob["index"]] = it
            else:
                it["short"] = ob["short"]
        table["items"].sort(key=lambda x: x["index"])

    def _locate(self, full: str, pages: int, param) -> dict:
        """param(인덱스 또는 이름) → 표 항목 {"index","short","name","map"}. 표에 없으면 페이지를 읽어 채운다."""
        table = self._table(full, pages)
        if isinstance(param, int) or (isinstance(param, str) and param.strip().isdigit()):
            index = int(param)
            if not 1 <= index <= pages * 8:
                raise ParamNotFound(f"index {index}는 1-{pages * 8} 밖")
            it = next((x for x in table["items"] if x["index"] == index), None)
            if it is None:
                self._merge_items(full, pages, self._read_pages(pages))
                it = next((x for x in table["items"] if x["index"] == index), None)
            if it is None:
                raise ParamNotFound(f"index {index} 자리가 비어 있음")
            return it
        q = normalize(str(param))

        def hits(items: list[dict]) -> list[dict]:
            out = []
            for x in items:
                n, s = normalize(x.get("name") or ""), normalize(x["short"])
                if q and (n == q or s == q or (n and (n.startswith(q) or q.startswith(n))) or q.startswith(s) or s.startswith(q)):
                    out.append(x)
            return out
        found = hits(table["items"])
        if not found:
            self._merge_items(full, pages, self._read_pages(pages))
            found = hits(table["items"])
        exact = [x for x in found if normalize(x.get("name") or "") == q or normalize(x["short"]) == q]
        if len(exact) == 1:
            return exact[0]
        if len(found) == 1:
            return found[0]
        shorts = [x["short"] for x in table["items"]]
        if not found:
            raise ParamNotFound(f"{param!r}에 맞는 파라미터 없음. 축약명: {shorts}")
        raise ParamNotFound(f"{param!r}가 여럿에 맞음: {[x['short'] for x in found]}")

    def _goto_param(self, item: dict) -> int:
        """NAME 모드에서 해당 페이지로 가고 VALUE 모드로 바꾼 뒤 열 번호를 돌려준다."""
        page = (item["index"] - 1) // 8 + 1
        self.d.page_to(page)
        self.d.toggle_name_value()
        return (item["index"] - 1) % 8

    def _param_dict(self, full: str, slot: int, item: dict, v: Value) -> dict:
        return {"plugin": full, "slot": slot, "index": item["index"], "short": item["short"],
                "name": item.get("name"), "value": v.number, "text": v.text}

    # ---------- 명령 ----------
    def list(self, strip: int | None, number: int | None) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_list"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            only: int | None = None
            if strip is not None or number is not None:
                ch = b._resolve(strip, number, action, t0)
                if not isinstance(ch, int):
                    return ch
                only = ch
            try:
                self._fresh()
                targets = [only] if only is not None else [
                    ch for ch, s in enumerate(b.surface.state.strips) if s.number is not None]
                tracks: dict[str, dict[str, dict | None] | None] = {}
                unsupported: list[int] = []
                learned = False
                for ch in targets:
                    num = b.surface.state.strips[ch].number     # PL은 1행이 채널명이 아니라 PAN에서 읽은 번호를 쓴다
                    try:
                        self._channel(ch)
                    except StripUnsupported as e:
                        if only is not None:
                            return b._result(action, False, "skipped", t0, note=e.note)
                        tracks[str(num)] = None                 # 출력·Master: PL이 따라가지 않아 읽지 않는다(실측 Z4)
                        unsupported.append(num)
                        continue
                    d.settle_overlay()
                    texts = [d.view.columns[i][1].strip() for i in range(MAX_SLOT)]
                    row: dict[str, dict | None] = {}
                    revealed = False
                    for i, text in enumerate(texts):
                        if text in EMPTY_TEXTS:
                            row[str(i + 1)] = None
                            continue
                        name = self.cache.abbrev.get(text.lstrip("*"))
                        if name is None:
                            d.tick(i, -1)                       # ceil 모델: -1 = 현재 항목, +1은 다음 항목(실측 E)
                            shown = strip_suffix(d.read_overlay_text(i))
                            revealed = True
                            if shown and shown != "--":
                                name = self._complete(shown)
                                self.cache.learn_abbrev(text.lstrip("*"), name)
                                learned = True
                        row[str(i + 1)] = {"text": text, "name": name}
                    tracks[str(num)] = row
                    if revealed:
                        d.leave(keep_select=True)               # 드러낸 미리 선택은 누르지 않고 모드 전환으로 취소
                if learned:
                    self.cache.save()
                self.inventory.update(tracks)
                after = {"tracks": tracks} if only is not None else {"tracks": tracks, "unsupported": unsupported}
                return b._result(action, True, "verified", t0, after=after)
            except ModeError as e:
                return b._result(action, False, "unverified", t0, note=str(e))
            except ValueError as e:
                return b._result(action, False, "skipped", t0, note=f"값 오류: {e}")
            finally:
                d.leave_safely()

    def _begin(self, action: str, strip, number, slot, t0):
        if not 1 <= slot <= MAX_SLOT:
            return self.b._result(action, False, "skipped", t0,
                                  note=f"slot은 1-{MAX_SLOT}(Plug-in Channel 뷰에서 닿는 슬롯만 지원)")
        ch = self.b._resolve(strip, number, action, t0)
        return ch

    def params(self, strip: int | None, number: int | None, slot: int) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_params"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = self._begin(action, strip, number, slot, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "slot": slot}
            try:
                self._fresh()
                full, abbrev, pages = self._open_edit(ch, slot)
                observed = self._read_pages(pages)
                self._merge_items(full, pages, observed)
                self.cache.save()
                table = {x["index"]: x for x in self._table(full, pages)["items"]}
                out = [{"index": o["index"], "short": o["short"], "name": table[o["index"]].get("name"),
                        "value": o["value"], "text": o["text"]} for o in observed]
                return b._result(action, True, "verified", t0, target=target,
                                 after={"plugin": full, "abbrev": abbrev, "slot": slot, "pages": pages, "params": out})
            except SlotEmpty:
                return b._result(action, False, "skipped", t0, target=target, note=f"슬롯 {slot}이 비어 있음")
            except StripUnsupported as e:
                return b._result(action, False, "skipped", t0, target=target, note=e.note)
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
            except ValueError as e:
                return b._result(action, False, "skipped", t0, target=target, note=f"값 오류: {e}")
            finally:
                d.leave_safely()

    def get(self, strip: int | None, number: int | None, slot: int, param) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_get"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = self._begin(action, strip, number, slot, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "slot": slot}
            try:
                self._fresh()
                full, _abbrev, pages = self._open_edit(ch, slot)
                item = self._locate(full, pages, param)
                col = self._goto_param(item)
                v = d.read_column(col)[1]
                return b._result(action, True, "verified", t0, target=target, after=self._param_dict(full, slot, item, v))
            except SlotEmpty:
                return b._result(action, False, "skipped", t0, target=target, note=f"슬롯 {slot}이 비어 있음")
            except ParamNotFound as e:
                return b._result(action, False, "skipped", t0, target=target, note=e.note)
            except StripUnsupported as e:
                return b._result(action, False, "skipped", t0, target=target, note=e.note)
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
            except ValueError as e:
                return b._result(action, False, "skipped", t0, target=target, note=f"값 오류: {e}")
            finally:
                d.leave_safely()

    def set(self, strip: int | None, number: int | None, slot: int, param, value,
            tolerance: float | None = None) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_set"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = self._begin(action, strip, number, slot, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "slot": slot}
            try:
                self._fresh()
                full, _abbrev, pages = self._open_edit(ch, slot)
                item = self._locate(full, pages, param)
                col = self._goto_param(item)
                before_v = d.read_column(col)[1]
                before = self._param_dict(full, slot, item, before_v)
                numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
                if not numeric and isinstance(value, str):
                    try:
                        value, numeric = float(value), True
                    except ValueError:
                        numeric = False
                mapping = _map_from(item.get("map")) if numeric else None
                if numeric and ((mapping is not None and mapping.type == "enum")
                                or (mapping is None and before_v.kind != "number")):
                    numeric, value = False, str(int(value)) if float(value).is_integer() else str(value)   # 숫자 입력도 enum이면 선택지 경로(리뷰 I3·I4)
                if numeric:
                    if mapping is None:
                        d.flip(True)
                        st = b.surface.state.strips[col]
                        raw0 = st.fader_raw if st.fader_known else None
                        mapping, _lo, _hi = probe_mapping(d, col)          # 범위를 모르면 페이더 1·16383으로 프로빙
                        if mapping is None:                                # 프로빙으로 옮긴 값을 원래 위치로 되돌린다(리뷰 I4)
                            if raw0 is not None:
                                d.fader(col, raw0)
                                note = "프로빙 실패, 원래 위치로 복원"
                            else:
                                note = f"프로빙 실패, 복원 못함: 원래 값 {before_v.text}"
                            return b._result(action, False, "unverified", t0, target=target, before=before,
                                             after=self._param_dict(full, slot, item, d.read_value(col)), note=note)
                        item["map"] = _map_to(mapping)
                        self.cache.save()
                    tol = tolerance if tolerance is not None else tolerance_for(float(value), before_v.unit)
                    out = set_numeric(d, col, float(value), mapping, tol, b.faders)
                    if not out.ok:                                         # 틀린 map을 지워 다음에 다시 프로빙하게 한다(리뷰 m5)
                        item["map"] = None
                        self.cache.save()
                else:
                    want = ("On" if value else "Off") if isinstance(value, bool) else str(value)
                    out = set_enum(d, col, want)
                after = self._param_dict(full, slot, item, out.value)
                if out.ok and out.note == "already":
                    return b._result(action, True, "skipped", t0, target=target, before=before, after=after, note="already")
                return b._result(action, out.ok, "verified" if out.ok else "unverified", t0, target=target,
                                 before=before, after=after, note=out.note)
            except SlotEmpty:
                return b._result(action, False, "skipped", t0, target=target, note=f"슬롯 {slot}이 비어 있음")
            except ParamNotFound as e:
                return b._result(action, False, "skipped", t0, target=target, note=e.note)
            except StripUnsupported as e:
                return b._result(action, False, "skipped", t0, target=target, note=e.note)
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
            except ValueError as e:
                return b._result(action, False, "skipped", t0, target=target, note=f"값 오류: {e}")
            finally:
                d.leave_safely()

    def insert(self, strip: int | None, number: int | None, slot: int, plugin: str,
               replace: bool = False) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_insert"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            idx, cands = find(self.cache.items, plugin)
            if idx is None:
                note = (f"{plugin!r}가 여럿에 맞음: {cands}" if cands
                        else f"{plugin!r}가 목록({self.cache.source}, {len(self.cache.items)}개)에 없음. `logic_plugin scan` 뒤 다시 시도")
                return b._result(action, False, "skipped", t0, note=note)
            ch = self._begin(action, strip, number, slot, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "slot": slot}
            want = self.cache.items[idx]
            v = slot - 1
            try:
                self._fresh()
                self._channel(ch)
                current = self._slot_text(slot)
                occupied = current not in EMPTY_TEXTS
                if occupied and not replace:
                    return b._result(action, False, "skipped", t0, target=target,
                                     note=f"슬롯 {slot}에 {current!r}가 있음. 교체하려면 replace=true")
                rewind_to_empty(d, v)
                d.tick(v, 2 * idx)                                   # `--`(0)에서 2·i틱 = i번째 항목(ceil 모델)
                shown = strip_suffix(d.read_overlay_text(v))
                if normalize(shown) != normalize(want):              # 오버레이가 늦게 올 수 있어 0.3초 뒤 한 번 더 읽는다(실측 S)
                    d.pause(0.3)
                    shown = strip_suffix(d.read_overlay_text(v))
                for _ in range(3):                                   # 목록이 캐시와 조금 어긋나면 근처에서 찾는다
                    if normalize(shown) == normalize(want):
                        break
                    j, _c = find(self.cache.items, shown)
                    if j is None:
                        break
                    d.tick(v, 2 * (idx - j))
                    shown = strip_suffix(d.read_overlay_text(v))
                if normalize(shown) != normalize(want):              # 누르지 않는다: finally의 leave가 미리 선택을 취소
                    return b._result(action, False, "unverified", t0, target=target,
                                     note=f"목록 위치 {idx}에 {shown!r}가 보임(기대 {want!r}). 설치된 플러그인이 달라진 듯. `logic_plugin scan` 권장")
                if not d.press_vpot_until(v, lambda w: w.kind == "plugin_edit" and w.index == slot, CONFIRM_S):
                    return b._result(action, False, "unverified", t0, target=target,
                                     note=f"확정 뒤 {CONFIRM_S:.0f}초 안에 편집 뷰가 아니라 {d.view.kind}")
                d.settle_smart()
                d.toggle_name_value()
                num, name, _complete = _header_name(b.surface.state.lcd[0])
                d.toggle_name_value()
                if num != slot or not name or not normalize(want).startswith(normalize(name)):
                    return b._result(action, False, "unverified", t0, target=target,
                                     note=f"확정 뒤 편집 뷰 헤더가 Ins.{num} {name!r}(기대 Ins.{slot} {want!r})")
                d.enter("plugin_channel")
                abbrev = self._slot_text(slot)
                self.cache.learn_abbrev(abbrev.lstrip("*"), want)
                self.cache.save()
                return b._result(action, True, "verified", t0, target=target, before={"slot": slot, "text": current},
                                 after={"slot": slot, "plugin": want, "abbrev": abbrev,
                                        "replaced": current if occupied else None})
            except StripUnsupported as e:
                return b._result(action, False, "skipped", t0, target=target, note=e.note)
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
            except ValueError as e:
                return b._result(action, False, "skipped", t0, target=target, note=f"값 오류: {e}")
            finally:
                d.leave_safely()

    def remove(self, strip: int | None, number: int | None, slot: int) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_remove"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = self._begin(action, strip, number, slot, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "slot": slot}
            try:
                self._fresh()
                self._channel(ch)
                current = self._slot_text(slot)
                if current in EMPTY_TEXTS:
                    return b._result(action, True, "skipped", t0, target=target, note="already")
                rewind_to_empty(d, slot - 1)                         # 오버레이 `--` 확인까지
                if not d.press_vpot_until(slot - 1, lambda w: w.kind == "empty_edit" and w.index == slot, CONFIRM_S):
                    return b._result(action, False, "unverified", t0, target=target, before={"slot": slot, "text": current},
                                     note=f"`--` 확정 뒤 {CONFIRM_S:.0f}초 안에 빈 편집 뷰가 아니라 {d.view.kind}")
                d.enter("plugin_channel")
                after = self._slot_text(slot)
                ok = after in EMPTY_TEXTS
                return b._result(action, ok, "verified" if ok else "unverified", t0, target=target,
                                 before={"slot": slot, "text": current}, after={"slot": slot, "text": after},
                                 note="" if ok else "제거 뒤에도 슬롯에 이름이 보임")
            except StripUnsupported as e:
                return b._result(action, False, "skipped", t0, target=target, note=e.note)
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
            except ValueError as e:
                return b._result(action, False, "skipped", t0, target=target, note=f"값 오류: {e}")
            finally:
                d.leave_safely()

    def bypass(self, strip: int | None, number: int | None, slot: int, on: bool) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_bypass"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = self._begin(action, strip, number, slot, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "slot": slot}
            try:
                self._fresh()
                self._channel(ch)
                current = self._slot_text(slot)
                if current in EMPTY_TEXTS:
                    return b._result(action, False, "skipped", t0, target=target, note=f"슬롯 {slot}이 비어 있음")
                if current.startswith("*") == on:
                    return b._result(action, True, "skipped", t0, target=target, after={"slot": slot, "text": current}, note="already")
                d.shift_press_vpot(slot - 1)                         # PL에서 SHIFT+V-Pot = 바이패스 토글, 뷰 그대로(실측 N)
                if d.view.kind != "plugin_channel":
                    return b._result(action, False, "unverified", t0, target=target, before={"slot": slot, "text": current},
                                     note=f"SHIFT+V-Pot 뒤 뷰가 {d.view.kind}")
                after = self._slot_text(slot)
                ok = after.startswith("*") == on
                return b._result(action, ok, "verified" if ok else "unverified", t0, target=target,
                                 before={"slot": slot, "text": current}, after={"slot": slot, "text": after},
                                 note="" if ok else "SHIFT+V-Pot 뒤 `*` 표시가 기대와 다름")
            except StripUnsupported as e:
                return b._result(action, False, "skipped", t0, target=target, note=e.note)
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
            except ValueError as e:
                return b._result(action, False, "skipped", t0, target=target, note=f"값 오류: {e}")
            finally:
                d.leave_safely()

    def calibrate(self, strip: int | None, number: int | None, slot: int) -> "ToolResult":
        """편집 뷰에서 파라미터마다 전체 이름(틱 오버레이 1행), 숫자 매핑(Flip 페이더 프로빙), 열거형 선택지(-1로 처음까지 간 뒤
        +1로 끝까지, 정착 열 텍스트)를 모아 캐시에 저장한다. 값을 바꾸고 되돌리지 않는다 → scripts/calibrate_plugin.py가
        삽입한 임시 인스턴스에만 쓴다."""
        b, d, action = self.b, self.d, "plugin_calibrate"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = self._begin(action, strip, number, slot, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "slot": slot}
            try:
                self._fresh()
                full, _abbrev, pages = self._open_edit(ch, slot)
                self._merge_items(full, pages, self._read_pages(pages))
                table = self._table(full, pages)
                probed = enums = 0
                for item in table["items"]:
                    col = self._goto_param(item)                                   # VALUE 모드
                    v = d.read_column(col)[1]
                    settled = d.read_overlay_name(col)                             # 정착 1행 조각(오버레이가 없을 때 보이는 것)
                    name: str | None = None
                    # 이름은 LCD가 바뀐 틱(tick() True)의 오버레이에서만 받는다. 끝값 무변화 틱은 오버레이가 없을 수 있어
                    # 정착 1행 조각을 이름으로 읽게 된다(리뷰 I3).
                    if v.kind == "enum":
                        last = v.text
                        for _ in range(MAX_OPTIONS):                               # 처음(가장 앞 선택지)까지 -1
                            if d.tick(col, -1) and name is None:
                                name = d.read_overlay_name(col)
                            d.settle_overlay()
                            t = d.read_column(col)[1].text
                            if t == last:
                                break
                            last = t
                        options = [last]
                        for _ in range(MAX_OPTIONS - 1):                           # +1로 끝까지 모은다(처음에 있었으면 여기서 이름)
                            if d.tick(col, 1) and name is None:
                                name = d.read_overlay_name(col)
                            d.settle_overlay()
                            t = d.read_column(col)[1].text
                            if t == options[-1]:
                                break
                            options.append(t)
                        item["map"] = {"type": "enum", "options": options}
                        enums += 1
                    else:
                        if d.tick(col, 1):
                            name = d.read_overlay_name(col)
                            d.tick(col, -1)
                        elif d.tick(col, -1):                                      # 최댓값이면 반대 방향으로 한 틱
                            name = d.read_overlay_name(col)
                            d.tick(col, 1)
                        d.settle_overlay()
                        if v.kind == "number" and not item.get("map"):
                            d.flip(True)
                            mapping, _lo, _hi = probe_mapping(d, col)              # 페이더 1·16383 → 범위(실측 X: 에코 뒤 LCD까지 대기)
                            if mapping is not None:
                                item["map"] = _map_to(mapping)
                                probed += 1
                    if name and "Page" not in name and name != settled:
                        item["name"] = name
                    d.toggle_name_value()                                           # NAME 모드로 복귀(다음 page_to가 헤더를 읽는다)
                self.cache.save()
                return b._result(action, True, "verified", t0, target=target,
                                 after={"plugin": full, "pages": pages, "items": table["items"], "probed": probed, "enums": enums})
            except SlotEmpty:
                return b._result(action, False, "skipped", t0, target=target, note=f"슬롯 {slot}이 비어 있음")
            except StripUnsupported as e:
                return b._result(action, False, "skipped", t0, target=target, note=e.note)
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
            except ValueError as e:
                return b._result(action, False, "skipped", t0, target=target, note=f"값 오류: {e}")
            finally:
                d.leave_safely()

    def scan(self, force: bool = False) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_scan"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            if self.cache.user_list and not force:
                return b._result(action, True, "skipped", t0, after=self.cache.to_resource(),
                                 note=f"already: {self.cache.scanned_at}에 스캔한 {len(self.cache.user_list)}개. 다시 하려면 force=true")
            try:
                self._fresh()
                d.enter("plugin_mixer")                              # P1 Mixer: 스트립 ch의 V-Pot = 그 트랙의 슬롯 1
                slot = d.view.index or 1

                def empty_strips() -> list[int]:
                    return [ch for ch, s in enumerate(b.surface.state.strips)
                            if s.number is not None and d.view.columns[ch][1].strip() in EMPTY_TEXTS]
                found = empty_strips()
                if not found:
                    return b._result(action, False, "skipped", t0, note=f"스캔에 쓸 빈 슬롯 {slot}이 보이는 뱅크에 없음. 슬롯 {slot}이 빈 트랙을 뱅크에 띄우고 다시")
                ch = found[0]
                names = scan_list(d, ch)
                self.cache.user_list = names
                self.cache.scanned_at = datetime.now().isoformat(timespec="seconds")
                self.cache.save()
                d.leave(keep_select=True)                            # 미리 선택 취소(삽입 없음)
                d.enter("plugin_mixer")
                still_empty = ch in empty_strips()
                return b._result(action, still_empty, "verified" if still_empty else "unverified", t0,
                                 after={"count": len(names), "path": str(self.cache.path), "strip": ch + 1, "slot": slot},
                                 note="" if still_empty else "스캔 뒤 슬롯이 비어 있지 않음(확인 누름이 섞였을 수 있음)")
            except ModeError as e:
                return b._result(action, False, "unverified", t0, note=str(e))
            except ValueError as e:
                return b._result(action, False, "skipped", t0, note=f"값 오류: {e}")
            finally:
                d.leave_safely()
