"""플러그인 캘리브레이션·삽입 메뉴 스캔 명령. PluginCommands.calibrate·scan이 위임한다(pc = PluginCommands).
편집 뷰 helper(_open_edit·_read_pages·_merge_items·_table·_goto_param)는 pc의 것을 쓴다."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from ..plugin import EMPTY_TEXTS, MAX_SLOT, _map_to, overlay_param_name
from ..setter import probe_mapping
from ..values import parse_value
from .scan import scan_list

if TYPE_CHECKING:
    from ..commands import ToolResult
    from ..plugin import PluginCommands

MAX_OPTIONS = 16        # 열거형 선택지 수집 상한(캘리브레이션)


def calibrate(pc: "PluginCommands", strip: int | None, number: int | None, slot: int) -> "ToolResult":
    """편집 뷰에서 파라미터마다 전체 이름(틱 오버레이 1행), 숫자 매핑(Flip 페이더 프로빙), 열거형 선택지(-1로 처음까지 간 뒤
    +1로 끝까지, 정착 열 텍스트)를 모아 캐시에 저장한다. 값을 바꾸고 되돌리지 않는다 → scripts/calibrate_plugin.py가
    삽입한 임시 인스턴스에만 쓴다."""
    b, d, action = pc.b, pc.d, "plugin_calibrate"
    t0 = b._now_ms()
    with b._lock:
        if (r := b._require_ready(action, t0)) is not None:
            return r
        ch = pc.b._begin(action, strip, number, t0, slot, MAX_SLOT,
                         f"slot은 1-{MAX_SLOT}(Plug-in Channel 뷰에서 닿는 슬롯만 지원)")
        if not isinstance(ch, int):
            return ch
        target = {**b._target(ch), "slot": slot}

        def body() -> "ToolResult":
            pc.b._fresh()
            full, _abbrev, pages = pc._open_edit(ch, slot)
            pc._merge_items(full, pages, pc._read_pages(pages))
            table = pc._table(full, pages)
            probed = enums = 0
            for item in table["items"]:
                col = pc._goto_param(item)                                     # VALUE 모드
                v = d.read_column(col)[1]
                header = d.surface.state.lcd[0]                                # 틱 전 1행(축약명). 이름은 틱 뒤 바뀐 칸에서만 뗀다
                name: str | None = None
                # 이름은 LCD가 바뀐 틱(tick() True)의 오버레이에서만 받는다. 끝값 무변화 틱은 오버레이가 없을 수 있어
                # 정착 1행 조각을 이름으로 읽게 된다(리뷰 I3).
                if v.kind == "enum":
                    # 텍스트가 같아도 멈추지 않고 고정 횟수: 축약이 겹치는 선택지를 남긴다(10/27 Circuit Type 'Studio'×2는 오버레이를 읽은 것, 10/28)
                    for _ in range(MAX_OPTIONS):                               # 처음(가장 앞 선택지)까지 -1(끝에선 무변화). 읽지 않으니 오버레이 대기 없음
                        if d.tick(col, -1) and name is None:
                            name = overlay_param_name(header, d.surface.state.lcd[0], col)
                    d.settle_overlay()                                         # 첫 읽기 전에만 오버레이가 걷히길 기다린다
                    texts = [d.read_column(col)[1].text]
                    for _ in range(MAX_OPTIONS - 1):                           # +1로 끝까지 모은다(처음에 있었으면 여기서 이름)
                        if d.tick(col, 1) and name is None:
                            name = overlay_param_name(header, d.surface.state.lcd[0], col)
                        d.settle_overlay()
                        texts.append(d.read_column(col)[1].text)
                    options = list(texts)
                    while len(options) > 1 and options[-1] == options[-2]:     # 끝에 닿은 뒤 무변화 틱의 반복은 하나로. 한계: 진짜로 끝에 연속된 같은 텍스트도 합쳐진다
                        options.pop()
                    capped = all(a != b for a, b in zip(texts, texts[1:]))     # 상한까지 한 번도 안 멈춤(잘라내기 전 기준 = 옛 루프가 MAX_OPTIONS개 모은 경우)
                    if capped and all(parse_value(o).kind == "number" for o in options):
                        # 상한까지 모인 숫자 선택지 = 첫 읽기가 남은 축약명을 받은 연속 숫자 파라미터(재수집 Rel·Q·Gain)
                        d.flip(True)
                        mapping, _lo, _hi = probe_mapping(d, col)
                        d.settle_overlay()                                     # 페이더 값 오버레이(14칸, 2.0초)가 다음 열을 덮어 공백·이전 값으로 읽힌다(실측 2026-10-20 Space Designer 77/178 map None)
                        item["map"] = None
                        if mapping is not None:
                            item["map"] = _map_to(mapping)
                            probed += 1
                    else:
                        item["map"] = {"type": "enum", "options": options}
                        enums += 1
                else:
                    if d.tick(col, 1):
                        name = overlay_param_name(header, d.surface.state.lcd[0], col)
                        d.tick(col, -1)
                    elif d.tick(col, -1):                                      # 최댓값이면 반대 방향으로 한 틱
                        name = overlay_param_name(header, d.surface.state.lcd[0], col)
                        d.tick(col, 1)
                    d.settle_overlay()
                    if v.kind == "number" and not item.get("map"):
                        d.flip(True)
                        mapping, _lo, _hi = probe_mapping(d, col)              # 페이더 1·16383 → 범위(실측 X: 에코 뒤 LCD까지 대기)
                        d.settle_overlay()
                        if mapping is not None:
                            item["map"] = _map_to(mapping)
                            probed += 1
                if name and "Page" not in name:
                    item["name"] = name
                d.toggle_name_value()                                           # NAME 모드로 복귀(다음 page_to가 헤더를 읽는다)
            pc.cache.save()
            return b._result(action, True, "verified", t0, target=target,
                             after={"plugin": full, "pages": pages, "items": table["items"], "probed": probed, "enums": enums})
        return b._guarded(action, t0, target, body)


def scan(pc: "PluginCommands", force: bool = False) -> "ToolResult":
    b, d, action = pc.b, pc.d, "plugin_scan"
    t0 = b._now_ms()
    with b._lock:
        if (r := b._require_ready(action, t0)) is not None:
            return r
        if pc.cache.user_list and not force:
            return b._result(action, True, "skipped", t0, after=pc.cache.to_resource(),
                             note=f"already: {pc.cache.scanned_at}에 스캔한 {len(pc.cache.user_list)}개. 다시 하려면 force=true")

        def body() -> "ToolResult":
            pc.b._fresh()
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
            pc.cache.user_list = names
            pc.cache.scanned_at = datetime.now().isoformat(timespec="seconds")
            pc.cache.save()
            d.leave(keep_select=True)                            # 미리 선택 취소(삽입 없음)
            d.enter("plugin_mixer")
            still_empty = ch in empty_strips()
            return b._result(action, still_empty, "verified" if still_empty else "unverified", t0,
                             after={"count": len(names), "path": str(pc.cache.path), "strip": ch + 1, "slot": slot},
                             note="" if still_empty else "스캔 뒤 슬롯이 비어 있지 않음(확인 누름이 섞였을 수 있음)")
        return b._guarded(action, t0, None, body)
