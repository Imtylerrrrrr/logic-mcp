"""Mackie Control 프로토콜: 바이트 ↔ 이벤트 순수 함수. I/O 없음."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union

DEVICE_ID = 0x14
SYSEX_HEADER = bytes([0xF0, 0x00, 0x00, 0x66])
SERIAL = b"LGCMCP1"
CHALLENGE = bytes([0x01, 0x02, 0x03, 0x04])
VERSION = b"V1.00"
LCD_WIDTH = 56


class Note:
    REC = 0x00
    SOLO = 0x08
    MUTE = 0x10
    SELECT = 0x18
    VPOT_PUSH = 0x20
    TRACK = 0x28
    SEND = 0x29
    PAN = 0x2A
    PLUGIN = 0x2B
    EQ = 0x2C
    INSTRUMENT = 0x2D
    BANK_LEFT = 0x2E
    BANK_RIGHT = 0x2F
    CHANNEL_LEFT = 0x30
    CHANNEL_RIGHT = 0x31
    FLIP = 0x32
    GLOBAL_VIEW = 0x33
    NAME_VALUE = 0x34
    SMPTE_BEATS = 0x35
    F1 = 0x36  # F1-F8 = 0x36-0x3D
    CURSOR_UP = 0x60
    CURSOR_DOWN = 0x61
    CURSOR_LEFT = 0x62
    CURSOR_RIGHT = 0x63
    ZOOM = 0x64
    SHIFT = 0x46
    OPTION = 0x47
    CONTROL = 0x48
    ALT = 0x49
    CYCLE = 0x56
    REWIND = 0x5B
    FFWD = 0x5C
    STOP = 0x5D
    PLAY = 0x5E
    RECORD = 0x5F
    FADER_TOUCH = 0x68  # + 채널 0-7, 마스터 0x70
    SMPTE_LED = 0x71
    BEATS_LED = 0x72
    RUDE_SOLO = 0x73


NOTE_NAMES: dict[int, str] = {
    **{Note.REC + i: f"REC{i + 1}" for i in range(8)},
    **{Note.SOLO + i: f"SOLO{i + 1}" for i in range(8)},
    **{Note.MUTE + i: f"MUTE{i + 1}" for i in range(8)},
    **{Note.SELECT + i: f"SELECT{i + 1}" for i in range(8)},
    **{Note.VPOT_PUSH + i: f"VPOT_PUSH{i + 1}" for i in range(8)},
    **{Note.FADER_TOUCH + i: f"FADER_TOUCH{i + 1}" for i in range(9)},
    **{v: k for k, v in vars(Note).items() if not k.startswith("_") and isinstance(v, int)
       and k not in ("REC", "SOLO", "MUTE", "SELECT", "VPOT_PUSH", "FADER_TOUCH")},
}


@dataclass(frozen=True)
class DeviceQuery:
    device: int


@dataclass(frozen=True)
class VersionRequest:
    device: int


@dataclass(frozen=True)
class LcdWrite:
    offset: int
    text: bytes


@dataclass(frozen=True)
class Led:
    note: int
    on: bool


@dataclass(frozen=True)
class FaderPos:
    channel: int  # 0-7, 마스터 8
    value: int    # 0-16383


@dataclass(frozen=True)
class TimeDigit:
    index: int  # 0 = 맨 왼쪽(CC 0x49) … 9 = 맨 오른쪽(CC 0x40)
    char: str
    dot: bool


@dataclass(frozen=True)
class AssignDigit:
    index: int  # 0 = 왼쪽(CC 0x4B), 1 = 오른쪽(CC 0x4A)
    char: str
    dot: bool


@dataclass(frozen=True)
class VpotRing:
    channel: int
    mode: int
    pos: int
    center: bool


@dataclass(frozen=True)
class Meter:
    channel: int
    level: int


@dataclass(frozen=True)
class McuSysex:
    command: int
    payload: bytes


@dataclass(frozen=True)
class Unknown:
    data: bytes


Event = Union[DeviceQuery, VersionRequest, LcdWrite, Led, FaderPos, TimeDigit,
              AssignDigit, VpotRing, Meter, McuSysex, Unknown]


def seg_char(v: int) -> tuple[str, bool]:
    """7세그먼트 문자 코드 → (문자, 점). 0x00-0x1F는 '@A-Z…', 0x20-0x3F는 ASCII 그대로."""
    c = v & 0x3F
    ch = chr(c + 0x40) if c < 0x20 else chr(c)
    return ch, bool(v & 0x40)


def decode(data: bytes) -> Event:
    if not data:
        return Unknown(data=data)
    st = data[0]
    if st == 0xF0:
        if len(data) >= 7 and data[:4] == SYSEX_HEADER and data[-1] == 0xF7:
            dev, cmd, payload = data[4], data[5], data[6:-1]
            if cmd == 0x00:
                return DeviceQuery(device=dev)
            if cmd == 0x13:
                return VersionRequest(device=dev)
            if cmd == 0x12 and len(payload) >= 1:
                return LcdWrite(offset=payload[0], text=bytes(payload[1:]))
            return McuSysex(command=cmd, payload=bytes(payload))
        return Unknown(data=data)
    kind = st & 0xF0
    if kind == 0x90 and len(data) == 3:
        return Led(note=data[1], on=data[2] != 0)
    if kind == 0xE0 and len(data) == 3:
        return FaderPos(channel=st & 0x0F, value=data[1] | (data[2] << 7))
    if kind == 0xB0 and len(data) == 3:
        cc, v = data[1], data[2]
        if 0x40 <= cc <= 0x49:
            ch, dot = seg_char(v)
            return TimeDigit(index=0x49 - cc, char=ch, dot=dot)
        if cc in (0x4A, 0x4B):
            ch, dot = seg_char(v)
            return AssignDigit(index=0x4B - cc, char=ch, dot=dot)
        if 0x30 <= cc <= 0x37:
            return VpotRing(channel=cc - 0x30, mode=(v >> 4) & 0x3, pos=v & 0x0F, center=bool(v & 0x40))
        return Unknown(data=data)
    if kind == 0xD0 and len(data) == 2:
        return Meter(channel=data[1] >> 4, level=data[1] & 0x0F)
    return Unknown(data=data)


def parse_fixture_line(line: str) -> tuple[float, str, bytes] | None:
    parts = line.split()
    if len(parts) < 3 or parts[1] not in ("RX", "TX"):
        return None
    return float(parts[0]), parts[1], bytes(int(x, 16) for x in parts[2:])


def load_fixture(path: str | Path) -> list[tuple[float, str, bytes]]:
    rows = []
    for line in Path(path).read_text().splitlines():
        parsed = parse_fixture_line(line)
        if parsed:
            rows.append(parsed)
    return rows


MAX_FADER = 16383


def handshake_reply(ev: Event) -> bytes | None:
    """Logic의 쿼리에 대한 응답. 0x14(본체)에만 답한다."""
    if isinstance(ev, DeviceQuery) and ev.device == DEVICE_ID:
        return SYSEX_HEADER + bytes([DEVICE_ID, 0x01]) + SERIAL + CHALLENGE + b"\xF7"
    if isinstance(ev, VersionRequest) and ev.device == DEVICE_ID:
        return SYSEX_HEADER + bytes([DEVICE_ID, 0x14]) + VERSION + b"\xF7"
    return None


def button_down(note: int) -> bytes:
    return bytes([0x90, note, 0x7F])


def button_up(note: int) -> bytes:
    return bytes([0x90, note, 0x00])


def fader_move(channel: int, value: int) -> list[bytes]:
    if not 0 <= channel <= 8:
        raise ValueError(f"channel {channel} not in 0..8")
    if not 0 <= value <= MAX_FADER:
        raise ValueError(f"value {value} not in 0..{MAX_FADER}")
    touch = Note.FADER_TOUCH + channel
    return [button_down(touch), bytes([0xE0 | channel, value & 0x7F, value >> 7]), button_up(touch)]


def vpot_turn(channel: int, steps: int) -> bytes:
    if steps == 0:
        raise ValueError("steps must be nonzero")
    mag = min(abs(steps), 63)
    return bytes([0xB0, 0x10 + channel, mag if steps > 0 else 0x40 | mag])


def vpot_turn_messages(channel: int, steps: int) -> list[bytes]:
    """크기 63 제한을 넘는 틱을 여러 메시지로 나눈다. 드라이버는 vpot_turn 대신 이것만 쓴다."""
    out: list[bytes] = []
    remaining, sign = abs(steps), (1 if steps > 0 else -1)
    while remaining > 0:
        n = min(remaining, 63)
        out.append(vpot_turn(channel, sign * n))
        remaining -= n
    return out
