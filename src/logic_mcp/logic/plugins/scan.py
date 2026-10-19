"""플러그인 삽입 메뉴 스캔. 빈 슬롯의 V-Pot을 돌려 미리 선택 오버레이의 이름을 읽기만 한다(확인 누름 없음 → 삽입 없음)."""
from __future__ import annotations

from ..modes import ModeDriver, ModeError
from .match import strip_suffix

ITEM_TICKS = 2          # 1항목 = 2틱. 위치 모델은 ceil: 표시 항목 = (틱 위치 + 1) // 2, `--`=0(실측 E)
REWIND_CHUNK = -63
MAX_REWIND = 80         # ≈ 2520항목
MAX_ITEMS = 2000
STALE_LIMIT = 3
SCAN_STEP = 1           # 스캔은 1틱씩: Logic이 틱 하나의 오버레이 쓰기를 가끔 빠뜨려 2틱 전진은 그 항목을 잃는다(실측 scan_diag)


def rewind_to_empty(d: ModeDriver, ch: int) -> None:
    """목록 처음(`--`)까지 되감는다."""
    for _ in range(MAX_REWIND):
        changed = d.tick(ch, REWIND_CHUNK)
        if d.read_overlay_text(ch) == "--":
            d.settle_quiet()                          # 되감기의 `--` 쓰기가 늦게 와서 다음 읽기를 오염시키지 않도록(실측 S)
            return
        if not changed:
            break
    raise ModeError("rewind", "'--'", d.read_overlay_text(ch) or "오버레이 없음")


def scan_list(d: ModeDriver, ch: int) -> list[str]:
    """plugin_mixer(또는 plugin_channel) 뷰에서 호출. `--`부터 1틱씩 전진하며 21자 이름을 모은다(`(s/s)` 같은
    채널 구성 접미는 슬롯마다 달라 떼어 둔다). 1항목 = 2위치라 같은 이름이 이어 보이는 것은 정상이다. 끝나면 호출자가 leave()로 취소한다."""
    rewind_to_empty(d, ch)
    names = ["--"]
    stale = 0
    for _ in range(MAX_ITEMS * ITEM_TICKS):
        changed = d.tick(ch, SCAN_STEP)
        text = strip_suffix(d.read_overlay_text(ch))
        if not changed or not text or "Plug-in" not in d.read_overlay_name(ch):   # 무변화(목록 끝 클램프·둘째 위치·빠진 쓰기)나 열 재묘사로 돌아간 글자
            stale += 1
            if stale >= STALE_LIMIT:
                break
            continue
        if text == names[-1]:
            continue                                  # 같은 항목의 둘째 위치(또는 빠진 쓰기 뒤): 정상
        stale = 0
        if text == "--":
            break                                     # 한 바퀴 돌아 처음으로
        names.append(text)
    return names
