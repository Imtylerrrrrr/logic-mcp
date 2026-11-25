"""플러그인 명령. Commands(스펙 1)의 주소 해석·결과 형식·락을 빌려 쓰고 ModeDriver로 뷰를 오간다.
모든 공개 메서드는 ToolResult를 돌려주고 Commands._guarded가 leave_safely()로 PAN·Flip off로 되돌린다."""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ..mcu import state as S
from .modes import CONFIRM_S, CURSOR_LATE_S, EDIT_OPEN_S, OVERLAY_WIDTH, ModeError, overlay_start
from .plugin_mixer import AuxMixer
from .plugins import calibrate as cal
from .plugins.cache import PluginCache, _map_from, _map_to
from .plugins.lcd import EMPTY_SHORTS, EMPTY_TEXTS, MAX_SLOT, _header_name, _header_track, pair_columns
from .plugins.scan import ITEM_TICKS, rewind_to_empty, seek_by_name
from .plugins.match import find, normalize, strip_suffix
from .strips import StripAux, StripUnsupported
from .setter import batch_verdict, coerce, probe_mapping, run_changes, set_numeric, set_option, verdict
from .values import Value, parse_value, tolerance_for

if TYPE_CHECKING:
    from .commands import Commands, ToolResult

VALUE_ROW_S = 1.0       # VALUE 전환 뒤 대상 열 2행이 축약명에서 값으로 바뀔 때까지(재수집: 토글 판정 뒤에도 축약명이 남음)


class SlotEmpty(Exception):
    def __init__(self, slot: int) -> None:
        super().__init__(slot)
        self.slot = slot


class ParamNotFound(Exception):
    def __init__(self, note: str) -> None:
        super().__init__(note)
        self.note = note


