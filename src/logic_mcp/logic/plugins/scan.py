"""플러그인 삽입 메뉴 스캔. 빈 슬롯의 V-Pot을 돌려 미리 선택 오버레이의 이름을 읽기만 한다(확인 누름 없음 → 삽입 없음)."""
from __future__ import annotations

from ..modes import ModeDriver, ModeError
from .match import normalize, strip_suffix

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


RECHECK_S = 0.4         # 이름이 맞으면 이만큼 뒤 다시 읽어 같을 때만 멈춘다(실측 S: 오버레이 지연)
WRAP_GRACE = 4          # 되감기의 늦은 `--` 쓰기(실측 S)를 한 바퀴로 오인하지 않도록 처음 몇 틱은 `--`를 무시


def seek_by_name(d: ModeDriver, ch: int, want: str, prefix: bool = False) -> tuple[bool, int, str]:
    """`--`로 되감은 뒤 1틱씩 전진하며 오버레이 이름이 want와 맞는 항목을 찾는다(실전 F1: 캐시 위치가 프로젝트 메뉴와 다름).
    맞음 = 정규화 일치(prefix면 접두 일치), RECHECK_S 뒤 재확인. scan_list와 같은 상한(STALE_LIMIT·MAX_ITEMS)에
    WRAP_GRACE틱 뒤의 `--`(한 바퀴)에서도 멈춘다. 찾으면 그 항목을 미리 선택한 채 돌려준다(누르기는 호출자).
    (찾음, 보낸 틱 수, 마지막으로 읽은 이름)."""
    q = normalize(want)

    def hit(text: str) -> bool:
        n = normalize(text)
        return bool(q) and (n == q or (prefix and n.startswith(q)))
    rewind_to_empty(d, ch)
    ticks = stale = 0
    last = "--"
    for _ in range(MAX_ITEMS * ITEM_TICKS):
        changed = d.tick(ch, SCAN_STEP)
        ticks += SCAN_STEP
        text = strip_suffix(d.read_overlay_text(ch))
        if not changed or not text or "Plug-in" not in d.read_overlay_name(ch):   # scan_list와 같은 무변화 판정
            stale += 1
            if stale >= STALE_LIMIT:
                break
            continue
        if text == "--":
            if ticks > WRAP_GRACE:
                break                                 # 한 바퀴 돌아 처음으로
            continue
        if text != last:
            stale = 0
            last = text
        if hit(text):
            d.pause(RECHECK_S)
            again = strip_suffix(d.read_overlay_text(ch))
            if hit(again):
                return True, ticks, again
    return False, ticks, last
