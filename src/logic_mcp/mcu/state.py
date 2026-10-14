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
    connection: Connection = Connection()


def initial_state() -> SurfaceState:
    return SurfaceState()


def parse_column(col: str) -> tuple[int | None, str]:
    m = _COL_RE.match(col.strip())
    if m:
        return int(m.group(1)), m.group(2).strip()
    return None, col.strip()


def _strips_from_lcd(strips: tuple[Strip, ...], lcd: tuple[str, str]) -> tuple[Strip, ...]:
    out = []
    for i, s in enumerate(strips):
        col1 = lcd[0][i * COL_W:(i + 1) * COL_W]
        col2 = lcd[1][i * COL_W:(i + 1) * COL_W]
        number, name = parse_column(col1)
        out.append(replace(s, number=number, name=name, value_text=col2.strip()))
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
        return replace(st, lcd=lcd, strips=_strips_from_lcd(st.strips, lcd), connection=conn)

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
            return replace(st, assignment=replace(st.assignment, mode=mode))
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
        return replace(st, assignment=replace(st.assignment, display="".join(disp)))

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