class PluginCommands:
    def __init__(self, base: "Commands", cache: PluginCache | None = None) -> None:
        self.b = base
        self.d = base.modes
        self.cache = cache or PluginCache.load()
        self.inventory: dict[str, dict[str, dict | None] | None] = {}
        self.mixer = AuxMixer(self)                      # Aux 스트립 슬롯 1(Plug-in Mixer 뷰) 경로

    # ---------- 공통 ----------
    def _on_slot(self, action: str, strip: int | None, number: int | None, slot: int,
                 body: Callable[[int, int, dict], "ToolResult"], *,
                 check: Callable[[int], "ToolResult | None"] | None = None, **extra) -> "ToolResult":
        """슬롯 하나를 상대하는 명령의 공통 순서: Commands._on_strip에 슬롯 범위 검사(check 뒤)와 PAN에서 시작(_fresh)을 더한다."""
        b = self.b

        def checks(t0: int) -> "ToolResult | None":
            if check is not None and (r := check(t0)) is not None:
                return r
            if not 1 <= slot <= MAX_SLOT:
                return b._result(action, False, "skipped", t0,
                                 note=f"slot은 1-{MAX_SLOT}(Plug-in Channel 뷰에서 닿는 슬롯만 지원)")
            return None

        def run(ch: int, t0: int, target: dict) -> "ToolResult":
            b._fresh()
            return body(ch, t0, target)
        return b._on_strip(action, strip, number, run, check=checks, extra={"slot": slot, **extra})

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
        opened = lambda v: v.kind == "plugin_edit" and v.index == slot
        ok = d.press_vpot_until(slot - 1, lambda v: opened(v) or (v.kind == "empty_edit" and v.index == slot), EDIT_OPEN_S)
        if ok and d.view.kind == "empty_edit":
            # 차 있는 슬롯인데 빈 화면: Logic이 직전 플러그인의 페이지 위치로 열어 마지막 페이지 너머를 보인다(VALUE는 1행 전부 `-`,
            # 2행 공백 — 빈 슬롯과 같은 화면). Cursor ◀ 한 번이면 마지막 페이지로 온다(실기 2026-11-21 Compressor 3페이지 뒤 Chorus).
            d.cursor(False)
            ok = d.wait_view(opened, EDIT_OPEN_S) or d.wait_view(opened, CURSOR_LATE_S)
        if not ok:
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
        known = self.cache.params.get(full)                # 표가 있으면 페이지 수를 안다: 1페이지면 누르지 않고, 여러 페이지인데 무반응이면 실패
        pages = d.probe_pages(known["pages"] if known and known.get("items") else None)
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
            d.toggle_name_value()
            pairs = [(sh, t.strip()) for sh, t in zip(shorts, cols)]
            skip = 0
            if page == pages and pages >= 2:     # 마지막 페이지는 오른쪽 정렬이라 앞 k열이 직전 페이지와 겹친다(실측 W)
                skip = next((k for k in range(7, 0, -1) if prev[8 - k:] == pairs[:k]), 0)
            for i, short, text in pair_columns(shorts, cols):
                if short not in EMPTY_SHORTS and i >= skip:
                    v = parse_value(text)
                    items.append({"index": (page - 1) * 8 + i + 1, "short": short, "value": v.number, "text": v.text})
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

    def _goto_param(self, item: dict, items: list[dict]) -> int:
        """NAME 모드에서 해당 페이지로 가고 VALUE 모드로 바꾼 뒤 열 번호를 돌려준다. items(표 항목)로 그 페이지의
        페이지 확인 가드를 d.guard에 걸고 한 번 확인한다(get도 덮음, 틀리면 ModeError)."""
        page = (item["index"] - 1) // 8 + 1
        self.d.page_to(page)
        self.d.toggle_name_value()
        col = (item["index"] - 1) % 8
        self.d.surface.wait_for(lambda s: s.lcd[1][col * S.COL_W:(col + 1) * S.COL_W].strip() != item["short"][:S.COL_W],
                                VALUE_ROW_S)                         # 시간 초과면 그대로 진행(값이 축약명과 같은 파라미터). 두 열 축약명은 앞 7자만 이 열에 보인다
        self.d.guard = self._page_guard(items, page, col)
        self.d.guard()
        return col

    def _page_guard(self, items: list[dict], page: int, col: int):
        """LCD가 page를 보일 때만 col을 읽고 쓰게 하는 확인(늦은 커서 누름이 페이지를 몰래 옮김, 실전 2026-11-19·실측 Z16·Z17).
        VALUE 모드 1행 = 그 페이지 7자 축약명(실측 `CirTyp Thrs   Ratio  Attack Rel    AutRel` + 토큰). 7자보다 긴 축약명은 다음 열로 넘친다.
        가려질 수 있는 열은 비교하지 않는다: 대상 열 오버레이 3칸(내 마지막 쓰기의 긴 이름이 ≈2초 남음), 토큰이 보이면 7·8열(≈2초).
        토큰이 보이면 그 번호가 page여야 한다. 기대 이름이 있는 열만 비교하고, 불일치 없음 + 근거(비교한 열 또는 맞는 토큰) 하나 이상이면 통과.
        근거가 없으면(작은 페이지가 오버레이에 다 가림) 대상 열에 제 축약명이 보이면 통과, 아니면 오버레이가 걷힌 뒤 모든 열로 다시.
        실패면 늦은 누름이 맞는 페이지를 가져올 수 있어 CURSOR_LATE_S까지 기다린 뒤 ModeError("guard")."""
        d, w = self.d, S.COL_W
        want = [""] * 8
        for it in items:
            if (it["index"] - 1) // 8 + 1 == page:
                c = (it["index"] - 1) % 8
                want[c] = it["short"][:w].strip()               # LCD 쪽도 strip해서 비교: 칸 경계의 공백(`Lo Cut `|`Freq`)
                if len(it["short"]) > w and c < 7:
                    want[c + 1] = it["short"][w:2 * w].strip()
        first = overlay_start(col) // w
        overlay = set(range(first, first + OVERLAY_WIDTH // w))

        def check(full: bool) -> bool | None:
            st = d.surface.state
            token = st.view.page
            if token and token[0] != page:
                return False
            skip = (set() if full else overlay) | ({6, 7} if token else set())
            compared = [c for c in range(8) if want[c] and c not in skip]
            if any(st.lcd[0][c * w:(c + 1) * w].strip() != want[c] for c in compared):
                return False
            return True if compared or token else None

        def guard() -> None:
            full = False
            ok = check(full)
            if ok is None:
                if d.surface.state.lcd[0][col * w:(col + 1) * w].strip() == want[col]:
                    return
                d.settle_overlay()
                full = True
                ok = check(full)
            if ok or d.wait_view(lambda _v: bool(check(full)), CURSOR_LATE_S):
                return
            raise ModeError("guard", f"{page}페이지 축약명 {want}", d.surface.state.lcd[0].rstrip() or "빈 1행")
        return guard

    def _param_dict(self, full: str, slot: int, item: dict, v: Value) -> dict:
        return {"plugin": full, "slot": slot, "index": item["index"], "short": item["short"],
                "name": item.get("name"), "value": v.number, "text": v.text}

    # ---------- 명령 ----------
    def list(self, strip: int | None, number: int | None) -> "ToolResult":
        b, action = self.b, "plugin_list"
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
                    tracks[str(num)], new = self._slot_row()
                    learned = learned or new
                aux_error = ""
                if aux:
                    try:
                        tracks.update(self._aux_rows(aux))
                    except ModeError as e:                      # 이미 읽은 트랙 행은 버리지 않는다: Aux 행만 null로 두고 unverified
                        aux_error = f"Aux 슬롯 1을 못 읽음: {e}"
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

    def _slot_row(self) -> tuple[dict[str, dict | None], bool]:
        """PL 뷰(대상 트랙으로 들어온 뒤) 2행 → 슬롯별 {"text","name"} 또는 None, 그리고 새 축약을 배웠는지.
        캐시에 없는 축약은 -1틱 오버레이로 이름을 드러내 배우고, 드러냈으면 모드 전환으로 미리 선택을 취소한다."""
        d = self.d
        learned = False
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
        if revealed:
            d.leave(keep_select=True)               # 드러낸 미리 선택은 누르지 않고 모드 전환으로 취소
        return row, learned

    def _aux_rows(self, aux: list[tuple[int, int | None]]) -> dict[str, dict]:
        """Aux 스트립들의 슬롯 1(Plug-in Mixer 뷰) → 번호별 행. 축약 → 이름은 캐시로만. 못 읽으면 ModeError."""
        slot1 = self.mixer.slot1()
        rows: dict[str, dict] = {}
        for ch, num in aux:                     # 축약 → 이름은 캐시로만(Aux에서는 미리 선택으로 드러내지 않는다)
            text = slot1[ch]
            row = {str(i): None for i in range(1, MAX_SLOT + 1)}
            if text not in EMPTY_TEXTS:
                row["1"] = {"text": text, "name": self.cache.abbrev.get(text.lstrip("*"))}
            rows[str(num)] = row
        return rows

    def params(self, strip: int | None, number: int | None, slot: int) -> "ToolResult":
        b, action = self.b, "plugin_params"

        def body(ch: int, t0: int, target: dict) -> "ToolResult":
            full, abbrev, pages = self._open_edit(ch, slot)
            observed = self._read_pages(pages)
            self._merge_items(full, pages, observed)
            self.cache.save()
            table = {x["index"]: x for x in self._table(full, pages)["items"]}
            out = [{"index": o["index"], "short": o["short"], "name": table[o["index"]].get("name"),
                    "value": o["value"], "text": o["text"]} for o in observed]
            return b._result(action, True, "verified", t0, target=target,
                             after={"plugin": full, "abbrev": abbrev, "slot": slot, "pages": pages, "params": out})
        return self._on_slot(action, strip, number, slot, body)

    def get(self, strip: int | None, number: int | None, slot: int, param) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_get"

        def body(ch: int, t0: int, target: dict) -> "ToolResult":
            full, _abbrev, pages = self._open_edit(ch, slot)
            item = self._locate(full, pages, param)
            col = self._goto_param(item, self._table(full, pages)["items"])
            v = d.read_column(col)[1]
            return b._result(action, True, "verified", t0, target=target, after=self._param_dict(full, slot, item, v))
        return self._on_slot(action, strip, number, slot, body)

    def _set_one(self, full: str, slot: int, item: dict, items: list[dict], value, tolerance: float | None) -> dict:
        """항목 하나를 맞춘다(편집 뷰 안, NAME 모드에서 시작). set·set_many 공통. ok·verified·note·before·after를 돌려준다."""
        b, d = self.b, self.d
        col = self._goto_param(item, items)
        before_v = d.read_column(col)[1]
        before = self._param_dict(full, slot, item, before_v)
        mapping = _map_from(item.get("map"))
        numeric, want = coerce(value, before_v, mapping)                # 숫자 입력도 enum이면 선택지 경로(리뷰 I3·I4)
        if numeric:
            probed, raw0 = False, None
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
                    return {"ok": False, "verified": "unverified", "note": note, "before": before,
                            "after": self._param_dict(full, slot, item, d.read_value(col))}
                item["map"] = _map_to(mapping)
                self.cache.save()
                probed = True
            tol = tolerance if tolerance is not None else tolerance_for(float(want), before_v.unit)
            out = set_numeric(d, col, float(want), mapping, tol, b.faders)
            if out.note.startswith("skip:"):                       # 범위 밖: map은 그대로. 방금 프로빙으로 옮긴 값은 되돌린다
                if probed:
                    if raw0 is not None:
                        d.fader(col, raw0)
                        out.note += " (프로빙으로 옮긴 값을 원래 위치로 복원)"
                    else:
                        out.note += f" (프로빙으로 값이 바뀜, 복원 못함: 원래 값 {before_v.text})"
            elif not out.ok:                                       # 틀린 map을 지워 다음에 다시 프로빙하게 한다(리뷰 m5)
                item["map"] = None
                self.cache.save()
        else:
            emap = item.get("map") or {}
            options = emap.get("options") if emap.get("type") == "enum" else None
            out = set_option(d, col, str(want), options, before_v)
        ok, verified, note = verdict(out)
        if verified == "skipped" and not ok:                       # 틱 없이 거른 경우(skip:)는 after 없이
            return {"ok": False, "verified": "skipped", "note": note, "before": before, "after": None}
        return {"ok": ok, "verified": verified, "note": note, "before": before,
                "after": self._param_dict(full, slot, item, out.value)}

    def set(self, strip: int | None, number: int | None, slot: int, param, value,
            tolerance: float | None = None) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_set"

        def body(ch: int, t0: int, target: dict) -> "ToolResult":
            full, _abbrev, pages = self._open_edit(ch, slot)
            item = self._locate(full, pages, param)
            r = self._set_one(full, slot, item, self._table(full, pages)["items"], value, tolerance)
            return b._result(action, r["ok"], r["verified"], t0, target=target, before=r["before"],
                             after=r["after"], note=r["note"])
        return self._on_slot(action, strip, number, slot, body)

    def set_many(self, strip: int | None, number: int | None, slot: int, changes: list[dict]) -> "ToolResult":
        """같은 플러그인의 값 여러 개를 편집 뷰 한 번 진입으로 맞춘다. 받은 순서대로, 첫 실패에서 멈춘다(앞 값은 되돌리지 않음).
        보내기 전에 전부 찾아 보고(읽기만), 하나라도 틀리면 아무 값도 바꾸지 않는다."""
        b, d, action = self.b, self.d, "plugin_set"

        def body(ch: int, t0: int, target: dict) -> "ToolResult":
            full, _abbrev, pages = self._open_edit(ch, slot)
            located: list[dict] = []
            for k, c in enumerate(changes, 1):
                try:
                    it = self._locate(full, pages, c["param"])
                except ParamNotFound as e:
                    raise ParamNotFound(f"changes {k}번째: {e.note}") from e
                if any(it is x for x in located):
                    raise ParamNotFound(f"changes {k}번째: {it['short']}가 두 번 나옴")
                located.append(it)
            items = self._table(full, pages)["items"]            # 모든 _locate가 끝난 뒤에 읽는다(_locate가 표를 채울 수 있다)
            heads = [{"param": c["param"], "index": it["index"], "short": it["short"], "name": it.get("name")}
                     for c, it in zip(changes, located)]

            def between() -> None:                              # 직전 값 오버레이(≈2초)가 이웃 열을 덮으므로 만기까지 기다린다
                d.settle_overlay()
                d.flip(False)
                d.toggle_name_value()

            def one(k: int) -> dict:
                c = changes[k]
                r = self._set_one(full, slot, located[k], items, c["value"], c.get("tolerance"))
                return {**r, **{x: (None if r[x] is None else {"value": r[x]["value"], "text": r[x]["text"]})
                                for x in ("before", "after")}}
            results = run_changes(heads, one, between)
            ok, verified, note = batch_verdict(len(changes), results, lambda r: r["short"])
            done = sum(1 for r in results if r["ok"])
            return b._result(action, ok, verified, t0, target=target, note=note,
                             after={"plugin": full, "slot": slot, "results": results, "done": done,
                                    "remaining": changes[len(results):]})
        return self._on_slot(action, strip, number, slot, body)

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

        def check(t0: int) -> "ToolResult | None":
            idx, cands = find(self.cache.items, plugin)
            if idx is None and cands:                        # 보내기 전에 거른다(본체도 같은 검사)
                return b._result(action, False, "skipped", t0, note=f"{plugin!r}가 여럿에 맞음: {cands}")
            return None

        def body(ch: int, t0: int, target: dict) -> "ToolResult":
            return self._insert_body(action, t0, target, ch, slot, plugin, replace)
        return self._on_slot(action, strip, number, slot, body, check=check)

    def remove(self, strip: int | None, number: int | None, slot: int) -> "ToolResult":
        action = "plugin_remove"

        def body(ch: int, t0: int, target: dict) -> "ToolResult":
            return self._remove_body(action, t0, target, ch, slot)
        return self._on_slot(action, strip, number, slot, body)

    def move(self, strip: int | None, number: int | None, slot: int, to_slot: int) -> "ToolResult":
        """슬롯 이동 = 제거 + 빈 목표 슬롯에 재삽입(MCU에 이동 명령이 없다, 스펙 4 F5). 설정값은 초기화된다.
        이름은 편집 뷰 헤더에서 읽는다(축약 캐시를 믿지 않는다, F6). 재삽입이 실패해도 되돌리지 않는다(되돌리기도 삽입)."""
        b, d, action = self.b, self.d, "plugin_move"

        def check(t0: int) -> "ToolResult | None":
            if not 1 <= to_slot <= MAX_SLOT or to_slot == slot:
                return b._result(action, False, "skipped", t0,
                                 note=f"to_slot은 1-{MAX_SLOT}이고 slot({slot})과 달라야 함")
            return None

        def body(ch: int, t0: int, target: dict) -> "ToolResult":
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
        return self._on_slot(action, strip, number, slot, body, check=check, to_slot=to_slot)

    def bypass(self, strip: int | None, number: int | None, slot: int, on: bool) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_bypass"

        def body(ch: int, t0: int, target: dict) -> "ToolResult":
            b._channel(ch, "plugin_channel")
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
        return self._on_slot(action, strip, number, slot, body)

    def calibrate(self, strip: int | None, number: int | None, slot: int) -> "ToolResult":
        """plugins/calibrate.py의 calibrate로 위임(설명은 그쪽)."""
        return cal.calibrate(self, strip, number, slot)

    def scan(self, force: bool = False) -> "ToolResult":
        """plugins/calibrate.py의 scan으로 위임."""
        return cal.scan(self, force)
