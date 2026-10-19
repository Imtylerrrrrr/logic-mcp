"""플러그인 삽입 메뉴 스캔. 빈 슬롯의 V-Pot을 돌려 미리 선택 오버레이의 이름을 읽기만 한다(확인 누름 없음 → 삽입 없음)."""
from __future__ import annotations

from ..modes import ModeDriver, ModeError
from .match import strip_suffix

ITEM_TICKS = 2          # 1항목 = 2틱. 위치 모델은 ceil: 표시 항목 = (틱 위치 + 1) // 2, `--`=0(실측 E)
REWIND_CHUNK = -63
MAX_REWIND = 80         # ≈ 2520항목
MAX_ITEMS = 2000
STALE_LIMIT = 3
REREADS = 2             # 틱이 반응했는데 이름이 낡았으면 같은 위치에서 다시 읽는 횟수(재수집: 늦은 오버레이로 항목이 빠짐)
REREAD_S = 0.3


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
    """plugin_mixer(또는 plugin_channel) 뷰에서 호출. `--`부터 2틱씩 전진하며 21자 이름을 모은다(`(s/s)` 같은
    채널 구성 접미는 슬롯마다 달라 떼어 둔다). 끝나면 호출자가 leave()로 취소한다."""
    rewind_to_empty(d, ch)
    names = ["--"]
    stale = 0

    def is_stale(text: str) -> bool:
        return text == names[-1] or not text or "Plug-in" not in d.read_overlay_name(ch)   # 오버레이가 끝나 열 재묘사로 돌아간 글자는 이름이 아니다

    while len(names) < MAX_ITEMS:
        changed = d.tick(ch, ITEM_TICKS)
        text = strip_suffix(d.read_overlay_text(ch))
        for _ in range(REREADS):                      # 오버레이가 늦게 오는 항목: 틱 없이 같은 위치에서 다시 읽는다
            if not changed or not is_stale(text):
                break
            d.pause(REREAD_S)
            text = strip_suffix(d.read_overlay_text(ch))
        if not changed or is_stale(text):
            stale += 1
            if stale >= STALE_LIMIT:
                break
            continue
        stale = 0
        if text == "--":
            break                                     # 한 바퀴 돌아 처음으로
        names.append(text)
    return names
