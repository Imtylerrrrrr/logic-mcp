"""EQ·플러그인 명령. Commands(스펙 1)의 주소 해석·결과 형식·락을 빌려 쓰고 ModeDriver로 뷰를 오간다.
모든 공개 메서드는 ToolResult를 돌려주고 finally에서 leave_safely()로 PAN·Flip off로 돌아간다."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from .modes import ModeError
from .plugins.cache import PluginCache
from .plugins.scan import rewind_to_empty, scan_list
from .plugins.match import find, normalize, strip_suffix
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
        self.inventory: dict[str, dict[str, dict | None]] = {}

    # ---------- 공통 ----------
    def _fresh(self) -> None:
        """남은 미리 선택·Flip·NAME 모드를 지우고 PAN에서 시작한다."""
        if self.d.view.kind != "pan" or self.b.surface.state.assignment.flip:
            self.d.leave(keep_select=True)

    def _slot_text(self, ch: int) -> str:
        return self.d.read_column(ch)[1].text

    def _open_edit(self, ch: int, slot: int) -> tuple[str, str, int]:
        d = self.d
        d.enter("plugin_mixer")
        d.slot_to(slot)
        abbrev = self._slot_text(ch)
        if abbrev in ("", "--"):
            raise SlotEmpty(slot)
        d.tick(ch, 1)                                   # 반 항목: 현재 항목의 전체 이름이 오버레이로 뜬다(실측)
        full = strip_suffix(d.read_overlay_text(ch))
        d.press_vpot(ch)
        if d.view.kind != "plugin_edit":
            raise ModeError("edit", "plugin_edit", d.view.kind)
        d.settle_smart()
        if full and full != "--":
            self.cache.learn_abbrev(abbrev, full)
        d.toggle_name_value()                           # NAME 모드: 1행 헤더 `Page n/N`, 2행 축약명
        pages = d.view.page[1] if d.view.page else 1
        return full or abbrev, abbrev, pages

    def _read_pages(self, pages: int) -> list[dict]:
        """NAME 모드에서 시작. 페이지마다 축약명(NAME)과 값(VALUE)을 읽고 NAME 모드로 돌아온다."""
        d, items = self.d, []
        for page in range(1, pages + 1):
            d.page_to(page)
            shorts = [c[1].strip() for c in d.view.columns]
            d.toggle_name_value()
            values = [parse_value(c[1]) for c in d.view.columns]
            d.toggle_name_value()
            for i, short in enumerate(shorts):
                if short:
                    items.append({"index": (page - 1) * 8 + i + 1, "short": short, "value": values[i].number,
                                  "text": values[i].text})
        return items

    def _table(self, full: str, pages: int) -> dict:
        return self.cache.params.setdefault(full, {"pages": pages, "items": []})

    def _merge_items(self, full: str, pages: int, observed: list[dict]) -> None:
        table = self._table(full, pages)
        table["pages"] = pages
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
                d.enter("plugin_mixer")
                tracks: dict[str, dict[str, dict | None]] = {}
                for slot in range(1, 16):
                    d.slot_to(slot)
                    for ch, s in enumerate(b.surface.state.strips):
                        if s.number is None or (only is not None and ch != only):
                            continue
                        text = d.view.columns[ch][1].strip()
                        row = tracks.setdefault(str(s.number), {})
                        row[str(slot)] = None if text in ("", "--") else {"text": text, "name": self.cache.abbrev.get(text)}
                self.inventory.update(tracks)
                return b._result(action, True, "verified", t0, after={"tracks": tracks})
            except ModeError as e:
                return b._result(action, False, "unverified", t0, note=str(e))
            finally:
                d.leave_safely()

    def _begin(self, action: str, strip, number, slot, t0):
        if not 1 <= slot <= 15:
            return self.b._result(action, False, "skipped", t0, note="slot은 1-15")
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
                d.focus(ch)
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
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
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
                d.focus(ch)
                full, _abbrev, pages = self._open_edit(ch, slot)
                item = self._locate(full, pages, param)
                col = self._goto_param(item)
                v = d.read_column(col)[1]
                return b._result(action, True, "verified", t0, target=target, after=self._param_dict(full, slot, item, v))
            except SlotEmpty:
                return b._result(action, False, "skipped", t0, target=target, note=f"슬롯 {slot}이 비어 있음")
            except ParamNotFound as e:
                return b._result(action, False, "skipped", t0, target=target, note=e.note)
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
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
                d.focus(ch)
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
                if numeric:
                    mapping = _map_from(item.get("map"))
                    if mapping is None:
                        d.flip(True)
                        mapping, _lo, _hi = probe_mapping(d, col)          # 범위를 모르면 페이더 1·16383으로 프로빙
                        if mapping is not None:
                            item["map"] = _map_to(mapping)
                            self.cache.save()
                    tol = tolerance if tolerance is not None else tolerance_for(float(value), before_v.unit)
                    out = set_numeric(d, col, float(value), mapping, tol, b.faders)
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
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
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
            try:
                self._fresh()
                d.focus(ch)
                d.enter("plugin_mixer")
                d.slot_to(slot)
                current = self._slot_text(ch)
                occupied = current not in ("", "--")
                if occupied and not replace:
                    return b._result(action, False, "skipped", t0, target=target,
                                     note=f"슬롯 {slot}에 {current!r}가 있음. 교체하려면 replace=true")
                rewind_to_empty(d, ch)
                d.tick(ch, 2 * idx)
                shown = strip_suffix(d.read_overlay_text(ch))
                for _ in range(3):                                   # 목록이 캐시와 조금 어긋나면 근처에서 찾는다
                    if normalize(shown) == normalize(want):
                        break
                    j, _c = find(self.cache.items, shown)
                    if j is None:
                        break
                    d.tick(ch, 2 * (idx - j))
                    shown = strip_suffix(d.read_overlay_text(ch))
                if normalize(shown) != normalize(want):
                    return b._result(action, False, "unverified", t0, target=target,
                                     note=f"목록 위치 {idx}에 {shown!r}가 보임(기대 {want!r}). 설치된 플러그인이 달라진 듯. `logic_plugin scan` 권장")
                d.press_vpot(ch)
                if d.view.kind != "plugin_edit":
                    return b._result(action, False, "unverified", t0, target=target,
                                     note=f"확인 뒤 편집 뷰가 아니라 {d.view.kind}")
                d.settle_smart()
                d.enter("plugin_mixer")
                d.slot_to(slot)
                abbrev = self._slot_text(ch)
                self.cache.learn_abbrev(abbrev, want)
                self.cache.save()
                return b._result(action, True, "verified", t0, target=target, before={"slot": slot, "text": current},
                                 after={"slot": slot, "plugin": want, "abbrev": abbrev,
                                        "replaced": current if occupied else None})
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
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
                d.focus(ch)
                d.enter("plugin_mixer")
                d.slot_to(slot)
                current = self._slot_text(ch)
                if current in ("", "--"):
                    return b._result(action, True, "skipped", t0, target=target, note="already")
                rewind_to_empty(d, ch)
                d.press_vpot(ch)                                     # `--` 확정 = 제거(실측: 빈 편집 뷰 상태가 됨)
                d.enter("plugin_mixer")
                d.slot_to(slot)
                after = self._slot_text(ch)
                ok = after in ("", "--")
                return b._result(action, ok, "verified" if ok else "unverified", t0, target=target,
                                 before={"slot": slot, "text": current}, after={"slot": slot, "text": after},
                                 note="" if ok else "제거 뒤에도 슬롯에 이름이 보임")
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
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
                d.focus(ch)
                d.enter("plugin_mixer")
                d.slot_to(slot)
                current = self._slot_text(ch)
                if current in ("", "--"):
                    return b._result(action, False, "skipped", t0, target=target, note=f"슬롯 {slot}이 비어 있음")
                if current.startswith("*") == on:
                    return b._result(action, True, "skipped", t0, target=target, after={"slot": slot, "text": current}, note="already")
                d.shift_press_vpot(ch)
                after = self._slot_text(ch)
                ok = after.startswith("*") == on
                return b._result(action, ok, "verified" if ok else "unverified", t0, target=target,
                                 before={"slot": slot, "text": current}, after={"slot": slot, "text": after},
                                 note="" if ok else "SHIFT+V-Pot 뒤 `*` 표시가 기대와 다름")
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
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
                d.enter("plugin_mixer")
                found: tuple[int, int] | None = None
                for slot in range(1, 16):
                    d.slot_to(slot)
                    for ch, s in enumerate(b.surface.state.strips):
                        if s.number is not None and d.view.columns[ch][1].strip() == "--":
                            found = (ch, slot)
                            break
                    if found:
                        break
                if found is None:
                    return b._result(action, False, "skipped", t0, note="스캔에 쓸 빈 슬롯이 보이는 뱅크에 없음. 빈 슬롯이 있는 트랙을 뱅크에 띄우고 다시")
                ch, slot = found
                names = scan_list(d, ch)
                self.cache.user_list = names
                self.cache.scanned_at = datetime.now().isoformat(timespec="seconds")
                self.cache.save()
                d.leave(keep_select=True)                            # 미리 선택 취소(삽입 없음)
                d.enter("plugin_mixer")
                d.slot_to(slot)
                still_empty = d.view.columns[ch][1].strip() == "--"
                return b._result(action, still_empty, "verified" if still_empty else "unverified", t0,
                                 after={"count": len(names), "path": str(self.cache.path), "strip": ch + 1, "slot": slot},
                                 note="" if still_empty else "스캔 뒤 슬롯이 비어 있지 않음(확인 누름이 섞였을 수 있음)")
            except ModeError as e:
                return b._result(action, False, "unverified", t0, note=str(e))
            finally:
                d.leave_safely()
