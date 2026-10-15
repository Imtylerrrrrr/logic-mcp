"""센드 명령(스펙 2b §4.3, 실측 S1~S11). SE(센드 채널) 뷰 한 곳에서만 다룬다: 2센드/페이지, 열 = (홀수 센드 0, 짝수 4) +
{dest 0, level 1, pos 2, mute 3}. 1행 라벨은 `Sen1In`/`Sen1De`/목적지 번호로 흔들리므로 열 위치로만 해석한다(S2).
목적지는 버스 번호 모델: `--`로 되감은 뒤 `번호+DEST_PREFIX` 틱, 오버레이의 `Bus m`을 읽어 보정, V-Pot 누름으로 확정(S4·S5).
레벨은 Flip 페이더(볼륨 dB 표, S6), pos·mute는 틱(S8·S9)."""
from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING

from .modes import CONFIRM_S, ModeError
from .plugins.scan import rewind_to_empty
from .strips import StripUnsupported
from .setter import set_numeric
from .values import Mapping, parse_value

if TYPE_CHECKING:
    from .commands import Commands, ToolResult

MAX_SEND = 8
MAX_BUS = 256
FIELDS = ("dest", "level", "pos", "mute")
POS_ORDER = ("pre", "post", "post_pan")                  # 틱 +1 방향(실측 S8)
DEST_PREFIX = 2                                           # `--` 뒤 `1`, `2` 다음이 `Bus 1`(실측 S4). 다르면 보정 루프가 맞춘다
EMPTY = ("", "--")
_POS_TEXT = {"pre": "pre", "post": "post", "pospan": "post_pan", "postpa": "post_pan", "postpan": "post_pan"}
_SEN_RE = re.compile(r"Sen(\d+)")
_BUS_RE = re.compile(r"Bus\s*(\d+)")
_QUERY_RE = re.compile(r"(?:[Bb]us\s*)?(\d+)")


def col_of(send: int, field: str) -> int:
    return (0 if send % 2 == 1 else 4) + FIELDS.index(field)


def page_of(send: int) -> int:
    return (send + 1) // 2


def se_page_of(view) -> int | None:
    """1행 첫 열 `Sen<n>…`으로 현재 페이지. 오버레이가 덮었으면 None."""
    m = _SEN_RE.match(view.columns[0][0].strip())
    return page_of(int(m.group(1))) if m else None


def bus_number(text: str) -> int | None:
    """`Bus 2`·`*Bus 2` → 2, `--` → 0, 그 밖(`1`, `2`, 빈칸, `Aux 1`) → None."""
    t = text.strip().lstrip("*")
    if t == "--":
        return 0
    m = _BUS_RE.fullmatch(t)
    return int(m.group(1)) if m else None


def pos_of_text(text: str) -> str | None:
    return _POS_TEXT.get(text.strip().replace(" ", "").lower())


def parse_send(columns, send: int) -> dict:
    off = col_of(send, "dest")
    texts = [columns[off + i][1].strip() for i in range(4)]
    dest = texts[0].lstrip("*")
    present = dest not in EMPTY
    if not present:
        return {"send": send, "present": False, "dest": None, "bus": None, "level_db": None, "pos": None, "muted": None,
                "text": texts}
    level = parse_value(texts[1])
    return {"send": send, "present": True, "dest": dest, "bus": bus_number(texts[0]),
            "level_db": level.number if level.kind == "number" else None, "pos": pos_of_text(texts[2]),
            "muted": texts[0].startswith("*") or texts[3] == "muted", "text": texts}


def dest_query(dest) -> int | None:
    """`"Bus 3"`·`"3"`·`3` → 3, `"--"`·`""`·`0` → 0(제거), 그 밖 → None."""
    if dest is None or isinstance(dest, bool):
        return None
    if isinstance(dest, int):
        return dest if 0 <= dest <= MAX_BUS else None
    t = str(dest).strip()
    if t in EMPTY or t == "0":
        return 0
    m = _QUERY_RE.fullmatch(t)
    n = int(m.group(1)) if m else None
    return n if n is not None and 1 <= n <= MAX_BUS else None


