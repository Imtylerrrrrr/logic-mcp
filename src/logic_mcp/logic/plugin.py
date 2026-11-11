"""플러그인 명령. Commands(스펙 1)의 주소 해석·결과 형식·락을 빌려 쓰고 ModeDriver로 뷰를 오간다.
모든 공개 메서드는 ToolResult를 돌려주고 Commands._guarded가 leave_safely()로 PAN·Flip off로 되돌린다."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..mcu import protocol as P
from ..mcu import state as S
from .modes import CONFIRM_S, EDIT_OPEN_S, OVERLAY_WIDTH, ModeError
from .plugins.cache import PluginCache
from .plugins.scan import ITEM_TICKS, rewind_to_empty, seek_by_name
from .plugins.match import find, normalize, strip_suffix
from .strips import StripAux, StripUnsupported
from .setter import coerce, probe_mapping, set_numeric, set_option, verdict
from .values import Mapping, Value, parse_value, tolerance_for

if TYPE_CHECKING:
    from .commands import Commands, ToolResult

MAX_SLOT = 8            # 2a는 Plug-in Channel 뷰(PL)의 슬롯 1~8만(실측 C: 9~15 접근 경로 미확인)
VALUE_ROW_S = 1.0       # VALUE 전환 뒤 대상 열 2행이 축약명에서 값으로 바뀔 때까지(재수집: 토글 판정 뒤에도 축약명이 남음)
EMPTY_TEXTS = ("", "--")  # PL·Mixer 2행에서 빈 슬롯(`--` 또는 갱신 전 공백, 실측 C·H)
EMPTY_SHORTS = ("", "-")  # 편집 뷰 빈 파라미터 칸(공백 또는 1행 `-`, 실기 10차: Adaptive Limiter·Overdrive·Distortion)
_HEADER_RE = re.compile(r'Ins\.(\d+) "([^"]*)("?)')
_TRACK_RE = re.compile(r"\s*Track\s+(\d+)")
_PAGE_TAIL_RE = re.compile(r"\s*Page\s*\d+/\d+.*$")


def _header_name(row1: str) -> tuple[int | None, str, bool]:
    """NAME 모드 1행 → (인서트 번호, 이름, 닫는 따옴표까지 보였는지). 56자 잘림으로 따옴표·`(s/s)`·Page가
    빠지거나 이름이 잘릴 수 있다(실측 G·L)."""
    m = _HEADER_RE.search(row1)
    if not m:
        return None, "", False
    text = _PAGE_TAIL_RE.sub("", m.group(2))
    return int(m.group(1)), strip_suffix(text).rstrip(" ("), m.group(3) == '"'


def _header_track(row1: str) -> int | None:
    """NAME 모드 1행 맨 앞 `Track <n>`의 n(실측 G). 편집 뷰는 채널 뷰가 따라가는 트랙을 보여 준다(실전 F2)."""
    m = _TRACK_RE.match(row1)
    return int(m.group(1)) if m else None


def overlay_param_name(header: str, row: str, col: int) -> str:
    """편집 뷰 1행에서 파라미터 전체 이름만 떼어 낸다. header = 틱 전 1행(축약명), row = 틱 뒤 1행(오버레이를 덧쓴 상태).
    이름은 해당 열부터 2열(길면 3열) 폭으로만 덧쓰이고 나머지 칸은 축약명이 남는다(실기 10차). 창은 min(col*7, 56-21)부터
    3칸(7자 단위): 대상 열 앞 칸은 바뀌었을 때만, 대상 열 칸은 항상 넣고, 그 뒤 칸은 바뀌지 않은 첫 칸부터 버린다.
    이어 붙여 strip. 아무것도 안 바뀌면 ""."""
    w = S.COL_W
    first = min(col * w, P.LCD_WIDTH - OVERLAY_WIDTH) // w
    cells = [(c, row[c * w:(c + 1) * w], row[c * w:(c + 1) * w] != header[c * w:(c + 1) * w])
             for c in range(first, first + OVERLAY_WIDTH // w)]
    if not any(changed for _c, _t, changed in cells):
        return ""
    parts = []
    for c, text, changed in cells:
        if c > col and not changed:
            break
        if c >= col or changed:
            parts.append(text)
    return "".join(parts).strip()


class SlotEmpty(Exception):
    def __init__(self, slot: int) -> None:
        super().__init__(slot)
        self.slot = slot


class ParamNotFound(Exception):
    def __init__(self, note: str) -> None:
        super().__init__(note)
        self.note = note


def _map_from(d: dict | None) -> Mapping | None:
    if not d:
        return None
    if "type" not in d:                                   # 손으로 고친 캐시의 망가진 map은 없는 것으로(리뷰 A1)
        return None
    return Mapping(d["type"], d.get("lo", 0.0), d.get("hi", 1.0), tuple(d.get("options") or ()))


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
        from .plugin_mixer import AuxMixer               # 순환 import 회피: plugin_mixer가 이 모듈의 상수를 쓴다
        self.mixer = AuxMixer(self)                      # Aux 스트립 슬롯 1(Plug-in Mixer 뷰) 경로

    # ---------- 공통 ----------
    def _slot_text(self, slot: int) -> str:
        """PL 2행의 슬롯 열(축약). `--`·공백은 빈 슬롯."""
        return self.d.read_column(slot - 1)[1].text

    def _shown(self, v: int, want: str) -> str:
        """미리 선택 오버레이의 이름. 기대와 다르면 오버레이가 늦게 올 수 있어 0.3초 뒤 한 번 더 읽는다(실측 S)."""
        shown = strip_suffix(self.d.read_overlay_text(v))
        if normalize(shown) != normalize(want):
            self.d.pause(0.3)
            shown = strip_suffix(self.d.read_overlay_text(v))
        return shown

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
        expect = self.b.surface.state.strips[ch].number
        self.b._channel(ch, "plugin_channel")
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
        if (tn := _header_track(row1)) != expect:          # 분류와 무관한 가드: Input이 `Bus…`가 아닌 Aux 등(채널 뷰가 다른 트랙)
            raise ModeError("header", f"Track {expect}", f"Track {tn}")
        key = abbrev.lstrip("*")
        cached = self.cache.abbrev.get(key)                 # 잘린 헤더: 축약 캐시는 헤더 이름과 접두가 맞을 때만 믿는다(실전 F6 오학습)
        full = name if complete else (cached if cached and normalize(cached).startswith(normalize(name)) else self._complete(name))
        self.cache.learn_abbrev(key, full)
        pages = d.probe_pages()
        return full, abbrev, pages

    def _read_pages(self, pages: int) -> list[dict]:
        """NAME 모드에서 시작. 페이지마다 축약명(NAME)과 값(VALUE)을 읽고 NAME 모드로 돌아온다.
        옛 플러그인은 파라미터 하나가 두 열을 쓴다(실기 11/11 Silver Compressor: NAME `Thresho`|`ld`, VALUE `-20.0`|공백).
        축약명이 열을 꽉 채우고(7자, 구분 공백 없음) 다음 열에 축약명이 있는데 그 열 값이 비어 있으면 한 파라미터로 잇는다
        (축약명은 두 열을 이은 것, 인덱스는 앞 열, 뒤 열은 항목을 만들지 않는다)."""
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
            i = 0
            while i < len(shorts):
                short, width = shorts[i], 1
                if (len(short) == S.COL_W and i + 1 < len(shorts) and shorts[i + 1] not in EMPTY_SHORTS
                        and not cols[i + 1].strip()):
                    short, width = short + shorts[i + 1], 2
                if short not in EMPTY_SHORTS and i >= skip:
                    items.append({"index": (page - 1) * 8 + i + 1, "short": short, "value": values[i].number,
                                  "text": values[i].text})
                i += width
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
        col = (item["index"] - 1) % 8
        self.d.surface.wait_for(lambda s: s.lcd[1][col * S.COL_W:(col + 1) * S.COL_W].strip() != item["short"][:S.COL_W],
                                VALUE_ROW_S)                         # 시간 초과면 그대로 진행(값이 축약명과 같은 파라미터). 두 열 축약명은 앞 7자만 이 열에 보인다
        return col

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

            def body() -> "ToolResult":
                self.b._fresh()
                targets = [only] if only is not None else [
                    ch for ch, s in enumerate(b.surface.state.strips) if s.number is not None]
                tracks: dict[str, dict[str, dict | None] | None] = {}
                unsupported: list[int] = []
                aux: list[tuple[int, int | None]] = []
                learned = False
                for ch in targets:
                    num = b.surface.state.strips[ch].number     # PL은 1행이 채널명이 아니라 PAN에서 읽은 번호를 쓴다
                    try:
                        self.b._channel(ch, "plugin_channel")
                    except StripUnsupported as e:
                        if only is not None:
                            return b._result(action, False, "skipped", t0, note=e.note)
                        tracks[str(num)] = None                 # 출력·Master: PL이 따라가지 않아 읽지 않는다(실측 Z4)
                        unsupported.append(num)
                        continue
                    except StripAux:
                        tracks[str(num)] = None                 # Aux: PL이 직전 트랙 슬롯을 보여 준다(실전 F2) → 아래 Mixer 뷰 슬롯 1만
                        aux.append((ch, num))
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
                                if self.cache.learn_abbrev(text.lstrip("*"), name):
                                    learned = True
                                else:
                                    name = None                 # 축약과 안 맞는 이름 = 이웃 항목 오버레이(실기 10/27): 보고도 저장도 안 함
                        row[str(i + 1)] = {"text": text, "name": name}
                    tracks[str(num)] = row
                    if revealed:
                        d.leave(keep_select=True)               # 드러낸 미리 선택은 누르지 않고 모드 전환으로 취소
                aux_error = ""
                if aux:
                    try:
                        slot1 = self.mixer.slot1()
                    except ModeError as e:                      # 이미 읽은 트랙 행은 버리지 않는다: Aux 행만 null로 두고 unverified
                        aux_error = f"Aux 슬롯 1을 못 읽음: {e}"
                    else:
                        for ch, num in aux:                     # 축약 → 이름은 캐시로만(Aux에서는 미리 선택으로 드러내지 않는다)
                            text = slot1[ch]
                            row = {str(i): None for i in range(1, MAX_SLOT + 1)}
                            if text not in EMPTY_TEXTS:
                                row["1"] = {"text": text, "name": self.cache.abbrev.get(text.lstrip("*"))}
                            tracks[str(num)] = row
                if learned:
                    self.cache.save()
                self.inventory.update(tracks)
                after = {"tracks": tracks} if only is not None else {"tracks": tracks, "unsupported": unsupported}
                if only is None or aux:
                    after["aux"] = [num for _ch, num in aux]
                if aux_error:
                    return b._result(action, False, "unverified", t0, after=after, note=aux_error)
                return b._result(action, True, "verified", t0, after=after)
            return b._guarded(action, t0, None, body)

    def params(self, strip: int | None, number: int | None, slot: int) -> "ToolResult":
        b, action = self.b, "plugin_params"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = self.b._begin(action, strip, number, t0, slot, MAX_SLOT,
                               f"slot은 1-{MAX_SLOT}(Plug-in Channel 뷰에서 닿는 슬롯만 지원)")
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "slot": slot}

            def body() -> "ToolResult":
                self.b._fresh()
                full, abbrev, pages = self._open_edit(ch, slot)
                observed = self._read_pages(pages)
                self._merge_items(full, pages, observed)
                self.cache.save()
                table = {x["index"]: x for x in self._table(full, pages)["items"]}
                out = [{"index": o["index"], "short": o["short"], "name": table[o["index"]].get("name"),
                        "value": o["value"], "text": o["text"]} for o in observed]
                return b._result(action, True, "verified", t0, target=target,
                                 after={"plugin": full, "abbrev": abbrev, "slot": slot, "pages": pages, "params": out})
            return b._guarded(action, t0, target, body)

    def get(self, strip: int | None, number: int | None, slot: int, param) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_get"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = self.b._begin(action, strip, number, t0, slot, MAX_SLOT,
                               f"slot은 1-{MAX_SLOT}(Plug-in Channel 뷰에서 닿는 슬롯만 지원)")
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "slot": slot}

            def body() -> "ToolResult":
                self.b._fresh()
                full, _abbrev, pages = self._open_edit(ch, slot)
                item = self._locate(full, pages, param)
                col = self._goto_param(item)
                v = d.read_column(col)[1]
                return b._result(action, True, "verified", t0, target=target, after=self._param_dict(full, slot, item, v))
            return b._guarded(action, t0, target, body)

    def set(self, strip: int | None, number: int | None, slot: int, param, value,
            tolerance: float | None = None) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_set"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = self.b._begin(action, strip, number, t0, slot, MAX_SLOT,
                               f"slot은 1-{MAX_SLOT}(Plug-in Channel 뷰에서 닿는 슬롯만 지원)")
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "slot": slot}

            def body() -> "ToolResult":
                self.b._fresh()
                full, _abbrev, pages = self._open_edit(ch, slot)
                item = self._locate(full, pages, param)
                col = self._goto_param(item)
                before_v = d.read_column(col)[1]
                before = self._param_dict(full, slot, item, before_v)
                mapping = _map_from(item.get("map"))
                numeric, want = coerce(value, before_v, mapping)                # 숫자 입력도 enum이면 선택지 경로(리뷰 I3·I4)
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
                    tol = tolerance if tolerance is not None else tolerance_for(float(want), before_v.unit)
                    out = set_numeric(d, col, float(want), mapping, tol, b.faders)
                    if not out.ok:                                         # 틀린 map을 지워 다음에 다시 프로빙하게 한다(리뷰 m5)
                        item["map"] = None
                        self.cache.save()
                else:
                    emap = item.get("map") or {}
                    options = emap.get("options") if emap.get("type") == "enum" else None
                    out = set_option(d, col, str(want), options, before_v)
                ok, verified, note = verdict(out)
                if verified == "skipped" and not ok:                       # 틱 없이 거른 경우(skip:)는 after 없이
                    return b._result(action, False, "skipped", t0, target=target, before=before, note=note)
                return b._result(action, ok, verified, t0, target=target, before=before,
                                 after=self._param_dict(full, slot, item, out.value), note=note)
            return b._guarded(action, t0, target, body)

    def _insert_body(self, action: str, t0: int, target: dict, ch: int, slot: int, plugin: str,
                     replace: bool) -> "ToolResult":
        """insert·move 공통 본체(_guarded 안에서, _fresh 뒤). 캐시 위치로 가서 근처 보정 → 안 맞으면 이름 탐색(실전 F1),
        캐시에 없는 이름은 접두 이름 탐색. 확정 뒤 편집 뷰 헤더로 검증."""
        b, d = self.b, self.d
        expect = b.surface.state.strips[ch].number
        idx, cands = find(self.cache.items, plugin)
        if idx is None and cands:
            return b._result(action, False, "skipped", t0, target=target, note=f"{plugin!r}가 여럿에 맞음: {cands}")
        want = self.cache.items[idx] if idx is not None else plugin
        v = slot - 1
        if slot == 1 and b.strips.kind(d, b.surface.state, ch) == "aux":   # Aux 슬롯 2~8은 _channel이 StripAux
            return self.mixer.insert(action, t0, target, ch, want, prefix=idx is None)
        self.b._channel(ch, "plugin_channel")
        current = self._slot_text(slot)
        occupied = current not in EMPTY_TEXTS
        if occupied and not replace:
            return b._result(action, False, "skipped", t0, target=target,
                             note=f"슬롯 {slot}에 {current!r}가 있음. 교체하려면 replace=true")
        path_note = ""
        if idx is None:                                      # 캐시 목록에 없는 이름: 메뉴를 접두 일치로 훑는다(스펙 4 F1)
            found, ticks, last = seek_by_name(d, v, plugin, prefix=True)
            if not found:
                return b._result(action, False, "unverified", t0, target=target,
                                 note=f"{plugin!r}가 목록({self.cache.source}, {len(self.cache.items)}개)에 없어 "
                                      f"이름 탐색 {ticks}틱 했으나 못 찾음(마지막 {last!r}). `logic_plugin scan` 권장")
            want, path_note = last, f"name_scan:{ticks}"
        else:
            rewind_to_empty(d, v)
            d.tick(v, 2 * idx)                               # `--`(0)에서 2·i틱 = i번째 항목(ceil 모델)
            shown = first = self._shown(v, want)
            for _ in range(3):                               # 목록이 캐시와 조금 어긋나면 근처에서 찾는다
                if normalize(shown) == normalize(want):
                    break
                j, _c = find(self.cache.items, shown)
                d.tick(v, ITEM_TICKS if j is None else 2 * (idx - j))   # 모르는 이름 = 캐시 목록에 빠진 항목 → 실제 위치는 뒤(재수집)
                shown = self._shown(v, want)
            if normalize(shown) != normalize(want):          # 순서가 크게 다르면 이름으로 처음부터 훑는다(실전 F1)
                found, ticks, last = seek_by_name(d, v, want)
                if not found:                                # 누르지 않는다: finally의 leave가 미리 선택을 취소
                    return b._result(action, False, "unverified", t0, target=target,
                                     note=f"목록 위치 {idx}에 {first!r}가 보임(기대 {want!r}). 이름 탐색 {ticks}틱 뒤에도 "
                                          f"{want!r} 못 찾음(마지막 {last!r}). 설치 목록이 다른 듯. `logic_plugin scan` 권장")
                path_note = f"name_scan:{ticks}"
        if not d.press_vpot_until(v, lambda w: w.kind == "plugin_edit" and w.index == slot, CONFIRM_S):
            return b._result(action, False, "unverified", t0, target=target,
                             note=f"확정 뒤 {CONFIRM_S:.0f}초 안에 편집 뷰가 아니라 {d.view.kind}")
        d.settle_smart()
        d.toggle_name_value()
        row1 = b.surface.state.lcd[0]
        num, name, _complete = _header_name(row1)
        d.toggle_name_value()
        if (tn := _header_track(row1)) != expect:
            return b._result(action, False, "unverified", t0, target=target,
                             note=f"확정 뒤 편집 뷰 헤더가 Track {tn}(기대 Track {expect}): 플러그인이 트랙 {tn}에 들어갔을 수 있음. "
                                  "Logic에서 직접 확인할 것")
        n_want, n_name = normalize(want), normalize(name)
        if num != slot or not name or not (n_want.startswith(n_name) or n_name.startswith(n_want)):
            return b._result(action, False, "unverified", t0, target=target,
                             note=f"확정 뒤 편집 뷰 헤더가 Ins.{num} {name!r}(기대 Ins.{slot} {want!r})")
        if len(n_name) > len(n_want):                        # 목록 이름이 오버레이 21칸에서 잘린 경우(실기: EVOC 20 TrackOscillat) 헤더의 전체 이름
            want = name
        d.enter("plugin_channel")
        abbrev = self._slot_text(slot)
        self.cache.learn_abbrev(abbrev.lstrip("*"), want)
        self.cache.save()
        return b._result(action, True, "verified", t0, target=target, before={"slot": slot, "text": current},
                         after={"slot": slot, "plugin": want, "abbrev": abbrev,
                                "replaced": current if occupied else None}, note=path_note)

    def _remove_body(self, action: str, t0: int, target: dict, ch: int, slot: int) -> "ToolResult":
        """remove·move 공통 본체(_guarded 안에서, _fresh 뒤). `--`로 되감아 확정 → 빈 편집 뷰 → PL 2행 `--` 확인."""
        b, d = self.b, self.d
        if slot == 1 and b.strips.kind(d, b.surface.state, ch) == "aux":
            return self.mixer.remove(action, t0, target, ch)
        self.b._channel(ch, "plugin_channel")
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

    def insert(self, strip: int | None, number: int | None, slot: int, plugin: str,
               replace: bool = False) -> "ToolResult":
        b, action = self.b, "plugin_insert"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            idx, cands = find(self.cache.items, plugin)
            if idx is None and cands:                        # 보내기 전에 거른다(본체도 같은 검사)
                return b._result(action, False, "skipped", t0, note=f"{plugin!r}가 여럿에 맞음: {cands}")
            ch = self.b._begin(action, strip, number, t0, slot, MAX_SLOT,
                               f"slot은 1-{MAX_SLOT}(Plug-in Channel 뷰에서 닿는 슬롯만 지원)")
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "slot": slot}

            def body() -> "ToolResult":
                self.b._fresh()
                return self._insert_body(action, t0, target, ch, slot, plugin, replace)
            return b._guarded(action, t0, target, body)

    def remove(self, strip: int | None, number: int | None, slot: int) -> "ToolResult":
        b, action = self.b, "plugin_remove"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = self.b._begin(action, strip, number, t0, slot, MAX_SLOT,
                               f"slot은 1-{MAX_SLOT}(Plug-in Channel 뷰에서 닿는 슬롯만 지원)")
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "slot": slot}

            def body() -> "ToolResult":
                self.b._fresh()
                return self._remove_body(action, t0, target, ch, slot)
            return b._guarded(action, t0, target, body)

    def move(self, strip: int | None, number: int | None, slot: int, to_slot: int) -> "ToolResult":
        """슬롯 이동 = 제거 + 빈 목표 슬롯에 재삽입(MCU에 이동 명령이 없다, 스펙 4 F5). 설정값은 초기화된다.
        이름은 편집 뷰 헤더에서 읽는다(축약 캐시를 믿지 않는다, F6). 재삽입이 실패해도 되돌리지 않는다(되돌리기도 삽입)."""
        b, d, action = self.b, self.d, "plugin_move"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            if not 1 <= to_slot <= MAX_SLOT or to_slot == slot:
                return b._result(action, False, "skipped", t0,
                                 note=f"to_slot은 1-{MAX_SLOT}이고 slot({slot})과 달라야 함")
            ch = self.b._begin(action, strip, number, t0, slot, MAX_SLOT,
                               f"slot은 1-{MAX_SLOT}(Plug-in Channel 뷰에서 닿는 슬롯만 지원)")
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "slot": slot, "to_slot": to_slot}

            def body() -> "ToolResult":
                self.b._fresh()
                header, _abbrev, _pages = self._open_edit(ch, slot)  # Aux면 StripAux, 빈 슬롯이면 SlotEmpty → skipped
                d.toggle_name_value()                                # _open_edit가 켠 NAME 모드를 끈다(재삽입 헤더 확인이 토글로 쓴다)
                idx, cands = find(self.cache.items, header)          # 재삽입 이름은 목록 항목 하나로 확정될 때만(제거 전에)
                if idx is None:
                    return b._result(action, False, "skipped", t0, target=target,
                                     note=f"이름을 확정하지 못해 이동하지 않음: {header!r} (후보 {cands})")
                full = self.cache.items[idx]
                d.enter("plugin_channel")
                occupant = self._slot_text(to_slot)
                if occupant not in EMPTY_TEXTS:
                    return b._result(action, False, "skipped", t0, target=target,
                                     note=f"슬롯 {to_slot}에 {occupant!r}가 있음. move는 빈 슬롯으로만 옮김")
                removed = self._remove_body(action, t0, target, ch, slot)
                if removed.verified != "verified":
                    return b._result(action, False, removed.verified, t0, target=target, before=removed.before,
                                     after=removed.after, note=f"제거 단계: {removed.note}")
                moved = {"from": slot, "to": to_slot, "plugin": full, "note_path": "remove+insert"}
                try:
                    put = self._insert_body(action, t0, target, ch, to_slot, full, replace=False)
                except ModeError as e:                               # 제거는 끝났다: 이름을 잃지 않게 결과로 돌려준다
                    return b._result(action, False, "unverified", t0, target=target, before={"slot": slot, "plugin": full},
                                     after=moved, note=f"제거는 됐으나 재삽입 실패: {e} — {full!r}가 to_slot에 들어갔는지 확인한 뒤 수동으로 다시 넣을 것")
                if put.verified != "verified":
                    return b._result(action, False, "unverified", t0, target=target, before={"slot": slot, "plugin": full},
                                     after=moved, note=f"슬롯 {slot}의 {full!r} 제거는 됐으나 재삽입 실패(슬롯 {to_slot}): {put.note}. "
                                                       "직접 다시 넣어야 함")
                return b._result(action, True, "verified", t0, target=target, before={"slot": slot, "plugin": full},
                                 after=moved,
                                 note="설정값은 초기화됨(MCU에 이동 명령이 없어 제거+재삽입)")
            return b._guarded(action, t0, target, body)

    def bypass(self, strip: int | None, number: int | None, slot: int, on: bool) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_bypass"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = self.b._begin(action, strip, number, t0, slot, MAX_SLOT,
                               f"slot은 1-{MAX_SLOT}(Plug-in Channel 뷰에서 닿는 슬롯만 지원)")
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "slot": slot}

            def body() -> "ToolResult":
                self.b._fresh()
                self.b._channel(ch, "plugin_channel")
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
            return b._guarded(action, t0, target, body)

    def calibrate(self, strip: int | None, number: int | None, slot: int) -> "ToolResult":
        """plugins/calibrate.py의 calibrate로 위임(설명은 그쪽). import는 순환을 피해 여기서."""
        from .plugins import calibrate as cal
        return cal.calibrate(self, strip, number, slot)

    def scan(self, force: bool = False) -> "ToolResult":
        """plugins/calibrate.py의 scan으로 위임. import는 순환을 피해 여기서."""
        from .plugins import calibrate as cal
        return cal.scan(self, force)
