"""플러그인 삽입 메뉴 스캔. 빈 슬롯의 V-Pot을 돌려 미리 선택 오버레이의 이름을 읽기만 한다(확인 누름 없음 → 삽입 없음)."""
from __future__ import annotations

from ..modes import ModeDriver, ModeError

ITEM_TICKS = 2          # 1항목 = 2틱(실측)
REWIND_CHUNK = -63
MAX_REWIND = 80         # ≈ 2520항목
MAX_ITEMS = 2000
STALE_LIMIT = 3


def rewind_to_empty(d: ModeDriver, ch: int) -> None:
    """목록 처음(`--`)까지 되감는다."""
    for _ in range(MAX_REWIND):
        changed = d.tick(ch, REWIND_CHUNK)
        if d.read_overlay_text(ch) == "--":
            return
        if not changed:
            break
    raise ModeError("rewind", "'--'", d.read_overlay_text(ch) or "오버레이 없음")


def scan_list(d: ModeDriver, ch: int) -> list[str]:
    """plugin_mixer 뷰에서 호출. `--`부터 한 항목씩 전진하며 21자 이름을 모은다. 끝나면 호출자가 leave()로 취소한다."""
    rewind_to_empty(d, ch)
    names = ["--"]
    stale = 0
    while len(names) < MAX_ITEMS:
        changed = d.tick(ch, ITEM_TICKS)
        text = d.read_overlay_text(ch)
        if not changed or text == names[-1] or not text or "Plug-in" not in d.read_overlay_name(ch):   # 오버레이가 끝나 열 재묘사로 돌아간 글자는 이름이 아니다
            stale += 1
            if stale >= STALE_LIMIT:
                break
            continue
        stale = 0
        if text == "--":
            break                                     # 한 바퀴 돌아 처음으로
        names.append(text)
    return names
