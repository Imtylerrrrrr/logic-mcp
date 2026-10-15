"""이벤트 스트림 → SurfaceState 순수 리듀서. I/O·스레드 없음."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from . import protocol as P

SETTLE_S = 0.12          # 조각난 LCD·타임 디스플레이가 잠잠해졌다고 보는 시간
READY_QUIET_S = 1.0      # 설치 애니메이션이 끝났다고 보는 조용한 시간
INSTALL_QUIET_S = 10.0   # 설치 애니메이션의 3초 공백과 시작 전 7.6초 공백을 덮는 조용 시간(핸드셰이크 뒤에만 적용)
STALE_S = 30.0           # 이 시간 동안 수신이 없으면 stale 표시
LCD_COLS = 8
COL_W = 7

_COL_RE = re.compile(r"^(\d+):(.*)$")
_ASSIGN = {P.Note.TRACK: "track", P.Note.SEND: "send", P.Note.PAN: "pan",
           P.Note.PLUGIN: "plugin", P.Note.EQ: "eq", P.Note.INSTRUMENT: "instrument"}
_TRANSPORT = {P.Note.PLAY: "play", P.Note.STOP: "stop", P.Note.RECORD: "record",
              P.Note.CYCLE: "cycle", P.Note.REWIND: "rewind", P.Note.FFWD: "ffwd"}
OVERLAY_MARK = "arameter:"   # "EQ 1 Parameter: …", "Pan/Surround parameter:" 모드 전환 오버레이 공통 조각
_PAGE_RE = re.compile(r"Page\s*(\d+)/(\d+)")
_NO_NAME_VIEWS = frozenset({"eq_channel", "eq_menu", "send_channel", "send_menu", "plugin_channel",
                            "plugin_edit", "empty_edit", "midi_fx", "track_menu"})          # 1행이 채널명이 아닌 뷰
_VALUE_VIEWS = frozenset({"pan", "track", "unknown"})                        # 2행이 볼륨·팬 값인 뷰


@dataclass(frozen=True)
class Strip:
    number: int | None = None
    name: str = ""
    rec: bool = False
    solo: bool = False
    mute: bool = False
    select: bool = False
    fader_raw: int = 0
    fader_known: bool = False
    pan_ring: tuple[int, int, bool] = (0, 0, False)
    meter: int = 0
    value_text: str = ""


@dataclass(frozen=True)
class Transport:
    play: bool = False
    stop: bool = False
    record: bool = False
    cycle: bool = False
    rewind: bool = False
    ffwd: bool = False


@dataclass(frozen=True)
class TimeDisplay:
    digits: str = " " * 10
    dots: tuple[bool, ...] = (False,) * 10
    mode: str = "unknown"  # beats | smpte | unknown

    @property
    def text(self) -> str:
        return self.digits

    def parsed(self) -> dict | None:
        if self.mode != "beats":
            return None
        d = self.digits
        try:
            return {"bars": int(d[0:3]), "beats": int(d[3:5]), "division": int(d[5:7]), "ticks": int(d[7:10])}
        except ValueError:
            return None


@dataclass(frozen=True)
class Assignment:
    mode: str | None = None
    display: str = "  "
    flip: bool = False


@dataclass(frozen=True)
class View:
    kind: str = "pan"
    index: int | None = None                     # 센드 번호, 플러그인 슬롯, EQ 파라미터 번호
    page: tuple[int, int] | None = None          # 편집 뷰 헤더 `Page 2/6`
    header: str = ""                             # NAME 모드 1행(트랙·인서트·플러그인 이름)
    columns: tuple[tuple[str, str], ...] = field(default_factory=lambda: tuple(("       ", "       ") for _ in range(8)))


@dataclass(frozen=True)
class Connection:
    state: str = "no_logic"  # no_logic | handshake | animating | ready
    last_rx: float = 0.0
    dirty_until: float = 0.0
    last_display_change: float = 0.0
    stale: bool = False
    installing: bool = False


@dataclass(frozen=True)
class SurfaceState:
    strips: tuple[Strip, ...] = field(default_factory=lambda: tuple(Strip() for _ in range(8)))
    master_fader: int = 0
    transport: Transport = Transport()
    time: TimeDisplay = TimeDisplay()
    assignment: Assignment = Assignment()
    lcd: tuple[str, str] = (" " * P.LCD_WIDTH, " " * P.LCD_WIDTH)
    leds_on: frozenset[int] = frozenset()
    view: View = View()
    connection: Connection = Connection()


def initial_state() -> SurfaceState:
    return SurfaceState()


def parse_column(col: str) -> tuple[int | None, str]:
    m = _COL_RE.match(col.strip())
    if m:
        return int(m.group(1)), m.group(2).strip()
    return None, col.strip()


def lcd_columns(lcd: tuple[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple((lcd[0][i * COL_W:(i + 1) * COL_W], lcd[1][i * COL_W:(i + 1) * COL_W]) for i in range(LCD_COLS))


def classify_view(display: str, lcd: tuple[str, str], mode: str | None) -> tuple[str, int | None]:
    """2자리 표시 + LCD 레이아웃 → (뷰 종류, 번호). 실측 코드: PN E1 EQ E_ S1 SE D1 S_ P1..P9 10..16 PL M1."""
    d = (display + "  ")[:2]
    row2 = lcd[1]
    cols = [c for c, _ in lcd_columns(lcd)]
    if d == "PN":
        return "pan", None
    if d == "E_":
        return "eq_menu", None
    if d == "EQ":
        return "eq_channel", None
    if d[0] == "E" and d[1].isdigit():
        return "eq_mixer", int(d[1])
    if d == "S_":
        return "send_menu", None
    if d == "SE":
        return "send_channel", None
    if d[0] == "S" and d[1].isdigit():
        return "send_mixer", int(d[1])
    if d[0] == "D" and d[1].isdigit():
        return "send_destlevel", int(d[1])
    if d == "C_":
        return "track_menu", None     # TRACK down: 2행이 홀드 메뉴(실측 Z5)
    if d == "CS":
        return "track", None          # Channel Strip 뷰: 1행 이름, 2행 스트립별 값(실측 Z5)
    if d == "PL":
        return "plugin_channel", None    # 코드만으로 판정: 슬롯 1 오버레이가 1행 `Ins1Pl`을 덮어도 `PL`은 그대로(실측 J)
    if d[0] == "M" and d[1].isdigit():
        return "midi_fx", int(d[1])
    slot = int(d[1]) if d[0] == "P" and d[1].isdigit() else (int(d) if d.strip().isdigit() else None)
    if slot is not None:
        if all(c.strip() == "-" for c in cols) and not row2.strip():
            return "empty_edit", slot
        if any(parse_column(c)[0] is not None for c in cols):
            return "plugin_mixer", slot
        return "plugin_edit", slot
    if mode == "track":
        return "track", None
    if not d.strip():
        return "pan", None            # 2자리 표시를 아직 못 받음(스펙 1 동작 유지)
    return "unknown", None


def _view_from(display: str, lcd: tuple[str, str], mode: str | None) -> View:
    kind, index = classify_view(display, lcd, mode)
    m = _PAGE_RE.search(lcd[0]) if kind == "plugin_edit" else None
    page = (int(m.group(1)), int(m.group(2))) if m else None
    header = lcd[0].rstrip() if page is not None else ""
    return View(kind=kind, index=index, page=page, header=header, columns=lcd_columns(lcd))


def _strips_from_lcd(strips: tuple[Strip, ...], lcd: tuple[str, str], *, with_values: bool,
                     overlay: bool) -> tuple[Strip, ...]:
    out = []
    for i, s in enumerate(strips):
        col1 = lcd[0][i * COL_W:(i + 1) * COL_W]
        col2 = lcd[1][i * COL_W:(i + 1) * COL_W]
        number, name = parse_column(col1)
        if overlay and number is None:
            number, name = s.number, s.name          # 모드 전환 오버레이가 덮은 열은 이전 값 유지
        out.append(replace(s, number=number, name=name, value_text=col2.strip() if with_values else s.value_text))
    return tuple(out)


def _set_strip(strips: tuple[Strip, ...], ch: int, **kw) -> tuple[Strip, ...]:
    if not 0 <= ch < 8:
        return strips
    return strips[:ch] + (replace(strips[ch], **kw),) + strips[ch + 1:]


def reduce(state: SurfaceState, ev: P.Event, now: float) -> SurfaceState:
    conn = replace(state.connection, last_rx=now, stale=False)
    st = replace(state, connection=conn)

    if isinstance(ev, P.DeviceQuery):
        if ev.device == P.DEVICE_ID:
            st = replace(st, connection=replace(st.connection, state="handshake", installing=True,
                                                     last_display_change=now))
        return st

    if isinstance(ev, P.LcdWrite):
        rows = [list(st.lcd[0]), list(st.lcd[1])]
        for i, b in enumerate(ev.text):
            p = ev.offset + i
            if p < 2 * P.LCD_WIDTH:
                rows[p // P.LCD_WIDTH][p % P.LCD_WIDTH] = chr(b) if 0x20 <= b < 0x7F else "?"
        lcd = ("".join(rows[0]), "".join(rows[1]))
        conn = replace(st.connection, dirty_until=now + SETTLE_S, last_display_change=now)
        if conn.state in ("no_logic", "handshake"):
            conn = replace(conn, state="animating")
        view = _view_from(st.assignment.display, lcd, st.assignment.mode)
        strips = st.strips
        if view.kind not in _NO_NAME_VIEWS:
            strips = _strips_from_lcd(strips, lcd, with_values=view.kind in _VALUE_VIEWS,
                                      overlay=OVERLAY_MARK in lcd[0])
        return replace(st, lcd=lcd, strips=strips, view=view, connection=conn)

    if isinstance(ev, P.Led):
        leds = st.leds_on | {ev.note} if ev.on else st.leds_on - {ev.note}
        st = replace(st, leds_on=leds)
        n = ev.note
        if 0x00 <= n <= 0x1F:
            kind = ("rec", "solo", "mute", "select")[n >> 3]
            return replace(st, strips=_set_strip(st.strips, n & 7, **{kind: ev.on}))
        if n in _TRANSPORT:
            return replace(st, transport=replace(st.transport, **{_TRANSPORT[n]: ev.on}))
        if n in _ASSIGN:
            mode = _ASSIGN[n] if ev.on else (None if st.assignment.mode == _ASSIGN[n] else st.assignment.mode)
            assignment = replace(st.assignment, mode=mode)
            return replace(st, assignment=assignment, view=_view_from(assignment.display, st.lcd, mode))
        if n == P.Note.FLIP:
            return replace(st, assignment=replace(st.assignment, flip=ev.on))
        if n == P.Note.BEATS_LED and ev.on:
            return replace(st, time=replace(st.time, mode="beats"))
        if n == P.Note.SMPTE_LED and ev.on:
            return replace(st, time=replace(st.time, mode="smpte"))
        return st

    if isinstance(ev, P.FaderPos):
        if ev.channel == 8:
            return replace(st, master_fader=ev.value)
        return replace(st, strips=_set_strip(st.strips, ev.channel, fader_raw=ev.value, fader_known=True))

    if isinstance(ev, P.VpotRing):
        conn = replace(st.connection, last_display_change=now)
        return replace(st, connection=conn,
                       strips=_set_strip(st.strips, ev.channel, pan_ring=(ev.mode, ev.pos, ev.center)))

    if isinstance(ev, P.Meter):
        return replace(st, strips=_set_strip(st.strips, ev.channel, meter=ev.level))

    if isinstance(ev, P.TimeDigit):
        digits = list(st.time.digits)
        dots = list(st.time.dots)
        digits[ev.index] = ev.char
        dots[ev.index] = ev.dot
        conn = replace(st.connection, dirty_until=now + SETTLE_S)
        return replace(st, time=replace(st.time, digits="".join(digits), dots=tuple(dots)), connection=conn)

    if isinstance(ev, P.AssignDigit):
        disp = list(st.assignment.display)
        disp[ev.index] = ev.char
        assignment = replace(st.assignment, display="".join(disp))
        return replace(st, assignment=assignment,
                       view=_view_from(assignment.display, st.lcd, assignment.mode))

    return st


def tick(state: SurfaceState, now: float) -> SurfaceState:
    conn = state.connection
    if conn.state in ("handshake", "animating") and conn.last_display_change > 0 \
            and now - conn.last_display_change >= (INSTALL_QUIET_S if conn.installing else READY_QUIET_S):
        conn = replace(conn, state="ready", installing=False)
    stale = conn.state != "no_logic" and not state.transport.play and now - conn.last_rx >= STALE_S
    if stale != conn.stale:
        conn = replace(conn, stale=stale)
    return state if conn is state.connection else replace(state, connection=conn)