class SendCommands:
    def __init__(self, base: "Commands") -> None:
        self.b = base
        self.d = base.modes

    # ---------- 공통 ----------
    def _fresh(self) -> None:
        if self.d.view.kind != "pan" or self.b.surface.state.assignment.flip:
            self.d.leave(keep_select=True)

    def _channel(self, ch: int) -> None:
        """대상 트랙을 선택하고 SE 뷰로 간다. 출력·Master는 SE가 따라가지 않으므로 먼저 막는다(실측 Z4·S10).
        이미 SE고 다른 스트립이면 PAN으로 나가 다시 들어간다(PL의 Z3와 같은 규칙)."""
        self.b.strips.ensure(self.d, self.b.surface.state, ch)
        if self.d.view.kind != "pan" and not self.b.surface.state.strips[ch].select:
            self.d.leave(keep_select=True)
        self.d.focus(ch)
        self.d.enter("send_channel")

    def _goto_page(self, send: int) -> None:
        """SE는 마지막 페이지를 기억하므로(실측 S3) 1행 `Sen<n>`으로 현재 페이지를 읽어 커서로 간다."""
        page = page_of(send)
        cur = se_page_of(self.d.view)
        if cur is None:
            raise ModeError("page", "1행 `Sen<n>` 라벨", self.d.view.columns[0][0].strip() or "빈 열")
        if cur == page:
            return
        if not self.d.page_until(lambda v: se_page_of(v) == page, forward=page > cur, max_steps=abs(page - cur)):
            raise ModeError("page", f"센드 {send}의 페이지 {page}", f"페이지 {se_page_of(self.d.view)}")

    def _row(self, send: int) -> dict:
        return parse_send(self.d.view.columns, send)

    def _begin(self, action: str, strip, number, send, t0):
        if not 1 <= send <= MAX_SEND:
            return self.b._result(action, False, "skipped", t0, note=f"send는 1-{MAX_SEND}")
        return self.b._resolve(strip, number, action, t0)

    def _fail(self, action: str, t0: int, target: dict, e: Exception) -> "ToolResult":
        if isinstance(e, StripUnsupported):
            return self.b._result(action, False, "skipped", t0, target=target, note=e.note)
        if isinstance(e, ModeError):
            return self.b._result(action, False, "unverified", t0, target=target, note=str(e))
        return self.b._result(action, False, "skipped", t0, target=target, note=f"값 오류: {e}")

    # ---------- 명령 ----------
    def get(self, strip: int | None, number: int | None) -> "ToolResult":
        b, d, action = self.b, self.d, "send_get"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = b._resolve(strip, number, action, t0)
            if not isinstance(ch, int):
                return ch
            target = b._target(ch)
            try:
                self._fresh()
                self._channel(ch)
                sends: dict[str, dict] = {}
                for page in range(1, MAX_SEND // 2 + 1):
                    self._goto_page(2 * page - 1)
                    for send in (2 * page - 1, 2 * page):
                        sends[str(send)] = self._row(send)
                return b._result(action, True, "verified", t0, target=target, after={"sends": sends})
            except (StripUnsupported, ModeError, ValueError) as e:
                return self._fail(action, t0, target, e)
            finally:
                d.leave_safely()

    def set_dest(self, strip: int | None, number: int | None, send: int, dest) -> "ToolResult":
        b, d = self.b, self.d
        want = dest_query(dest)
        action = "send_remove" if want == 0 else "send_set_dest"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            if want is None:
                return b._result(action, False, "skipped", t0,
                                 note=f"dest는 버스 번호(1-{MAX_BUS}, 예: \"Bus 3\"·3) 또는 \"--\"(제거). 받은 값: {dest!r}")
            ch = self._begin(action, strip, number, send, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "send": send}
            col = col_of(send, "dest")
            try:
                self._fresh()
                self._channel(ch)
                self._goto_page(send)
                before = self._row(send)
                if (before["bus"] or 0) == want:
                    return b._result(action, True, "skipped", t0, target=target, before=before, after=before, note="already")
                rewind_to_empty(d, col)                                  # 오버레이 `--`까지(1틱 = 1항목이라 -63이면 넉넉, 실측 S4)
                if want > 0:
                    d.tick(col, want + DEST_PREFIX)
                    shown = bus_number(d.read_overlay_text(col))
                    for _ in range(4):                                   # 목록 앞 항목 수가 다르면 보이는 번호로 보정(실측 S4)
                        if shown == want:
                            break
                        d.tick(col, 1 if not shown else want - shown)    # `--`·`1`·`2`처럼 버스가 아니면 한 칸 앞으로
                        shown = bus_number(d.read_overlay_text(col))
                    if shown != want:                                    # 누르지 않는다: finally의 leave가 미리 선택을 취소(S4)
                        return b._result(action, False, "unverified", t0, target=target, before=before,
                                         note=f"목적지 오버레이가 {d.read_overlay_text(col)!r}(기대 Bus {want}). 확정하지 않음")
                ok = d.press_vpot_until(col, lambda v: (parse_send(v.columns, send)["bus"] or 0) == want
                                        and (want == 0 or parse_send(v.columns, send)["present"]), CONFIRM_S)
                d.settle_overlay()                                       # `Send n Instantiate` 오버레이가 지나간 뒤 읽는다(S5)
                after = self._row(send)
                ok = ok and (after["bus"] or 0) == want
                if ok:
                    note = "버스 센드를 새로 만들면 Logic이 Aux 트랙을 자동 생성해 뒤 스트립 번호가 바뀔 수 있음(실측 S5)" if want else ""
                else:
                    note = f"확정 뒤 {CONFIRM_S:.0f}초 안에 목적지가 {after['text'][0]!r}(기대 {'--' if want == 0 else f'Bus {want}'})"
                return b._result(action, ok, "verified" if ok else "unverified", t0, target=target, before=before,
                                 after=after, note=note)
            except (StripUnsupported, ModeError, ValueError) as e:
                return self._fail(action, t0, target, e)
            finally:
                d.leave_safely()

    def remove(self, strip: int | None, number: int | None, send: int) -> "ToolResult":
        return self.set_dest(strip, number, send, "--")

    def set_level(self, strip: int | None, number: int | None, send: int, db: float) -> "ToolResult":
        b, d, action = self.b, self.d, "send_set_level"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            if db != db:
                return b._result(action, False, "skipped", t0, note="db가 NaN. 예: -6.0, 0, \"-inf\"")
            ch = self._begin(action, strip, number, send, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "send": send}
            col = col_of(send, "level")
            try:
                self._fresh()
                self._channel(ch)
                self._goto_page(send)
                before = self._row(send)
                if not before["present"]:
                    return b._result(action, False, "skipped", t0, target=target,
                                     note=f"센드 {send} 없음. set_dest로 먼저 목적지를 정할 것")
                clamp = "clamped to +6.0 dB" if db > 6.0 else ""
                goal = min(db, 6.0)
                if goal == -math.inf:
                    d.flip(True)
                    d.fader(col, 1)                                        # raw 1 → `-oo dB`(실측 S6)
                    d.settle_overlay()
                    after = self._row(send)
                    ok, detail = after["level_db"] == -math.inf, ""
                else:
                    out = set_numeric(d, col, goal, Mapping("db_table"), 0.1, b.faders)   # 센드 dB 표 = 볼륨 표(실측 S6)
                    d.settle_overlay()
                    after = self._row(send)
                    ok, detail = out.ok and after["level_db"] is not None and abs(after["level_db"] - goal) <= 0.1, out.note
                    if ok and out.note == "already":
                        return b._result(action, True, "skipped", t0, target=target, before=before, after=after, note="already")
                return b._result(action, ok, "verified" if ok else "unverified", t0, target=target, before=before,
                                 after=after, note=" ".join(x for x in (clamp, detail) if x))
            except (StripUnsupported, ModeError, ValueError) as e:
                return self._fail(action, t0, target, e)
            finally:
                d.leave_safely()

    def set_pos(self, strip: int | None, number: int | None, send: int, pos: str) -> "ToolResult":
        b, d, action = self.b, self.d, "send_set_pos"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            if pos not in POS_ORDER:
                return b._result(action, False, "skipped", t0, note=f"pos는 {'|'.join(POS_ORDER)} 중 하나")
            ch = self._begin(action, strip, number, send, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "send": send}
            col = col_of(send, "pos")
            try:
                self._fresh()
                self._channel(ch)
                self._goto_page(send)
                before = self._row(send)
                if not before["present"]:
                    return b._result(action, False, "skipped", t0, target=target,
                                     note=f"센드 {send} 없음. set_dest로 먼저 목적지를 정할 것")
                cur = before["pos"]
                if cur == pos:
                    return b._result(action, True, "skipped", t0, target=target, before=before, after=before, note="already")
                if cur is None:
                    raise ModeError("pos", "Pre/Post/PosPan", before["text"][2] or "빈 열")
                after = before
                for _ in range(2):                                         # 순서 고정 Pre→Post→Post Pan(실측 S8): 차이만큼 한 번에
                    d.tick(col, POS_ORDER.index(pos) - POS_ORDER.index(cur))
                    d.settle_overlay()
                    after = self._row(send)
                    if after["pos"] == pos:
                        break
                    cur = after["pos"] or cur
                ok = after["pos"] == pos
                return b._result(action, ok, "verified" if ok else "unverified", t0, target=target, before=before,
                                 after=after, note="" if ok else f"위치가 {after['text'][2]!r}(기대 {pos})")
            except (StripUnsupported, ModeError, ValueError) as e:
                return self._fail(action, t0, target, e)
            finally:
                d.leave_safely()

    def mute(self, strip: int | None, number: int | None, send: int, on: bool) -> "ToolResult":
        b, d, action = self.b, self.d, "send_mute"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = self._begin(action, strip, number, send, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "send": send}
            col = col_of(send, "mute")
            try:
                self._fresh()
                self._channel(ch)
                self._goto_page(send)
                before = self._row(send)
                if not before["present"]:
                    return b._result(action, False, "skipped", t0, target=target,
                                     note=f"센드 {send} 없음. set_dest로 먼저 목적지를 정할 것")
                if before["muted"] == on:
                    return b._result(action, True, "skipped", t0, target=target, before=before, after=before, note="already")
                d.tick(col, 1 if on else -1)                                # +1 = muted, -1 = active(실측 S9)
                d.settle_overlay()
                after = self._row(send)
                ok = after["muted"] == on
                return b._result(action, ok, "verified" if ok else "unverified", t0, target=target, before=before,
                                 after=after, note="" if ok else f"뮤트 열이 {after['text'][3]!r}")
            except (StripUnsupported, ModeError, ValueError) as e:
                return self._fail(action, t0, target, e)
            finally:
                d.leave_safely()
