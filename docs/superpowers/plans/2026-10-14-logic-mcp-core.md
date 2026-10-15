# logic-mcp 코어 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Claude Code가 Logic Pro의 트랜스포트·트랙·믹서를 Mackie Control 에뮬레이션으로 조작하고 피드백으로 검증하는 MCP 서버.

**Architecture:** 단일 Python 프로세스. 순수 함수 프로토콜 계층(바이트↔이벤트) → 순수 리듀서(이벤트→`SurfaceState`) → `Surface`(rtmidi 가상 포트 + 상태 + 대기) → `Commands`(보내고 피드백 기다려 판정) → `MCPServer` 툴/리소스. 모든 명령은 Logic이 돌려주는 LED·페이더·LCD로 검증한다.

**Tech Stack:** Python 3.13, uv, `mcp>=2.3,<3`(v2 `MCPServer`), `python-rtmidi`, `pydantic`, `pytest`, `anyio`.

**Spec:** `docs/superpowers/specs/2026-10-14-logic-mcp-core-design.md`

## Global Constraints

- Python `>=3.13`. 의존성 `mcp>=2.3,<3`, `python-rtmidi>=1.5.8`, `pydantic>=2`. 개발 `pytest>=8`, `anyio>=4`.
- 패키지명 `logic_mcp`, src 레이아웃, 콘솔 스크립트 `logic-mcp`.
- MCU 디바이스 ID는 `0x14`만 응답한다. 다른 ID 쿼리에는 아무것도 보내지 않는다.
- 가상 포트 이름은 `"LogicMCP"` 고정. 프로세스 수명 동안 다시 만들지 않는다.
- 툴 이름은 `logic_` 접두사. 토글 액션을 노출하지 않는다.
- 모든 툴은 `ToolResult`(ok, verified, action, target, before, after, elapsed_ms, note)를 돌려준다.
- 제한 시간: LED 500ms, 페이더 800ms, 팬 500ms, 뱅크 1000ms. 잠잠해짐 120ms. ready 판정 조용 1.0초(재바인딩). 핸드셰이크(DeviceQuery 0x14) 뒤에는 10초(`INSTALL_QUIET_S`): 실측 설치 애니메이션은 677~736초에 걸치고 안에 3초 공백, 시작 전 7.6초 공백이 있다(Task 5 구현 중 수정, 2026-10-14).
- 자동 재시도 없음. 전역 명령 락. `ready`가 아니면 `logic_session` 외 툴은 보내지 않는다.
- 원시 픽스처 형식: `  <초>.<밀리초> RX|TX <hex bytes>` 한 줄씩.
- 커밋은 기능 단위, 변경 200줄 안쪽. 실제 Logic으로 확인한 뒤에만 완료.
- 실제 Logic 검증 중 MPK mini IV 설정과 "기본값 재형성" 메뉴는 절대 건드리지 않는다.

## Review Focus

1. sysex가 `F7` 없이 끊기거나 빈 메시지가 오면 `decode`는 예외 없이 `Unknown`을 돌려줘야 한다. → Task 2 테스트.
2. `db`가 +6.0을 넘거나 NaN이면 클램프 또는 거부하고 `note`에 적어야 한다. 음수 무한대 문자열 `"-inf"`는 페이더 0이어야 한다. → Task 7, Task 9 테스트.
3. `strip`과 `number`를 둘 다 주거나 둘 다 안 주거나 `strip`이 1-8 밖이면 보내지 않고 고치는 법을 알려줘야 한다. → Task 8 테스트.
4. LCD 열이 `12:Aud`처럼 두 자리 번호면 번호 12, 이름 `Aud`로 파싱해야 하고, 번호 없는 열은 `number=None`이어야 한다. → Task 4 테스트.
5. 팬 값 텍스트가 정수가 아니면(`-`, 빈칸, `dB` 텍스트) `set_pan`은 V-Pot +1 한 번으로 값을 드러내 보고, 그래도 팬 텍스트가 아니면 보내지 않고 설정을 고치라고 해야 한다(실기 검증에서 수정: 2행은 마지막으로 바뀐 파라미터 값을 보여줌). → Task 9 테스트.

---

## 파일 구조

```
logic-mcp/
  pyproject.toml
  README.md
  .mcp.json.example
  .gitignore
  src/logic_mcp/__init__.py
  src/logic_mcp/mcu/__init__.py
  src/logic_mcp/mcu/protocol.py      # 바이트↔이벤트, 인코더, 핸드셰이크 응답, 픽스처 파서
  src/logic_mcp/mcu/state.py         # SurfaceState 리듀서 + tick
  src/logic_mcp/mcu/transport.py     # RtMidiTransport, Transport 프로토콜
  src/logic_mcp/mcu/surface.py       # 트랜스포트+상태+락+대기
  src/logic_mcp/logic/__init__.py
  src/logic_mcp/logic/faders.py      # dB 표, 텍스트 파서
  src/logic_mcp/logic/fader_db.json  # 임시표 → Task 12에서 캘리브레이션 결과로 교체
  src/logic_mcp/logic/commands.py    # ToolResult, Commands
  src/logic_mcp/server/__init__.py
  src/logic_mcp/server/app.py        # create_server
  src/logic_mcp/server/tools.py      # register_tools
  src/logic_mcp/server/resources.py  # register_resources
  src/logic_mcp/server/main.py       # main()
  tests/fakes.py                     # FakeTransport, make_surface
  tests/fixtures/mcu/cap_raw6.log    # ~/logic-mcp-spike/cap_raw6.log 복사
  tests/fixtures/mcu/cap_raw2.log    # ~/logic-mcp-spike/cap_raw2.log 복사
  tests/test_protocol.py
  tests/test_state.py
  tests/test_surface.py
  tests/test_faders.py
  tests/test_commands.py
  tests/test_server.py
  scripts/capture.py
  scripts/live_check.py
  scripts/calibrate_fader.py
  docs/mcu-protocol.md
  docs/progress.md
```

---

### Task 1: 프로젝트 뼈대와 픽스처

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `src/logic_mcp/__init__.py`, `src/logic_mcp/mcu/__init__.py`, `src/logic_mcp/logic/__init__.py`, `src/logic_mcp/server/__init__.py`, `docs/progress.md`
- Create: `tests/fixtures/mcu/cap_raw6.log`, `tests/fixtures/mcu/cap_raw2.log` (복사)
- Test: `tests/test_smoke.py`

**Interfaces:**
- Produces: 패키지 `logic_mcp`, 픽스처 경로 `tests/fixtures/mcu/`.

- [ ] **Step 1: pyproject.toml 작성**

```toml
[project]
name = "logic-mcp"
version = "0.1.0"
description = "Logic Pro를 Mackie Control 에뮬레이션으로 조작하는 MCP 서버"
requires-python = ">=3.13"
dependencies = [
    "mcp>=2.3,<3",
    "python-rtmidi>=1.5.8",
    "pydantic>=2",
]

[project.scripts]
logic-mcp = "logic_mcp.server.main:main"

[dependency-groups]
dev = ["pytest>=8", "anyio>=4"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/logic_mcp"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: .gitignore와 빈 패키지 파일**

`.gitignore`:
```
.venv/
__pycache__/
*.pyc
.pytest_cache/
dist/
*.egg-info/
```

빈 파일 4개: `src/logic_mcp/__init__.py`, `src/logic_mcp/mcu/__init__.py`, `src/logic_mcp/logic/__init__.py`, `src/logic_mcp/server/__init__.py`

- [ ] **Step 3: 픽스처 복사**

```bash
mkdir -p tests/fixtures/mcu
cp ~/logic-mcp-spike/cap_raw6.log ~/logic-mcp-spike/cap_raw2.log tests/fixtures/mcu/
wc -l tests/fixtures/mcu/*.log
```
Expected: cap_raw6.log 4500줄 이상, cap_raw2.log 1300줄 이상.

- [ ] **Step 4: 스모크 테스트 작성**

`tests/test_smoke.py`:
```python
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "mcu"


def test_package_imports():
    import logic_mcp  # noqa: F401


def test_fixtures_present():
    lines = (FIXTURES / "cap_raw6.log").read_text().splitlines()
    assert len(lines) > 4000
    assert lines[0].split()[1] in ("RX", "TX")
```

- [ ] **Step 5: 동기화하고 테스트 실행**

Run: `uv sync && uv run pytest -q`
Expected: `2 passed`

- [ ] **Step 6: docs/progress.md 작성**

```markdown
# 진행 (스펙 1)

스펙: docs/superpowers/specs/2026-10-14-logic-mcp-core-design.md
계획: docs/superpowers/plans/2026-10-14-logic-mcp-core.md

## 완료
- Task 1 뼈대·픽스처

## 다음
- Task 2 protocol 디코드

## 메모
- 스파이크 자료: ~/logic-mcp-spike (진행상황.md, 리서치.md)
```

- [ ] **Step 7: 커밋**

```bash
git add -A
git commit -m "chore: 프로젝트 뼈대, 픽스처, 스모크 테스트"
```

---

### Task 2: protocol 디코드와 픽스처 파서

**Files:**
- Create: `src/logic_mcp/mcu/protocol.py`
- Test: `tests/test_protocol.py`

**Interfaces:**
- Produces:
  - `class Note` 상수(아래 코드), `NOTE_NAMES: dict[int, str]`
  - 이벤트 dataclass: `DeviceQuery(device)`, `VersionRequest(device)`, `LcdWrite(offset, text: bytes)`, `Led(note, on)`, `FaderPos(channel, value)`, `TimeDigit(index, char, dot)`, `AssignDigit(index, char, dot)`, `VpotRing(channel, mode, pos, center)`, `Meter(channel, level)`, `McuSysex(command, payload: bytes)`, `Unknown(data: bytes)`; `Event = Union[...]`
  - `decode(data: bytes) -> Event`
  - `seg_char(v: int) -> tuple[str, bool]`
  - `parse_fixture_line(line: str) -> tuple[float, str, bytes] | None`
  - `load_fixture(path) -> list[tuple[float, str, bytes]]`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_protocol.py`:
```python
from pathlib import Path

import pytest

from logic_mcp.mcu import protocol as P

FIXTURE = Path(__file__).parent / "fixtures" / "mcu" / "cap_raw6.log"


def test_parse_fixture_line():
    ts, d, data = P.parse_fixture_line("  754.235 RX 90 10 7F")
    assert ts == pytest.approx(754.235)
    assert d == "RX"
    assert data == bytes([0x90, 0x10, 0x7F])
    assert P.parse_fixture_line("") is None


def test_decode_device_query_and_version():
    assert P.decode(bytes.fromhex("F0 00 00 66 14 00 F7")) == P.DeviceQuery(device=0x14)
    assert P.decode(bytes.fromhex("F0 00 00 66 15 00 F7")) == P.DeviceQuery(device=0x15)
    assert P.decode(bytes.fromhex("F0 00 00 66 14 13 00 F7")) == P.VersionRequest(device=0x14)


def test_decode_lcd_write():
    ev = P.decode(bytes.fromhex("F0 00 00 66 14 12 38 4D 75 74 65 64 F7"))
    assert ev == P.LcdWrite(offset=56, text=b"Muted")


def test_decode_led_fader_ring_meter():
    assert P.decode(bytes([0x90, 0x10, 0x7F])) == P.Led(note=0x10, on=True)
    assert P.decode(bytes([0x90, 0x5D, 0x00])) == P.Led(note=0x5D, on=False)
    assert P.decode(bytes([0xE0, 0x06, 0x4E])) == P.FaderPos(channel=0, value=9990)
    assert P.decode(bytes([0xE8, 0x00, 0x00])) == P.FaderPos(channel=8, value=0)
    assert P.decode(bytes([0xB0, 0x30, 0x16])) == P.VpotRing(channel=0, mode=1, pos=6, center=False)
    assert P.decode(bytes([0xB0, 0x31, 0x56])) == P.VpotRing(channel=1, mode=1, pos=6, center=True)
    assert P.decode(bytes([0xD0, 0x2C])) == P.Meter(channel=2, level=12)


def test_decode_time_and_assign_digits():
    # CC 0x49가 맨 왼쪽(index 0), 0x40이 맨 오른쪽(index 9)
    assert P.decode(bytes([0xB0, 0x41, 0x34])) == P.TimeDigit(index=8, char="4", dot=False)
    assert P.decode(bytes([0xB0, 0x49, 0x20])) == P.TimeDigit(index=0, char=" ", dot=False)
    assert P.decode(bytes([0xB0, 0x40, 0x71])) == P.TimeDigit(index=9, char="1", dot=True)
    assert P.decode(bytes([0xB0, 0x4B, 0x10])) == P.AssignDigit(index=0, char="P", dot=False)


def test_decode_other_mcu_sysex_and_unknown():
    assert P.decode(bytes.fromhex("F0 00 00 66 14 0E 00 03 F7")) == P.McuSysex(command=0x0E, payload=bytes([0x00, 0x03]))
    assert P.decode(bytes.fromhex("F0 00 00 66 14 12 38 4D")) == P.Unknown(data=bytes.fromhex("F0 00 00 66 14 12 38 4D"))
    assert P.decode(b"") == P.Unknown(data=b"")
    assert P.decode(bytes([0xF0, 0x7E, 0x00])) == P.Unknown(data=bytes([0xF0, 0x7E, 0x00]))
    assert P.decode(bytes([0xB0, 0x3C, 0x01])) == P.Unknown(data=bytes([0xB0, 0x3C, 0x01]))


def test_seg_char():
    assert P.seg_char(0x34) == ("4", False)
    assert P.seg_char(0x74) == ("4", True)
    assert P.seg_char(0x10) == ("P", False)
    assert P.seg_char(0x20) == (" ", False)


def test_fixture_decodes_without_error():
    rows = P.load_fixture(FIXTURE)
    assert len(rows) > 4000
    kinds = set()
    for _ts, direction, data in rows:
        if direction != "RX":
            continue
        kinds.add(type(P.decode(data)).__name__)
    assert {"LcdWrite", "Led", "FaderPos", "TimeDigit", "VpotRing", "DeviceQuery", "VersionRequest"} <= kinds
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_protocol.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'logic_mcp.mcu.protocol'`

- [ ] **Step 3: protocol.py 구현(디코드 부분)**

`src/logic_mcp/mcu/protocol.py`:
```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_protocol.py -q`
Expected: `8 passed`

- [ ] **Step 5: 커밋**

```bash
git add src/logic_mcp/mcu/protocol.py tests/test_protocol.py
git commit -m "feat(mcu): MCU 바이트 디코드와 픽스처 파서"
```

---

### Task 3: protocol 인코드와 핸드셰이크 응답

**Files:**
- Modify: `src/logic_mcp/mcu/protocol.py` (끝에 추가)
- Test: `tests/test_protocol.py` (끝에 추가)

**Interfaces:**
- Produces:
  - `handshake_reply(ev: Event) -> bytes | None`
  - `button_down(note) -> bytes`, `button_up(note) -> bytes`
  - `fader_move(channel: int, value: int) -> list[bytes]` (터치 ON, 피치벤드, 터치 OFF)
  - `vpot_turn(channel: int, steps: int) -> bytes` (steps는 -63..63, 0 금지)
  - `MAX_FADER = 16383`

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_protocol.py` 끝에:
```python
def test_handshake_reply_only_for_0x14():
    reply = P.handshake_reply(P.DeviceQuery(device=0x14))
    assert reply == bytes.fromhex("F0 00 00 66 14 01 4C 47 43 4D 43 50 31 01 02 03 04 F7")
    assert P.handshake_reply(P.DeviceQuery(device=0x15)) is None
    assert P.handshake_reply(P.DeviceQuery(device=0x10)) is None
    assert P.handshake_reply(P.VersionRequest(device=0x14)) == bytes.fromhex("F0 00 00 66 14 14 56 31 2E 30 30 F7")
    assert P.handshake_reply(P.VersionRequest(device=0x11)) is None
    assert P.handshake_reply(P.Led(note=1, on=True)) is None


def test_handshake_reply_matches_fixture_tx():
    rows = P.load_fixture(FIXTURE)
    pairs = [(rows[i][2], rows[i + 1][2]) for i in range(len(rows) - 1)
             if rows[i][1] == "RX" and rows[i + 1][1] == "TX"]
    checked = 0
    for rx, tx in pairs:
        ev = P.decode(rx)
        if isinstance(ev, (P.DeviceQuery, P.VersionRequest)) and ev.device == 0x14:
            assert P.handshake_reply(ev) == tx
            checked += 1
    assert checked >= 2


def test_button_and_fader_and_vpot_encoders():
    assert P.button_down(P.Note.PLAY) == bytes([0x90, 0x5E, 0x7F])
    assert P.button_up(P.Note.PLAY) == bytes([0x90, 0x5E, 0x00])
    assert P.fader_move(0, 10000) == [bytes([0x90, 0x68, 0x7F]), bytes([0xE0, 0x10, 0x4E]), bytes([0x90, 0x68, 0x00])]
    assert P.fader_move(7, 0)[1] == bytes([0xE7, 0x00, 0x00])
    assert P.vpot_turn(0, 5) == bytes([0xB0, 0x10, 0x05])
    assert P.vpot_turn(0, -5) == bytes([0xB0, 0x10, 0x45])
    assert P.vpot_turn(3, 63) == bytes([0xB0, 0x13, 0x3F])
    assert P.vpot_turn(3, 99) == bytes([0xB0, 0x13, 0x3F])
    with pytest.raises(ValueError):
        P.vpot_turn(0, 0)
    with pytest.raises(ValueError):
        P.fader_move(0, 16384)
    with pytest.raises(ValueError):
        P.fader_move(9, 0)
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_protocol.py -q`
Expected: 3 FAIL, `AttributeError: module ... has no attribute 'handshake_reply'`

- [ ] **Step 3: 인코더 구현**

`src/logic_mcp/mcu/protocol.py` 끝에 추가:
```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_protocol.py -q`
Expected: `11 passed`

- [ ] **Step 5: 커밋**

```bash
git add src/logic_mcp/mcu/protocol.py tests/test_protocol.py
git commit -m "feat(mcu): 핸드셰이크 응답과 버튼·페이더·V-Pot 인코더"
```

---

### Task 4: state 리듀서 — 스트립, LED, 페이더, 링, 미터

**Files:**
- Create: `src/logic_mcp/mcu/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: Task 2의 이벤트 타입, `LCD_WIDTH`, `Note`.
- Produces:
  - dataclass `Strip(number, name, rec, solo, mute, select, fader_raw, pan_ring: tuple[int,int,bool], meter, value_text)`
  - `Transport(play, stop, record, cycle, rewind, ffwd)`
  - `TimeDisplay(digits: str, dots: tuple[bool,...], mode: str)` + `.text` + `.parsed()`
  - `Assignment(mode: str | None, display: str, flip: bool)`
  - `Connection(state, last_rx, dirty_until, last_display_change, stale)`
  - `SurfaceState(strips, master_fader, transport, time, assignment, lcd: tuple[str, str], leds_on: frozenset[int], connection)`
  - `initial_state() -> SurfaceState`, `reduce(state, event, now) -> SurfaceState`, `parse_column(col: str) -> tuple[int | None, str]`
  - 상수 `SETTLE_S = 0.12`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_state.py`:
```python
from pathlib import Path

from logic_mcp.mcu import protocol as P
from logic_mcp.mcu import state as S

FIXTURE = Path(__file__).parent / "fixtures" / "mcu" / "cap_raw6.log"


def replay(until: float, start: float = 0.0) -> S.SurfaceState:
    st = S.initial_state()
    for ts, direction, data in P.load_fixture(FIXTURE):
        if ts < start or direction != "RX":
            continue
        if ts > until:
            break
        st = S.tick(st, ts)
        st = S.reduce(st, P.decode(data), ts)
    return S.tick(st, until)


def test_parse_column():
    assert S.parse_column("1:1    ") == (1, "1")
    assert S.parse_column("2:StOu ") == (2, "StOu")
    assert S.parse_column("12:Aud ") == (12, "Aud")
    assert S.parse_column("St Out ") == (None, "St Out")
    assert S.parse_column("       ") == (None, "")


def test_lcd_write_updates_rows_and_strips():
    st = S.initial_state()
    st = S.reduce(st, P.LcdWrite(offset=0, text=b"1:1    2:StOu 5:Mast "), 10.0)
    st = S.reduce(st, P.LcdWrite(offset=56, text=b"+0.0 dB-5.8 dB"), 10.1)
    assert st.lcd[0].startswith("1:1    2:StOu 5:Mast")
    assert st.strips[0].number == 1 and st.strips[0].name == "1"
    assert st.strips[1].number == 2 and st.strips[1].name == "StOu"
    assert st.strips[2].number == 5
    assert st.strips[3].number is None and st.strips[3].name == ""
    assert st.strips[0].value_text == "+0.0 dB"
    assert st.strips[1].value_text == "-5.8 dB"
    assert st.connection.dirty_until == 10.1 + S.SETTLE_S
    assert st.connection.last_rx == 10.1


def test_led_maps_to_strips_transport_assignment():
    st = S.initial_state()
    st = S.reduce(st, P.Led(note=P.Note.MUTE + 2, on=True), 1.0)
    st = S.reduce(st, P.Led(note=P.Note.SOLO + 7, on=True), 1.0)
    st = S.reduce(st, P.Led(note=P.Note.REC + 0, on=True), 1.0)
    st = S.reduce(st, P.Led(note=P.Note.SELECT + 1, on=True), 1.0)
    st = S.reduce(st, P.Led(note=P.Note.PLAY, on=True), 1.0)
    st = S.reduce(st, P.Led(note=P.Note.STOP, on=False), 1.0)
    st = S.reduce(st, P.Led(note=P.Note.PAN, on=True), 1.0)
    st = S.reduce(st, P.Led(note=P.Note.FLIP, on=True), 1.0)
    st = S.reduce(st, P.Led(note=P.Note.BEATS_LED, on=True), 1.0)
    assert st.strips[2].mute and st.strips[7].solo and st.strips[0].rec and st.strips[1].select
    assert st.transport.play and not st.transport.stop
    assert st.assignment.mode == "pan" and st.assignment.flip
    assert st.time.mode == "beats"
    assert {P.Note.MUTE + 2, P.Note.PLAY, P.Note.PAN} <= st.leds_on
    st = S.reduce(st, P.Led(note=P.Note.PAN, on=False), 1.1)
    st = S.reduce(st, P.Led(note=P.Note.EQ, on=True), 1.1)
    assert st.assignment.mode == "eq"
    st = S.reduce(st, P.Led(note=P.Note.MUTE + 2, on=False), 1.2)
    assert not st.strips[2].mute and P.Note.MUTE + 2 not in st.leds_on


def test_fader_ring_meter():
    st = S.initial_state()
    st = S.reduce(st, P.FaderPos(channel=0, value=9990), 1.0)
    st = S.reduce(st, P.FaderPos(channel=8, value=12443), 1.0)
    st = S.reduce(st, P.VpotRing(channel=0, mode=1, pos=6, center=True), 1.0)
    st = S.reduce(st, P.Meter(channel=3, level=9), 1.0)
    assert st.strips[0].fader_raw == 9990
    assert st.master_fader == 12443
    assert st.strips[0].pan_ring == (1, 6, True)
    assert st.strips[3].meter == 9
    assert st.connection.last_display_change == 1.0  # 링은 표시 변화로 센다


def test_fixture_mute_feedback():
    st = replay(754.3)
    assert st.strips[0].mute is True
    assert st.lcd[1].startswith("Muted")
    st = replay(755.0)
    assert st.strips[0].mute is False


def test_fixture_numbers_and_values():
    st = replay(4563.6)
    assert [s.number for s in st.strips[:3]] == [1, 2, 5]
    assert st.strips[1].name == "StOu"
    st = replay(4570.6)
    assert st.strips[0].fader_raw == 9990
    assert st.strips[0].value_text == "-5.8 dB"
    st = replay(4631.0)
    assert st.strips[0].value_text == "+5"
    assert st.strips[0].pan_ring == (1, 6, False)
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_state.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'logic_mcp.mcu.state'`

- [ ] **Step 3: state.py 구현(이 태스크 범위: tick은 시간만 갱신하는 최소 버전)**

`src/logic_mcp/mcu/state.py`:
```python
"""이벤트 스트림 → SurfaceState 순수 리듀서. I/O·스레드 없음."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from . import protocol as P

SETTLE_S = 0.12          # 조각난 LCD·타임 디스플레이가 잠잠해졌다고 보는 시간
READY_QUIET_S = 1.0      # 설치 애니메이션이 끝났다고 보는 조용한 시간
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
            st = replace(st, connection=replace(st.connection, state="handshake"))
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
        return replace(st, strips=_set_strip(st.strips, ev.channel, fader_raw=ev.value))

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
    """시간 경과만으로 일어나는 전이. Task 5에서 완성."""
    return state
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_state.py -q`
Expected: `6 passed`

- [ ] **Step 5: 커밋**

```bash
git add src/logic_mcp/mcu/state.py tests/test_state.py
git commit -m "feat(mcu): SurfaceState 리듀서 — 스트립, LED, 페이더, 링, 미터"
```

---

### Task 5: state — 타임 디스플레이 파싱과 연결 상태 머신

**Files:**
- Modify: `src/logic_mcp/mcu/state.py` (`tick` 완성)
- Test: `tests/test_state.py` (끝에 추가)

**Interfaces:**
- Produces: `tick(state, now)` 완성 — `handshake`/`animating`에서 표시 변화가 `READY_QUIET_S` 동안 없으면 `ready`; 어느 상태에서든 `STALE_S` 동안 무수신이고 재생 중이 아니면 `stale=True`.

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_state.py` 끝에:
```python
def test_time_display_parse_from_fixture():
    st = replay(755.7)
    assert st.transport.play is True and st.transport.stop is False
    assert st.time.mode == "beats"
    parsed = st.time.parsed()
    assert parsed is not None and parsed["bars"] == 1
    st = replay(757.2)
    assert st.transport.stop is True and st.transport.play is False
    assert st.time.parsed() == {"bars": 1, "beats": 4, "division": 1, "ticks": 66}


def test_connection_rebind_without_handshake_becomes_ready():
    # 픽스처 시작(183s)은 핸드셰이크 없이 LCD부터 온다(이름으로 재바인딩)
    st = replay(184.5)
    assert st.connection.state in ("animating", "ready")
    st = replay(200.0)
    assert st.connection.state == "ready"


def test_connection_handshake_animating_ready_from_fixture():
    st = replay(665.401)
    assert st.connection.state == "handshake"
    st = replay(666.5)  # 첫 LCD 쓰기는 666.122초
    assert st.connection.state == "animating"
    st = replay(719.5)
    assert st.connection.state == "ready"
    st = replay(754.3)
    assert st.connection.state == "ready" and st.strips[0].mute


def test_stale_flag():
    st = S.initial_state()
    st = S.reduce(st, P.LcdWrite(offset=0, text=b"1:1"), 100.0)
    st = S.tick(st, 101.5)
    assert st.connection.state == "ready" and not st.connection.stale
    st = S.tick(st, 131.0)
    assert st.connection.stale is True
    st = S.reduce(st, P.Led(note=P.Note.PLAY, on=True), 131.0)
    st = S.tick(st, 170.0)
    assert st.connection.stale is False  # 재생 중엔 stale 아님
    st = S.reduce(st, P.Led(note=P.Note.PLAY, on=False), 170.0)
    st = S.tick(st, 201.0)
    assert st.connection.stale is True
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_state.py -q`
Expected: 3~4 FAIL (`state == 'ready'` 불일치, stale 불일치)

- [ ] **Step 3: tick 구현**

`src/logic_mcp/mcu/state.py`의 `tick`을 교체:
```python
def tick(state: SurfaceState, now: float) -> SurfaceState:
    conn = state.connection
    if conn.state in ("handshake", "animating") and conn.last_display_change > 0 \
            and now - conn.last_display_change >= READY_QUIET_S:
        conn = replace(conn, state="ready")
    stale = conn.state != "no_logic" and not state.transport.play and now - conn.last_rx >= STALE_S
    if stale != conn.stale:
        conn = replace(conn, stale=stale)
    return state if conn is state.connection else replace(state, connection=conn)
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_state.py -q`
Expected: `10 passed`. 실패하면 픽스처의 해당 구간 타임스탬프를 `awk '$1>=719 && $1<=720' tests/fixtures/mcu/cap_raw6.log`로 보고 임계값이 아니라 테스트 시각을 조정한다(애니메이션은 717.1초에 끝났다).

- [ ] **Step 5: 커밋**

```bash
git add src/logic_mcp/mcu/state.py tests/test_state.py
git commit -m "feat(mcu): 타임 디스플레이 파싱과 연결 상태 머신"
```

---

### Task 6: transport와 Surface

**Files:**
- Create: `src/logic_mcp/mcu/transport.py`, `src/logic_mcp/mcu/surface.py`, `tests/fakes.py`
- Test: `tests/test_surface.py`

**Interfaces:**
- Produces:
  - `class Transport(Protocol)`: 속성 `on_message: Callable[[float, bytes], None]`, `open()`, `close()`, `send(data: bytes)`
  - `class RtMidiTransport(port_name: str = "LogicMCP", clock=time.monotonic)`
  - `class Surface(transport, clock=time.monotonic, tick_interval=0.1)`: `.state`, `start()`, `stop()`, `send(data)`, `handle_message(ts, data)`, `tick()`, `wait_for(pred, timeout) -> bool`, `wait_settled(timeout=1.0) -> bool`
  - 테스트용 `FakeTransport`(`sent`, `replies`, `feed`, `now`), `make_surface() -> tuple[Surface, FakeTransport]`

- [ ] **Step 1: 실패하는 테스트와 가짜 작성**

`tests/fakes.py`:
```python
from __future__ import annotations

from collections.abc import Callable

from logic_mcp.mcu.surface import Surface


class FakeTransport:
    """send()에 대한 응답을 동기적으로 되돌려 주는 가짜 포트."""

    def __init__(self) -> None:
        self.on_message: Callable[[float, bytes], None] = lambda ts, data: None
        self.sent: list[bytes] = []
        self.replies: Callable[[bytes], list[bytes]] = lambda data: []
        self.now = 1000.0
        self.opened = False
        self.closed = False

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.closed = True

    def send(self, data: bytes) -> None:
        self.sent.append(data)
        for reply in self.replies(data):
            self.on_message(self.now, reply)

    def feed(self, data: bytes) -> None:
        self.on_message(self.now, data)


def make_surface() -> tuple[Surface, FakeTransport]:
    fake = FakeTransport()
    surface = Surface(fake, clock=lambda: fake.now + 1.0, tick_interval=0.01)
    return surface, fake
```

`tests/test_surface.py`:
```python
import sys

import pytest

from logic_mcp.mcu import protocol as P
from tests.fakes import make_surface


def test_handshake_reply_is_sent_and_state_updates():
    surface, fake = make_surface()
    fake.feed(bytes.fromhex("F0 00 00 66 14 00 F7"))
    assert fake.sent == [P.handshake_reply(P.DeviceQuery(device=0x14))]
    assert surface.state.connection.state == "handshake"
    fake.feed(bytes.fromhex("F0 00 00 66 15 00 F7"))
    assert len(fake.sent) == 1


def test_wait_for_returns_true_when_reply_arrives_during_send():
    surface, fake = make_surface()
    fake.replies = lambda data: [P.button_down(P.Note.MUTE)] if data == P.button_down(P.Note.MUTE) else []
    surface.send(P.button_down(P.Note.MUTE))
    assert surface.wait_for(lambda s: s.strips[0].mute, timeout=0.2) is True


def test_wait_for_times_out():
    surface, fake = make_surface()
    assert surface.wait_for(lambda s: s.strips[0].mute, timeout=0.05) is False


def test_wait_settled_uses_clock():
    surface, fake = make_surface()
    fake.feed(bytes.fromhex("F0 00 00 66 14 12 00 41 F7"))
    # clock = fake.now + 1.0 이므로 dirty_until(now+0.12)을 이미 지났다
    assert surface.wait_settled(timeout=0.1) is True


def test_tick_promotes_to_ready():
    surface, fake = make_surface()
    fake.feed(bytes.fromhex("F0 00 00 66 14 12 00 41 F7"))
    assert surface.state.connection.state == "animating"
    surface.tick()
    assert surface.state.connection.state == "ready"


def test_start_stop_opens_and_closes_transport():
    surface, fake = make_surface()
    surface.start()
    assert fake.opened
    surface.stop()
    assert fake.closed


@pytest.mark.skipif(sys.platform != "darwin", reason="CoreMIDI 가상 포트")
def test_rtmidi_virtual_port_opens_and_closes():
    from logic_mcp.mcu.transport import RtMidiTransport
    t = RtMidiTransport(port_name="LogicMCP-test")
    t.open()
    t.send(bytes([0x90, 0x5E, 0x00]))
    t.close()
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_surface.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'logic_mcp.mcu.surface'`

- [ ] **Step 3: transport.py 구현**

`src/logic_mcp/mcu/transport.py`:
```python
"""CoreMIDI 가상 포트. 수신 콜백은 CoreMIDI 스레드에서 불리므로 on_message로 넘기기만 한다."""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

PORT_NAME = "LogicMCP"


class Transport(Protocol):
    on_message: Callable[[float, bytes], None]

    def open(self) -> None: ...
    def close(self) -> None: ...
    def send(self, data: bytes) -> None: ...


class RtMidiTransport:
    def __init__(self, port_name: str = PORT_NAME, clock: Callable[[], float] = time.monotonic) -> None:
        self.port_name = port_name
        self.on_message: Callable[[float, bytes], None] = lambda ts, data: None
        self._clock = clock
        self._in = None
        self._out = None

    def open(self) -> None:
        import rtmidi  # 지연 임포트: 테스트 환경에서 모듈 로드만으로 CoreMIDI를 건드리지 않게

        self._out = rtmidi.MidiOut()
        self._out.open_virtual_port(self.port_name)
        self._in = rtmidi.MidiIn()
        self._in.open_virtual_port(self.port_name)
        self._in.ignore_types(sysex=False, timing=True, active_sense=True)
        self._in.set_callback(self._callback)

    def _callback(self, event, _data=None) -> None:
        message, _delta = event
        self.on_message(self._clock(), bytes(message))

    def send(self, data: bytes) -> None:
        if self._out is None:
            raise RuntimeError("port not open")
        self._out.send_message(list(data))

    def close(self) -> None:
        # 가상 포트는 close_port로 닫히지 않고 인스턴스를 지워야 사라진다(python-rtmidi 문서)
        for port in (self._in, self._out):
            if port is not None:
                port.close_port()
                port.delete()
        self._in = self._out = None
```

- [ ] **Step 4: surface.py 구현**

`src/logic_mcp/mcu/surface.py`:
```python
"""트랜스포트 + 상태 + 락 + 대기. 명령 계층은 이 클래스만 본다."""
from __future__ import annotations

import threading
import time
from collections.abc import Callable

from . import protocol as P
from . import state as S
from .transport import Transport


class Surface:
    def __init__(self, transport: Transport, clock: Callable[[], float] = time.monotonic,
                 tick_interval: float = 0.1) -> None:
        self._t = transport
        self._t.on_message = self.handle_message
        self._clock = clock
        self._tick_interval = tick_interval
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._state = S.initial_state()
        self._stop = threading.Event()
        self._ticker: threading.Thread | None = None

    @property
    def state(self) -> S.SurfaceState:
        with self._lock:
            return self._state

    @property
    def clock(self) -> Callable[[], float]:
        return self._clock

    def start(self) -> None:
        self._t.open()
        self._stop.clear()
        self._ticker = threading.Thread(target=self._tick_loop, name="surface-tick", daemon=True)
        self._ticker.start()

    def stop(self) -> None:
        self._stop.set()
        if self._ticker is not None:
            self._ticker.join(timeout=1.0)
        self._t.close()

    def _tick_loop(self) -> None:
        while not self._stop.wait(self._tick_interval):
            self.tick()

    def tick(self) -> None:
        with self._cond:
            self._state = S.tick(self._state, self._clock())
            self._cond.notify_all()

    def handle_message(self, ts: float, data: bytes) -> None:
        ev = P.decode(data)
        reply = P.handshake_reply(ev)
        if reply is not None:
            self._t.send(reply)
        with self._cond:
            self._state = S.reduce(self._state, ev, ts)
            self._cond.notify_all()

    def send(self, data: bytes) -> None:
        self._t.send(data)

    def wait_for(self, pred: Callable[[S.SurfaceState], bool], timeout: float) -> bool:
        with self._cond:
            return self._cond.wait_for(lambda: pred(self._state), timeout=timeout)

    def wait_settled(self, timeout: float = 1.0) -> bool:
        return self.wait_for(lambda s: self._clock() >= s.connection.dirty_until, timeout)
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/test_surface.py -q`
Expected: `7 passed` (rtmidi 테스트 포함). `wait_for` 타임아웃 테스트는 ticker가 없어도 `Condition.wait_for`의 timeout으로 끝난다.

- [ ] **Step 6: 커밋**

```bash
git add src/logic_mcp/mcu/transport.py src/logic_mcp/mcu/surface.py tests/fakes.py tests/test_surface.py
git commit -m "feat(mcu): rtmidi 트랜스포트와 Surface(상태·락·대기)"
```

---

### Task 7: 페이더 dB 표와 값 텍스트 파서

**Files:**
- Create: `src/logic_mcp/logic/faders.py`, `src/logic_mcp/logic/fader_db.json`
- Test: `tests/test_faders.py`

**Interfaces:**
- Produces:
  - `MAX_RAW = 14845`, `ZERO_DB_RAW = 12443`, `MAX_DB = 6.0`
  - `class FaderTable`: `FaderTable.load(path: Path | None = None)`, `.db_to_raw(db: float) -> int`, `.raw_to_db(raw: int) -> float` (0 → `-inf`)
  - `parse_db_text(text: str) -> float | None` (`"+0.0 dB"` → 0.0, `"-oo dB"` → `-inf`, 그 외 None)
  - `parse_pan_text(text: str) -> int | None` (`"+5"` → 5, `"0"` → 0, `"-12"` → -12, 그 외 None)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_faders.py`:
```python
import math

import pytest

from logic_mcp.logic import faders as F


def test_spot_points():
    t = F.FaderTable.load()
    assert t.db_to_raw(0.0) == 12443
    assert t.db_to_raw(-5.8) == 9990
    assert t.db_to_raw(6.0) == 14845
    assert t.db_to_raw(math.inf * -1) == 0
    assert t.raw_to_db(12443) == pytest.approx(0.0)
    assert t.raw_to_db(0) == -math.inf


def test_clamp_and_monotonic():
    t = F.FaderTable.load()
    assert t.db_to_raw(20.0) == F.MAX_RAW
    assert t.db_to_raw(-200.0) == 0
    prev = -1
    for db10 in range(-600, 61):
        raw = t.db_to_raw(db10 / 10)
        assert raw >= prev
        prev = raw
    with pytest.raises(ValueError):
        t.db_to_raw(math.nan)


def test_interpolation_between_points():
    t = F.FaderTable.load()
    mid = t.db_to_raw(-2.9)
    assert 9990 < mid < 12443


def test_parse_db_text():
    assert F.parse_db_text("+0.0 dB") == 0.0
    assert F.parse_db_text("-5.8 dB") == -5.8
    assert F.parse_db_text("-oo dB") == -math.inf
    assert F.parse_db_text("-10.5dB") == -10.5
    assert F.parse_db_text("Muted") is None
    assert F.parse_db_text("") is None


def test_parse_pan_text():
    assert F.parse_pan_text("+5") == 5
    assert F.parse_pan_text("0") == 0
    assert F.parse_pan_text("-12") == -12
    assert F.parse_pan_text("-") is None
    assert F.parse_pan_text("+0.0 dB") is None
    assert F.parse_pan_text("") is None
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_faders.py -q`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: 임시 표와 faders.py 구현**

`src/logic_mcp/logic/fader_db.json` (실측 4점. Task 12 캘리브레이션이 64 간격 표로 교체한다):
```json
{
  "source": "provisional: spike 2026-10-14, replace with scripts/calibrate_fader.py output",
  "points": [[0, null], [9990, -5.8], [12443, 0.0], [14845, 6.0]]
}
```

`src/logic_mcp/logic/faders.py`:
```python
"""Logic 페이더 14비트 값 ↔ dB. 표는 실측(캘리브레이션)으로 만든다."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

MAX_RAW = 14845      # +6.0 dB. Logic은 이 위를 클램프한다
ZERO_DB_RAW = 12443
MAX_DB = 6.0
_MIN_FINITE_DB = -72.0   # -inf 아래 구간 보간용 가짜 바닥. 캘리브레이션 표가 들어오면 영향 없음
_DB_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?|-oo)\s*dB\s*$")
_PAN_RE = re.compile(r"^\s*([+-]?\d+)\s*$")


@dataclass(frozen=True)
class FaderTable:
    points: tuple[tuple[int, float], ...]  # (raw, db) 오름차순, db는 -inf 가능

    @classmethod
    def load(cls, path: Path | None = None) -> "FaderTable":
        p = path or Path(__file__).with_name("fader_db.json")
        data = json.loads(p.read_text())
        pts = [(int(r), -math.inf if d is None else float(d)) for r, d in data["points"]]
        pts.sort()
        return cls(points=tuple(pts))

    def db_to_raw(self, db: float) -> int:
        if math.isnan(db):
            raise ValueError("db is NaN")
        if db == -math.inf:
            return 0
        if db >= MAX_DB:
            return MAX_RAW
        pts = [(r, (_MIN_FINITE_DB if d == -math.inf else d)) for r, d in self.points]
        if db <= pts[0][1]:
            return pts[0][0]
        for (r0, d0), (r1, d1) in zip(pts, pts[1:]):
            if d0 <= db <= d1:
                if d1 == d0:
                    return r0
                return round(r0 + (r1 - r0) * (db - d0) / (d1 - d0))
        return pts[-1][0]

    def raw_to_db(self, raw: int) -> float:
        if raw <= 0:
            return -math.inf
        pts = [(r, (_MIN_FINITE_DB if d == -math.inf else d)) for r, d in self.points]
        if raw >= pts[-1][0]:
            return pts[-1][1]
        for (r0, d0), (r1, d1) in zip(pts, pts[1:]):
            if r0 <= raw <= r1:
                if r1 == r0:
                    return d0
                return round(d0 + (d1 - d0) * (raw - r0) / (r1 - r0), 1)
        return pts[0][1]


def parse_db_text(text: str) -> float | None:
    m = _DB_RE.match(text)
    if not m:
        return None
    return -math.inf if m.group(1) == "-oo" else float(m.group(1))


def parse_pan_text(text: str) -> int | None:
    m = _PAN_RE.match(text)
    return int(m.group(1)) if m else None
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_faders.py -q`
Expected: `5 passed`

- [ ] **Step 5: 커밋**

```bash
git add src/logic_mcp/logic/faders.py src/logic_mcp/logic/fader_db.json tests/test_faders.py
git commit -m "feat(logic): 페이더 dB 표(임시)와 LCD 값 텍스트 파서"
```

---

### Task 8: Commands — 결과 모델, 주소 해석, LED 상태 명령

**Files:**
- Create: `src/logic_mcp/logic/commands.py`
- Test: `tests/test_commands.py`

**Interfaces:**
- Consumes: `Surface`, `FaderTable`, `protocol`, `state`.
- Produces:
  - `class ToolResult(BaseModel)`: `ok: bool`, `verified: Literal["verified","unverified","timeout","skipped"]`, `action: str`, `target: dict | None`, `before: dict | None`, `after: dict | None`, `elapsed_ms: int`, `note: str`
  - `class Commands(surface: Surface, faders: FaderTable, sleep=time.sleep, logic_running=<pgrep>)`:
    - `status() -> dict`
    - `track(action: str, strip: int | None = None, number: int | None = None) -> ToolResult`
    - 내부: `_resolve(strip, number, action) -> int | ToolResult`, `_press(note)`, `_set_led(action, note, want_on, target) -> ToolResult`, `_strip_view(ch) -> dict`, `_require_ready(action) -> ToolResult | None`, `_result(...)`
  - 상수 `LED_TIMEOUT = 0.5`, `FADER_TIMEOUT = 0.8`, `PAN_TIMEOUT = 0.5`, `BANK_TIMEOUT = 1.0`, `PRESS_HOLD_S = 0.03`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_commands.py`:
```python
from logic_mcp.logic.commands import Commands, ToolResult
from logic_mcp.logic.faders import FaderTable
from logic_mcp.mcu import protocol as P
from tests.fakes import make_surface

LCD_NUMBERED = bytes.fromhex("F0 00 00 66 14 12 00") + b"1:1    2:StOu 5:Mast                                    " + b"\xF7"


def make_commands(ready: bool = True):
    surface, fake = make_surface()
    cmds = Commands(surface, FaderTable.load(), sleep=lambda s: None, logic_running=lambda: True)
    if ready:
        fake.feed(LCD_NUMBERED)
        fake.feed(P.button_down(P.Note.PAN))      # PAN 모드 LED
        fake.feed(P.button_down(P.Note.BEATS_LED))
        surface.tick()
        assert surface.state.connection.state == "ready"
    return cmds, surface, fake


def echo_led(fake):
    """버튼 down을 받으면 같은 노트의 LED를 켜고, 이미 켜져 있으면 끄는 Logic 흉내."""
    lit: set[int] = set()

    def replies(data: bytes) -> list[bytes]:
        if len(data) == 3 and data[0] == 0x90 and data[2] == 0x7F:
            n = data[1]
            if n in lit:
                lit.discard(n)
                return [P.button_up(n)]
            lit.add(n)
            return [P.button_down(n)]
        return []
    fake.replies = replies
    return lit


def test_not_ready_refuses_without_sending():
    cmds, surface, fake = make_commands(ready=False)
    r = cmds.track("mute", strip=1)
    assert r.ok is False and fake.sent == []
    assert "wait_ready" in r.note


def test_address_validation():
    cmds, surface, fake = make_commands()
    assert cmds.track("mute").ok is False
    assert cmds.track("mute", strip=1, number=1).ok is False
    assert cmds.track("mute", strip=9).ok is False
    assert cmds.track("mute", strip=0).ok is False
    assert fake.sent == []
    r = cmds.track("mute", number=99)
    assert r.ok is False and "99" in r.note


def test_number_without_prefix_refused():
    cmds, surface, fake = make_commands(ready=False)
    fake.feed(bytes.fromhex("F0 00 00 66 14 12 00") + b"Audio 1St Out Master " + b"\xF7")
    surface.tick()
    r = cmds.track("mute", number=1)
    assert r.ok is False and "configure" in r.note and fake.sent == []


def test_mute_verified_then_skipped_then_unmute():
    cmds, surface, fake = make_commands()
    echo_led(fake)
    r = cmds.track("mute", strip=1)
    assert isinstance(r, ToolResult)
    assert r.ok and r.verified == "verified"
    assert r.target == {"strip": 1, "number": 1, "name": "1"}
    assert r.before["mute"] is False and r.after["mute"] is True
    assert fake.sent == [P.button_down(P.Note.MUTE), P.button_up(P.Note.MUTE)]
    r2 = cmds.track("mute", strip=1)
    assert r2.ok and r2.verified == "skipped" and len(fake.sent) == 2
    r3 = cmds.track("unmute", number=1)
    assert r3.ok and r3.verified == "verified" and r3.after["mute"] is False


def test_solo_arm_select_use_right_notes():
    cmds, surface, fake = make_commands()
    echo_led(fake)
    assert cmds.track("solo", strip=3).after["solo"] is True
    assert fake.sent[0] == P.button_down(P.Note.SOLO + 2)
    assert cmds.track("arm", strip=8).after["rec"] is True
    assert fake.sent[2] == P.button_down(P.Note.REC + 7)
    assert cmds.track("select", strip=2).after["select"] is True
    assert fake.sent[4] == P.button_down(P.Note.SELECT + 1)


def test_timeout_when_no_feedback():
    cmds, surface, fake = make_commands()
    r = cmds.track("mute", strip=1)
    assert r.ok is False and r.verified == "timeout"
    assert r.elapsed_ms >= 0


def test_status_fields():
    cmds, surface, fake = make_commands()
    s = cmds.status()
    assert s["state"] == "ready" and s["name_format_ok"] is True
    assert s["assignment_mode"] == "pan" and s["logic_running"] is True
    assert s["visible_numbers"] == [1, 2, 5]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_commands.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'logic_mcp.logic.commands'`

- [ ] **Step 3: commands.py 구현(이 태스크 범위)**

`src/logic_mcp/logic/commands.py`:
```python
"""보내고 → 기대 피드백을 기다리고 → 판정. 모든 툴은 여기로 온다."""
from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from ..mcu import protocol as P
from ..mcu import state as S
from ..mcu.surface import Surface
from .faders import FaderTable, parse_db_text, parse_pan_text

LED_TIMEOUT = 0.5
FADER_TIMEOUT = 0.8
PAN_TIMEOUT = 0.5
BANK_TIMEOUT = 1.0
PRESS_HOLD_S = 0.03
Verified = Literal["verified", "unverified", "timeout", "skipped"]


class ToolResult(BaseModel):
    ok: bool
    verified: Verified
    action: str
    target: dict | None = None
    before: dict | None = None
    after: dict | None = None
    elapsed_ms: int = 0
    note: str = ""


def _logic_running() -> bool:
    return subprocess.run(["pgrep", "-x", "Logic Pro"], capture_output=True).returncode == 0


_TRACK_ACTIONS: dict[str, tuple[str, int, bool]] = {
    "mute": ("mute", P.Note.MUTE, True), "unmute": ("mute", P.Note.MUTE, False),
    "solo": ("solo", P.Note.SOLO, True), "unsolo": ("solo", P.Note.SOLO, False),
    "arm": ("rec", P.Note.REC, True), "disarm": ("rec", P.Note.REC, False),
    "select": ("select", P.Note.SELECT, True),
}


class Commands:
    def __init__(self, surface: Surface, faders: FaderTable,
                 sleep: Callable[[float], None] = time.sleep,
                 logic_running: Callable[[], bool] = _logic_running) -> None:
        self.surface = surface
        self.faders = faders
        self._sleep = sleep
        self._logic_running = logic_running
        self._lock = threading.Lock()
        self.configured = False

    # ---------- 공통 ----------
    def _now_ms(self) -> int:
        return int(self.surface.clock() * 1000)

    def _result(self, action: str, ok: bool, verified: Verified, t0: int, *, target=None,
                before=None, after=None, note: str = "") -> ToolResult:
        return ToolResult(ok=ok, verified=verified, action=action, target=target, before=before,
                          after=after, elapsed_ms=max(0, self._now_ms() - t0), note=note)

    def _require_ready(self, action: str, t0: int) -> ToolResult | None:
        st = self.surface.state.connection.state
        if st == "ready":
            return None
        return self._result(action, False, "skipped", t0,
                            note=f"상태가 {st}. `logic_session wait_ready` 후 다시 시도")

    def _strip_view(self, ch: int) -> dict:
        s = self.surface.state.strips[ch]
        return {"strip": ch + 1, "number": s.number, "name": s.name, "rec": s.rec, "solo": s.solo,
                "mute": s.mute, "select": s.select, "fader_raw": s.fader_raw,
                "fader_db": self.faders.raw_to_db(s.fader_raw), "pan_ring": list(s.pan_ring),
                "meter": s.meter, "value_text": s.value_text}

    def _target(self, ch: int) -> dict:
        s = self.surface.state.strips[ch]
        return {"strip": ch + 1, "number": s.number, "name": s.name}

    def _press(self, note: int) -> None:
        self.surface.send(P.button_down(note))
        self._sleep(PRESS_HOLD_S)
        self.surface.send(P.button_up(note))

    def _resolve(self, strip: int | None, number: int | None, action: str, t0: int) -> int | ToolResult:
        if (strip is None) == (number is None):
            return self._result(action, False, "skipped", t0, note="strip(1-8)과 number 중 하나만 지정")
        if strip is not None:
            if not 1 <= strip <= 8:
                return self._result(action, False, "skipped", t0, note=f"strip {strip}은 1-8 밖. 다른 뱅크는 number로 지정")
            return strip - 1
        numbers = [s.number for s in self.surface.state.strips]
        if all(n is None for n in numbers):
            return self._result(action, False, "skipped", t0,
                                note="LCD에 번호 접두사가 없음. `logic_session configure`를 먼저 실행")
        if number in numbers:
            return numbers.index(number)
        shown = self._show_number(number, t0)
        if shown is not None:
            return shown
        visible = [n for n in numbers if n is not None]
        return self._result(action, False, "skipped", t0, note=f"번호 {number} 없음. 보이는 번호: {visible}")

    def _show_number(self, number: int, t0: int) -> int | None:
        """Task 10에서 뱅크 이동으로 구현. 지금은 현재 뱅크만 본다."""
        numbers = [s.number for s in self.surface.state.strips]
        return numbers.index(number) if number in numbers else None

    def _set_led(self, action: str, note: int, want_on: bool, target: dict, before: dict,
                 after_fn: Callable[[], dict], t0: int) -> ToolResult:
        if (note in self.surface.state.leds_on) == want_on:
            return self._result(action, True, "skipped", t0, target=target, before=before,
                                after=after_fn(), note="already")
        self._press(note)
        ok = self.surface.wait_for(lambda s: (note in s.leds_on) == want_on, LED_TIMEOUT)
        self.surface.wait_settled(0.3)
        after = after_fn()
        if ok:
            return self._result(action, True, "verified", t0, target=target, before=before, after=after)
        changed = self.surface.state.connection.last_rx * 1000 > t0
        return self._result(action, False, "unverified" if changed else "timeout", t0, target=target,
                            before=before, after=after,
                            note="LED 피드백이 기대와 다름" if changed else "피드백 없음(제한 시간 초과)")

    # ---------- 툴 ----------
    def status(self) -> dict:
        st = self.surface.state
        c = st.connection
        now = self.surface.clock()
        return {
            "state": c.state, "stale": c.stale, "port": "LogicMCP",
            "last_rx_age_ms": int((now - c.last_rx) * 1000) if c.last_rx else None,
            "settling": now < c.dirty_until,
            "assignment_mode": st.assignment.mode, "flip": st.assignment.flip,
            "name_format_ok": any(s.number is not None for s in st.strips),
            "configured": self.configured,
            "logic_running": self._logic_running(),
            "visible_numbers": [s.number for s in st.strips if s.number is not None],
            "transport": st.transport.__dict__, "time": {"mode": st.time.mode, "text": st.time.text,
                                                        "parsed": st.time.parsed()},
        }

    def track(self, action: str, strip: int | None = None, number: int | None = None) -> ToolResult:
        t0 = self._now_ms()
        with self._lock:
            if (r := self._require_ready(action, t0)) is not None:
                return r
            if action not in _TRACK_ACTIONS:
                return self._result(action, False, "skipped", t0, note=f"모르는 action {action}")
            ch = self._resolve(strip, number, action, t0)
            if isinstance(ch, ToolResult):
                return ch
            field, base, want = _TRACK_ACTIONS[action]
            return self._set_led(action, base + ch, want, self._target(ch), self._strip_view(ch),
                                 lambda: self._strip_view(ch), t0)
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_commands.py -q`
Expected: `7 passed`

- [ ] **Step 5: 커밋**

```bash
git add src/logic_mcp/logic/commands.py tests/test_commands.py
git commit -m "feat(logic): Commands — 결과 모델, 주소 해석, 트랙 LED 명령"
```

---

### Task 9: Commands — 트랜스포트, 볼륨, 팬

**Files:**
- Modify: `src/logic_mcp/logic/commands.py` (메서드 추가)
- Test: `tests/test_commands.py` (끝에 추가)

**Interfaces:**
- Produces:
  - `transport(action: str) -> ToolResult` — play, stop, record, cycle_on, cycle_off, rewind, fast_forward
  - `mixer_volume(strip, number, db: float) -> ToolResult`
  - `mixer_pan(strip, number, pan: int) -> ToolResult`

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_commands.py` 끝에:
```python
import math


def test_transport_play_stop_cycle():
    cmds, surface, fake = make_commands()
    lit = echo_led(fake)
    r = cmds.transport("play")
    assert r.ok and r.verified == "verified" and r.after["play"] is True
    assert cmds.transport("play").verified == "skipped"
    r = cmds.transport("stop")
    assert r.ok and r.after["stop"] is True
    r = cmds.transport("cycle_on")
    assert r.ok and r.after["cycle"] is True
    r = cmds.transport("cycle_off")
    assert r.ok and r.after["cycle"] is False
    assert cmds.transport("dance").ok is False


def test_transport_rewind_verified_by_time_change():
    cmds, surface, fake = make_commands()
    fake.replies = lambda d: [bytes([0xB0, 0x47, 0x32])] if d == P.button_down(P.Note.REWIND) else []
    r = cmds.transport("rewind")
    assert r.ok and r.verified == "verified"
    assert fake.sent[:2] == [P.button_down(P.Note.REWIND), P.button_up(P.Note.REWIND)]


def fader_echo(fake, quantize=lambda v: v):
    def replies(data: bytes) -> list[bytes]:
        if data[0] & 0xF0 == 0xE0:
            ch = data[0] & 0x0F
            v = quantize(data[1] | (data[2] << 7))
            return [bytes([0xE0 | ch, v & 0x7F, v >> 7])]
        return []
    fake.replies = replies


def test_set_volume_verified_with_quantized_echo():
    cmds, surface, fake = make_commands()
    fader_echo(fake, quantize=lambda v: v - 10)
    r = cmds.mixer_volume(strip=1, number=None, db=-5.8)
    assert r.ok and r.verified == "verified"
    assert fake.sent == P.fader_move(0, 9990)
    assert r.after["fader_raw"] == 9980


def test_set_volume_clamps_and_notes():
    cmds, surface, fake = make_commands()
    fader_echo(fake)
    r = cmds.mixer_volume(strip=1, number=None, db=12.0)
    assert r.ok and "clamp" in r.note and fake.sent[1] == bytes([0xE0, 14845 & 0x7F, 14845 >> 7])
    r = cmds.mixer_volume(strip=1, number=None, db=-math.inf)
    assert r.ok and fake.sent[-2] == bytes([0xE0, 0x00, 0x00])
    r = cmds.mixer_volume(strip=1, number=None, db=math.nan)
    assert r.ok is False and "NaN" in r.note


def test_set_volume_unverified_when_echo_far():
    cmds, surface, fake = make_commands()
    fake.feed(bytes([0xE0, 0x1B, 0x61]))  # 페이더 1 = 12443 에서 시작
    fader_echo(fake, quantize=lambda v: 0)
    r = cmds.mixer_volume(strip=1, number=None, db=0.0)
    assert r.ok is False and r.verified == "unverified"


def lcd_row2(text: bytes) -> bytes:
    return bytes.fromhex("F0 00 00 66 14 12 38") + text + b"\xF7"


def test_set_pan_reads_lcd_and_sends_delta():
    cmds, surface, fake = make_commands()
    fake.feed(lcd_row2(b"0      "))
    fake.replies = lambda d: [lcd_row2(b"+10    ")] if d == P.vpot_turn(0, 10) else []
    r = cmds.mixer_pan(strip=1, number=None, pan=10)
    assert r.ok and r.verified == "verified" and r.after["value_text"] == "+10"
    assert fake.sent == [P.vpot_turn(0, 10)]
    assert cmds.mixer_pan(strip=1, number=None, pan=10).verified == "skipped"


def test_set_pan_second_nudge_then_unverified():
    cmds, surface, fake = make_commands()
    fake.feed(lcd_row2(b"0      "))
    fake.replies = lambda d: [lcd_row2(b"+7     ")]
    r = cmds.mixer_pan(strip=1, number=None, pan=10)
    assert r.ok is False and r.verified == "unverified"
    assert fake.sent == [P.vpot_turn(0, 10), P.vpot_turn(0, 3)]


def test_set_pan_refused_outside_pan_mode_or_bad_text():
    cmds, surface, fake = make_commands()
    fake.feed(lcd_row2(b"0      "))
    fake.feed(P.button_up(P.Note.PAN))
    fake.feed(P.button_down(P.Note.EQ))
    r = cmds.mixer_pan(strip=1, number=None, pan=5)
    assert r.ok is False and "eq" in r.note and fake.sent == []
    fake.feed(P.button_up(P.Note.EQ))
    fake.feed(P.button_down(P.Note.PAN))
    fake.feed(lcd_row2(b"-      "))
    r = cmds.mixer_pan(strip=1, number=None, pan=5)
    assert r.ok is False and "configure" in r.note and fake.sent == []
    assert cmds.mixer_pan(strip=1, number=None, pan=64).ok is False
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_commands.py -q`
Expected: 8 FAIL, `AttributeError: 'Commands' object has no attribute 'transport'`

- [ ] **Step 3: 메서드 추가**

`src/logic_mcp/logic/commands.py`의 `Commands` 클래스 끝에 추가:
```python
    _TRANSPORT_LED = {"play": (P.Note.PLAY, True), "stop": (P.Note.STOP, True),
                      "record": (P.Note.RECORD, True), "cycle_on": (P.Note.CYCLE, True),
                      "cycle_off": (P.Note.CYCLE, False)}
    _TRANSPORT_MOVE = {"rewind": P.Note.REWIND, "fast_forward": P.Note.FFWD}

    def _transport_view(self) -> dict:
        st = self.surface.state
        return {**st.transport.__dict__, "time": st.time.text, "time_parsed": st.time.parsed()}

    def transport(self, action: str) -> ToolResult:
        t0 = self._now_ms()
        with self._lock:
            if (r := self._require_ready(action, t0)) is not None:
                return r
            if action in self._TRANSPORT_LED:
                note, want = self._TRANSPORT_LED[action]
                return self._set_led(action, note, want, {"transport": action}, self._transport_view(),
                                     self._transport_view, t0)
            if action in self._TRANSPORT_MOVE:
                before = self._transport_view()
                text0 = self.surface.state.time.text
                self._press(self._TRANSPORT_MOVE[action])
                ok = self.surface.wait_for(lambda s: s.time.text != text0, LED_TIMEOUT)
                self.surface.wait_settled(0.3)
                return self._result(action, ok, "verified" if ok else "unverified", t0,
                                    target={"transport": action}, before=before, after=self._transport_view(),
                                    note="" if ok else "타임 디스플레이가 변하지 않음(이미 끝?)")
            return self._result(action, False, "skipped", t0, note=f"모르는 action {action}")

    def mixer_volume(self, strip: int | None, number: int | None, db: float) -> ToolResult:
        action = "set_volume"
        t0 = self._now_ms()
        with self._lock:
            if (r := self._require_ready(action, t0)) is not None:
                return r
            if db != db:  # NaN
                return self._result(action, False, "skipped", t0, note="db가 NaN. 예: -6.0, 0, \"-inf\"")
            ch = self._resolve(strip, number, action, t0)
            if isinstance(ch, ToolResult):
                return ch
            raw = self.faders.db_to_raw(db)
            note = f"clamped to +6.0 dB" if db > 6.0 else ""
            before = self._strip_view(ch)
            for msg in P.fader_move(ch, raw):
                self.surface.send(msg)
            ok = self.surface.wait_for(lambda s: abs(s.strips[ch].fader_raw - raw) <= 32, FADER_TIMEOUT)
            self.surface.wait_settled(0.5)
            after = self._strip_view(ch)
            if ok:
                return self._result(action, True, "verified", t0, target=self._target(ch), before=before,
                                    after=after, note=note)
            changed = after["fader_raw"] != before["fader_raw"]
            return self._result(action, False, "unverified" if changed else "timeout", t0,
                                target=self._target(ch), before=before, after=after,
                                note=(note + " " if note else "") +
                                ("페이더 에코값이 보낸 값과 다름" if changed else "페이더 에코 없음"))

    def mixer_pan(self, strip: int | None, number: int | None, pan: int) -> ToolResult:
        action = "set_pan"
        t0 = self._now_ms()
        with self._lock:
            if (r := self._require_ready(action, t0)) is not None:
                return r
            if not -64 <= pan <= 63:
                return self._result(action, False, "skipped", t0, note="pan은 -64..63 정수")
            mode = self.surface.state.assignment.mode
            if mode != "pan":
                return self._result(action, False, "skipped", t0,
                                    note=f"V-Pot 할당 모드가 {mode}. PAN 모드에서만 팬을 보냄(스펙 2 logic_assign)")
            ch = self._resolve(strip, number, action, t0)
            if isinstance(ch, ToolResult):
                return ch
            current = parse_pan_text(self.surface.state.strips[ch].value_text)
            if current is None:
                return self._result(action, False, "skipped", t0, target=self._target(ch),
                                    note="LCD 2행이 팬 값이 아님. `logic_session configure`로 값 표시 모드 확인")
            before = self._strip_view(ch)
            if current == pan:
                return self._result(action, True, "skipped", t0, target=self._target(ch), before=before,
                                    after=before, note="already")
            for _attempt in range(2):
                cur = parse_pan_text(self.surface.state.strips[ch].value_text)
                if cur is None or cur == pan:
                    break
                self.surface.send(P.vpot_turn(ch, max(-63, min(63, pan - cur))))
                self.surface.wait_for(lambda s: parse_pan_text(s.strips[ch].value_text) == pan, PAN_TIMEOUT)
                self.surface.wait_settled(0.3)
            after = self._strip_view(ch)
            ok = parse_pan_text(after["value_text"]) == pan
            return self._result(action, ok, "verified" if ok else "unverified", t0, target=self._target(ch),
                                before=before, after=after, note="" if ok else "LCD 팬 값이 목표와 다름")
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_commands.py -q`
Expected: `15 passed`

- [ ] **Step 5: 커밋**

```bash
git add src/logic_mcp/logic/commands.py tests/test_commands.py
git commit -m "feat(logic): 트랜스포트·볼륨·팬 명령과 검증"
```

---

### Task 10: Commands — 뱅크, configure, wait_ready

**Files:**
- Modify: `src/logic_mcp/logic/commands.py`
- Test: `tests/test_commands.py` (끝에 추가)

**Interfaces:**
- Produces:
  - `bank(action: str, number: int | None = None) -> ToolResult` — left, right, channel_left, channel_right, first, last, show
  - `_show_number(number, t0) -> int | None` 완성(첫 세트로 간 뒤 BANK_RIGHT 최대 32회)
  - `configure() -> ToolResult`
  - `wait_ready(timeout_s: float) -> ToolResult`

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_commands.py` 끝에:
```python
def lcd_row1(text: bytes) -> bytes:
    return bytes.fromhex("F0 00 00 66 14 12 00") + text.ljust(56) + b"\xF7"


class BankSim:
    """번호 1..n 트랙을 8개씩 보여주는 Logic 흉내. OPTION+BANK◀=첫 세트, BANK▶=+8(끝에서 클램프)."""

    def __init__(self, fake, n: int):
        self.fake, self.n, self.start, self.option = fake, n, 1, False
        fake.replies = self.replies

    def row(self) -> bytes:
        cols = [f"{i}:T{i}".ljust(7)[:7].encode() for i in range(self.start, self.start + 8) if i <= self.n]
        return b"".join(cols)

    def replies(self, data: bytes) -> list[bytes]:
        if data == P.button_down(P.Note.OPTION):
            self.option = True
            return []
        if data == P.button_up(P.Note.OPTION):
            self.option = False
            return []
        if data == P.button_down(P.Note.BANK_RIGHT):
            new = min(self.start + 8, max(1, self.n - 7)) if self.n > 8 else 1
            if self.option:
                new = max(1, self.n - 7)
        elif data == P.button_down(P.Note.BANK_LEFT):
            new = 1 if self.option else max(1, self.start - 8)
        elif data == P.button_down(P.Note.CHANNEL_RIGHT):
            new = min(self.start + 1, max(1, self.n - 7))
        elif data == P.button_down(P.Note.CHANNEL_LEFT):
            new = max(1, self.start - 1)
        else:
            return []
        if new == self.start:
            return []
        self.start = new
        return [lcd_row1(self.row())]


def test_bank_right_left_first_last():
    cmds, surface, fake = make_commands()
    sim = BankSim(fake, 19)
    fake.feed(lcd_row1(sim.row()))
    r = cmds.bank("right")
    assert r.ok and r.verified == "verified" and r.after["visible_numbers"][0] == 9
    r = cmds.bank("right")
    assert r.after["visible_numbers"] == list(range(12, 20))
    r = cmds.bank("right")
    assert r.ok is False and r.verified == "unverified" and "변화 없음" in r.note
    r = cmds.bank("first")
    assert r.ok and r.after["visible_numbers"][0] == 1
    assert fake.sent[-3:] == [P.button_down(P.Note.BANK_LEFT), P.button_up(P.Note.BANK_LEFT), P.button_up(P.Note.OPTION)]
    r = cmds.bank("last")
    assert r.after["visible_numbers"][-1] == 19
    r = cmds.bank("channel_left")
    assert r.after["visible_numbers"][0] == 11


def test_show_number_navigates_and_track_by_number_in_other_bank():
    cmds, surface, fake = make_commands()
    sim = BankSim(fake, 19)
    fake.feed(lcd_row1(sim.row()))
    r = cmds.bank("show", number=14)
    assert r.ok and 14 in r.after["visible_numbers"]
    r = cmds.bank("show", number=14)
    assert r.verified == "skipped"
    r = cmds.bank("show", number=40)
    assert r.ok is False and "40" in r.note
    # number 주소가 다른 뱅크에 있어도 track이 알아서 옮긴다
    old = fake.replies
    def replies(data: bytes) -> list[bytes]:
        out = old(data)
        if data == P.button_down(P.Note.MUTE + 2) and sim.start == 9:
            out.append(P.button_down(P.Note.MUTE + 2))
        return out
    fake.replies = replies
    r = cmds.track("mute", number=11)
    assert r.ok and r.target == {"strip": 3, "number": 11, "name": "T11"}


def test_configure_turns_on_numbers_and_value_mode_and_beats():
    cmds, surface, fake = make_commands(ready=False)
    fake.feed(lcd_row1(b"Audio 1St Out Master "))
    fake.feed(P.button_down(P.Note.SMPTE_LED))
    surface.tick()
    state = {"numbers": False, "value": False, "beats": False}

    def replies(data: bytes) -> list[bytes]:
        if data == P.button_down(P.Note.NAME_VALUE) and P.button_down(P.Note.OPTION) in fake.sent[-2:]:
            state["numbers"] = True
            return [lcd_row1(b"1:Audio2:St Ou3:Maste")]
        if data == P.button_down(P.Note.NAME_VALUE):
            state["value"] = True
            return []
        if data[0] & 0xF0 == 0xE0:
            return [lcd_row2(b"+0.0 dB" if state["value"] else b"Volume ")]
        if data == P.button_down(P.Note.SMPTE_BEATS):
            return [P.button_up(P.Note.SMPTE_LED), P.button_down(P.Note.BEATS_LED)]
        return []
    fake.replies = replies
    r = cmds.configure()
    assert r.ok and state == {"numbers": True, "value": True, "beats": True}
    assert cmds.status()["configured"] is True and cmds.status()["name_format_ok"] is True
    r2 = cmds.configure()
    assert r2.ok and r2.verified == "skipped"


def test_wait_ready():
    cmds, surface, fake = make_commands(ready=False)
    r = cmds.wait_ready(0.05)
    assert r.ok is False and r.verified == "timeout"
    fake.feed(lcd_row1(b"1:1"))
    surface.tick()
    assert cmds.wait_ready(0.05).ok is True
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_commands.py -q`
Expected: 4 FAIL (`bank`/`configure`/`wait_ready` 없음, `number=11` 해석 실패)

- [ ] **Step 3: 구현**

`src/logic_mcp/logic/commands.py`에서 기존 `_show_number`를 교체하고 메서드를 추가:
```python
    _BANK_NOTES = {"left": P.Note.BANK_LEFT, "right": P.Note.BANK_RIGHT,
                   "channel_left": P.Note.CHANNEL_LEFT, "channel_right": P.Note.CHANNEL_RIGHT}

    def _bank_view(self) -> dict:
        st = self.surface.state
        return {"visible_numbers": [s.number for s in st.strips if s.number is not None],
                "row1": st.lcd[0]}

    def _press_with_option(self, note: int) -> None:
        self.surface.send(P.button_down(P.Note.OPTION))
        self._press(note)
        self.surface.send(P.button_up(P.Note.OPTION))

    def _move_bank(self, press: Callable[[], None]) -> bool:
        row0 = self.surface.state.lcd[0]
        press()
        ok = self.surface.wait_for(lambda s: s.lcd[0] != row0, BANK_TIMEOUT)
        self.surface.wait_settled(0.3)
        return ok

    def _show_number(self, number: int, t0: int) -> int | None:
        def visible() -> int | None:
            numbers = [s.number for s in self.surface.state.strips]
            return numbers.index(number) if number in numbers else None
        if (ch := visible()) is not None:
            return ch
        self._move_bank(lambda: self._press_with_option(P.Note.BANK_LEFT))
        for _ in range(32):
            if (ch := visible()) is not None:
                return ch
            if not self._move_bank(lambda: self._press(P.Note.BANK_RIGHT)):
                return None
        return visible()

    def bank(self, action: str, number: int | None = None) -> ToolResult:
        t0 = self._now_ms()
        with self._lock:
            if (r := self._require_ready(action, t0)) is not None:
                return r
            before = self._bank_view()
            if action == "show":
                if number is None:
                    return self._result(action, False, "skipped", t0, note="show에는 number가 필요")
                if number in before["visible_numbers"]:
                    return self._result(action, True, "skipped", t0, before=before, after=before, note="already")
                ch = self._show_number(number, t0)
                after = self._bank_view()
                if ch is None:
                    return self._result(action, False, "unverified", t0, before=before, after=after,
                                        note=f"번호 {number} 없음. 보이는 번호: {after['visible_numbers']}")
                return self._result(action, True, "verified", t0, target={"strip": ch + 1, "number": number},
                                    before=before, after=after)
            if action == "first":
                ok = self._move_bank(lambda: self._press_with_option(P.Note.BANK_LEFT))
            elif action == "last":
                ok = self._move_bank(lambda: self._press_with_option(P.Note.BANK_RIGHT))
            elif action in self._BANK_NOTES:
                ok = self._move_bank(lambda: self._press(self._BANK_NOTES[action]))
            else:
                return self._result(action, False, "skipped", t0, note=f"모르는 action {action}")
            after = self._bank_view()
            if action in ("first", "last") and not ok and before["visible_numbers"]:
                return self._result(action, True, "skipped", t0, before=before, after=after, note="already")
            return self._result(action, ok, "verified" if ok else "unverified", t0, before=before, after=after,
                                note="" if ok else "LCD 변화 없음(끝에 닿았거나 트랙이 8개 이하)")

    def configure(self) -> ToolResult:
        action = "configure"
        t0 = self._now_ms()
        with self._lock:
            st = self.surface.state
            if st.connection.state not in ("ready", "animating"):
                return self._result(action, False, "skipped", t0,
                                    note=f"상태가 {st.connection.state}. Logic에서 프로젝트를 열면 자동 설치됨")
            done: list[str] = []
            # 1) 번호 접두사
            if not any(s.number is not None for s in st.strips):
                self._move_bank(lambda: self._press_with_option(P.Note.NAME_VALUE))
                if not any(s.number is not None for s in self.surface.state.strips):
                    return self._result(action, False, "unverified", t0, after=self.status(),
                                        note="OPTION+NAME/VALUE 뒤에도 LCD에 번호가 없음")
                done.append("numbers")
            # 2) 값 표시 모드: 페이더 1을 현재값으로 다시 보내 dB 텍스트가 뜨는지 본다
            def probe_value_mode() -> bool:
                raw = self.surface.state.strips[0].fader_raw
                for msg in P.fader_move(0, raw):
                    self.surface.send(msg)
                return self.surface.wait_for(lambda s: parse_db_text(s.strips[0].value_text) is not None, FADER_TIMEOUT)
            if not probe_value_mode():
                self._press(P.Note.NAME_VALUE)
                self.surface.wait_settled(0.5)
                if not probe_value_mode():
                    return self._result(action, False, "unverified", t0, after=self.status(),
                                        note="NAME/VALUE 뒤에도 LCD 2행에 dB 값이 안 보임")
                done.append("value_mode")
            # 3) Beats 클락
            if self.surface.state.time.mode != "beats":
                self._press(P.Note.SMPTE_BEATS)
                if not self.surface.wait_for(lambda s: s.time.mode == "beats", LED_TIMEOUT):
                    return self._result(action, False, "unverified", t0, after=self.status(),
                                        note="SMPTE/BEATS 뒤에도 BEATS LED가 안 켜짐")
                done.append("beats")
            self.surface.wait_settled(0.5)
            self.configured = True
            return self._result(action, True, "verified" if done else "skipped", t0, after=self.status(),
                                note=("changed: " + ", ".join(done)) if done else "already")

    def wait_ready(self, timeout_s: float) -> ToolResult:
        action = "wait_ready"
        t0 = self._now_ms()
        ok = self.surface.wait_for(lambda s: s.connection.state == "ready", timeout_s)
        return self._result(action, ok, "verified" if ok else "timeout", t0, after=self.status(),
                            note="" if ok else "Logic이 서피스를 설치하지 않음. Logic에서 프로젝트를 열거나 다시 여세요")
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_commands.py -q`
Expected: `19 passed`

- [ ] **Step 5: 커밋**

```bash
git add src/logic_mcp/logic/commands.py tests/test_commands.py
git commit -m "feat(logic): 뱅크 이동, number 탐색, configure, wait_ready"
```

---

### Task 11: MCP 서버 — 툴, 리소스, main

**Files:**
- Create: `src/logic_mcp/server/app.py`, `src/logic_mcp/server/tools.py`, `src/logic_mcp/server/resources.py`, `src/logic_mcp/server/main.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Produces:
  - `create_server(commands: Commands, *, start_surface: bool) -> MCPServer`
  - `register_tools(mcp, commands)`, `register_resources(mcp, commands)`
  - `main()` → rtmidi 트랜스포트로 Surface·Commands를 만들고 `mcp.run()`(stdio)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_server.py`:
```python
import json

import pytest
from mcp import Client

from logic_mcp.logic.commands import Commands
from logic_mcp.logic.faders import FaderTable
from logic_mcp.mcu import protocol as P
from logic_mcp.server.app import create_server
from tests.fakes import make_surface
from tests.test_commands import LCD_NUMBERED, echo_led


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def setup():
    surface, fake = make_surface()
    cmds = Commands(surface, FaderTable.load(), sleep=lambda s: None, logic_running=lambda: True)
    fake.feed(LCD_NUMBERED)
    fake.feed(P.button_down(P.Note.PAN))
    surface.tick()
    echo_led(fake)
    mcp = create_server(cmds, start_surface=False)
    return mcp, fake


@pytest.mark.anyio
async def test_tool_list_and_names(setup):
    mcp, fake = setup
    async with Client(mcp, raise_exceptions=True) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools.tools}
        assert names == {"logic_transport", "logic_track", "logic_mixer", "logic_bank", "logic_session"}
        track = next(t for t in tools.tools if t.name == "logic_track")
        assert set(track.input_schema["properties"]) == {"action", "strip", "number"}
        assert "mute" in track.input_schema["properties"]["action"]["enum"]


@pytest.mark.anyio
async def test_mute_call_returns_structured_result(setup):
    mcp, fake = setup
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("logic_track", {"action": "mute", "strip": 1})
        sc = result.structured_content
        assert sc["ok"] is True and sc["verified"] == "verified"
        assert sc["after"]["mute"] is True
        assert fake.sent[0] == P.button_down(P.Note.MUTE)


@pytest.mark.anyio
async def test_session_status_and_resources(setup):
    mcp, fake = setup
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("logic_session", {"action": "status"})
        assert result.structured_content["after"]["state"] == "ready"
        res = await client.list_resources()
        uris = {str(r.uri) for r in res.resources}
        assert {"logic://status", "logic://transport", "logic://strips", "logic://lcd"} <= uris
        strips = await client.read_resource("logic://strips")
        data = json.loads(strips.contents[0].text)
        assert data["strips"][0]["number"] == 1 and len(data["strips"]) == 8
        lcd = json.loads((await client.read_resource("logic://lcd")).contents[0].text)
        assert lcd["row1"].startswith("1:1")
        tr = json.loads((await client.read_resource("logic://transport")).contents[0].text)
        assert "play" in tr and "time" in tr


@pytest.mark.anyio
async def test_mixer_db_accepts_minus_inf_string(setup):
    mcp, fake = setup
    async with Client(mcp, raise_exceptions=True) as client:
        fake.replies = lambda d: [bytes([0xE0, 0, 0])] if d[0] & 0xF0 == 0xE0 else []
        result = await client.call_tool("logic_mixer", {"action": "set_volume", "strip": 1, "db": "-inf"})
        assert result.structured_content["ok"] is True
        result = await client.call_tool("logic_mixer", {"action": "set_pan", "strip": 1})
        assert result.structured_content["ok"] is False and "pan" in result.structured_content["note"]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_server.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'logic_mcp.server.app'`

- [ ] **Step 3: tools.py**

`src/logic_mcp/server/tools.py`:
```python
"""MCP 툴. 입력 검증과 Commands 호출만 한다."""
from __future__ import annotations

import math
from typing import Annotated, Literal

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from ..logic.commands import Commands, ToolResult

Strip = Annotated[int | None, Field(ge=1, le=8, description="현재 뱅크의 스트립 1-8. number와 둘 중 하나만")]
Number = Annotated[int | None, Field(ge=1, description="LCD에 찍히는 Logic 채널 번호(절대 주소). strip과 둘 중 하나만")]


def register_tools(mcp: MCPServer, commands: Commands) -> None:
    @mcp.tool(name="logic_transport", annotations=ToolAnnotations(idempotent_hint=True),
              description="재생/정지/녹음/사이클/되감기/빨리감기. LED와 타임 디스플레이로 검증한다.")
    def logic_transport(
        action: Literal["play", "stop", "record", "cycle_on", "cycle_off", "rewind", "fast_forward"],
    ) -> ToolResult:
        return commands.transport(action)

    @mcp.tool(name="logic_track", annotations=ToolAnnotations(idempotent_hint=True),
              description="트랙 뮤트/솔로/녹음 활성/선택. 이미 그 상태면 보내지 않는다(skipped).")
    def logic_track(
        action: Literal["mute", "unmute", "solo", "unsolo", "arm", "disarm", "select"],
        strip: Strip = None,
        number: Number = None,
    ) -> ToolResult:
        return commands.track(action, strip=strip, number=number)

    @mcp.tool(name="logic_mixer", annotations=ToolAnnotations(idempotent_hint=True),
              description="볼륨(dB, -inf..+6.0)과 팬(-64..63). 팬은 V-Pot가 PAN 모드일 때만.")
    def logic_mixer(
        action: Literal["set_volume", "set_pan"],
        strip: Strip = None,
        number: Number = None,
        db: Annotated[float | Literal["-inf"] | None, Field(description="set_volume: dB. 문자열 \"-inf\" 허용")] = None,
        pan: Annotated[int | None, Field(ge=-64, le=63, description="set_pan: -64(L)..63(R)")] = None,
    ) -> ToolResult:
        if action == "set_volume":
            if db is None:
                return ToolResult(ok=False, verified="skipped", action=action, note="set_volume에는 db가 필요. 예: -6.0, 0, \"-inf\"")
            value = -math.inf if db == "-inf" else float(db)
            return commands.mixer_volume(strip, number, value)
        if pan is None:
            return ToolResult(ok=False, verified="skipped", action=action, note="set_pan에는 pan(-64..63)이 필요")
        return commands.mixer_pan(strip, number, pan)

    @mcp.tool(name="logic_bank",
              description="8스트립 뱅크 이동. show는 number가 보이도록 뱅크를 찾아간다.")
    def logic_bank(
        action: Literal["left", "right", "channel_left", "channel_right", "first", "last", "show"],
        number: Number = None,
    ) -> ToolResult:
        return commands.bank(action, number=number)

    @mcp.tool(name="logic_session",
              description="status: 연결 상태. wait_ready: Logic이 서피스를 설치할 때까지 대기. configure: 번호 표시·값 모드·Beats 클락 보정(처음 한 번).")
    def logic_session(
        action: Literal["status", "wait_ready", "configure"],
        timeout_s: Annotated[float, Field(gt=0, le=120)] = 10.0,
    ) -> ToolResult:
        if action == "status":
            return ToolResult(ok=True, verified="skipped", action=action, after=commands.status())
        if action == "wait_ready":
            return commands.wait_ready(timeout_s)
        return commands.configure()
```

- [ ] **Step 4: resources.py, app.py, main.py**

`src/logic_mcp/server/resources.py`:
```python
"""읽기 전용 리소스. JSON 문자열을 돌려준다."""
from __future__ import annotations

import json

from mcp.server import MCPServer

from ..logic.commands import Commands


def register_resources(mcp: MCPServer, commands: Commands) -> None:
    @mcp.resource("logic://status", description="연결 상태, 설정 여부, 보이는 번호")
    def status() -> str:
        return json.dumps(commands.status(), ensure_ascii=False)

    @mcp.resource("logic://transport", description="트랜스포트 LED와 타임 디스플레이(최신값)")
    def transport() -> str:
        st = commands.surface.state
        return json.dumps({**st.transport.__dict__, "time": {"mode": st.time.mode, "text": st.time.text,
                                                              "parsed": st.time.parsed()}}, ensure_ascii=False)

    @mcp.resource("logic://strips", description="현재 뱅크 스트립 8개")
    def strips() -> str:
        st = commands.surface.state
        return json.dumps({"settling": commands.surface.clock() < st.connection.dirty_until,
                           "strips": [commands._strip_view(i) for i in range(8)]}, ensure_ascii=False)

    @mcp.resource("logic://lcd", description="LCD 2×56 원문")
    def lcd() -> str:
        st = commands.surface.state
        return json.dumps({"row1": st.lcd[0], "row2": st.lcd[1],
                           "settling": commands.surface.clock() < st.connection.dirty_until}, ensure_ascii=False)
```

`src/logic_mcp/server/app.py`:
```python
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server import MCPServer

from ..logic.commands import Commands
from .resources import register_resources
from .tools import register_tools


def create_server(commands: Commands, *, start_surface: bool) -> MCPServer:
    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[None]:
        if start_surface:
            commands.surface.start()
        try:
            yield None
        finally:
            if start_surface:
                commands.surface.stop()

    mcp = MCPServer("logic-mcp", lifespan=lifespan)
    register_tools(mcp, commands)
    register_resources(mcp, commands)
    return mcp
```

`src/logic_mcp/server/main.py`:
```python
from __future__ import annotations

from ..logic.commands import Commands
from ..logic.faders import FaderTable
from ..mcu.surface import Surface
from ..mcu.transport import RtMidiTransport
from .app import create_server


def build() -> tuple[Commands, Surface]:
    surface = Surface(RtMidiTransport())
    return Commands(surface, FaderTable.load()), surface


def main() -> None:
    commands, _surface = build()
    create_server(commands, start_surface=True).run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/test_server.py -q`
Expected: `4 passed`. `input_schema` 속성명이 다르면 `tools.tools[0]`를 `print`해서 실제 필드명(`inputSchema`일 수 있음)으로 테스트를 맞춘다. 구조화 응답이 `structured_content`에 없으면 `result.content[0].text`를 `json.loads`한다.

- [ ] **Step 6: 전체 테스트와 서버 기동 확인**

Run: `uv run pytest -q`
Expected: 전부 통과.

Run: `timeout 5 uv run logic-mcp < /dev/null; echo exit=$?`
Expected: 가상 포트를 열고 stdio EOF로 종료(exit 0 또는 124). 예외 트레이스가 없어야 한다.

- [ ] **Step 7: 커밋**

```bash
git add src/logic_mcp/server tests/test_server.py
git commit -m "feat(server): MCP 툴 5개, 리소스 4개, stdio 진입점"
```

---

### Task 12: 스크립트, 문서, 실제 Logic 검증, 캘리브레이션

**Files:**
- Create: `scripts/capture.py`, `scripts/live_check.py`, `scripts/calibrate_fader.py`, `docs/mcu-protocol.md`, `README.md`, `.mcp.json.example`
- Modify: `src/logic_mcp/logic/fader_db.json` (캘리브레이션 결과), `docs/progress.md`

**Interfaces:**
- Consumes: `Surface`, `Commands`, `RtMidiTransport`, `FaderTable`, `parse_db_text`.

이 태스크는 실제 Logic Pro가 필요하다. 시작 전에 `~/logic-mcp-spike`의 capture2.py가 돌고 있으면 끝낸다(`pkill -f capture2.py`). 같은 이름의 가상 포트가 두 개면 Logic이 엉뚱한 쪽에 붙는다.

- [ ] **Step 1: scripts/capture.py**

```python
"""가상 포트를 열고 Logic이 보내는 MCU 트래픽을 'ts RX|TX hex' 픽스처 형식으로 기록한다.
사용: uv run python scripts/capture.py <초> <출력경로>"""
import sys
import time

from logic_mcp.mcu import protocol as P
from logic_mcp.mcu.surface import Surface
from logic_mcp.mcu.transport import RtMidiTransport

duration = float(sys.argv[1]) if len(sys.argv) > 1 else 600
out_path = sys.argv[2] if len(sys.argv) > 2 else f"capture_{int(time.time())}.log"
t0 = time.monotonic()
log = open(out_path, "a", buffering=1)


class LoggingTransport(RtMidiTransport):
    def send(self, data: bytes) -> None:
        log.write(f"{time.monotonic() - t0:9.3f} TX {data.hex(' ').upper()}\n")
        super().send(data)


transport = LoggingTransport()
surface = Surface(transport)
inner = surface.handle_message


def handle(ts: float, data: bytes) -> None:
    log.write(f"{ts - t0:9.3f} RX {data.hex(' ').upper()}\n")
    inner(ts, data)
    ev = P.decode(data)
    if not isinstance(ev, (P.Meter, P.TimeDigit)):
        print(f"[{ts - t0:7.2f}] {ev}", flush=True)


transport.on_message = handle
surface.start()
print(f"포트 LogicMCP 열림. {duration:.0f}초 기록 → {out_path}")
try:
    time.sleep(duration)
finally:
    surface.stop()
    print("LCD:", surface.state.lcd)
```

- [ ] **Step 2: scripts/live_check.py**

```python
"""실제 Logic으로 명령→피드백을 확인한다. Logic에서 프로젝트를 열어 둔 상태로 실행.
사용: uv run python scripts/live_check.py"""
import time

from logic_mcp.server.main import build

commands, surface = build()
surface.start()
try:
    print("Logic이 서피스를 설치하기를 기다리는 중 (프로젝트를 열거나 다시 여세요)…")
    print(commands.wait_ready(60).model_dump())
    rows = [("configure", commands.configure())]
    rows.append(("status", commands.status()))
    rows.append(("mute 1", commands.track("mute", strip=1)))
    rows.append(("unmute 1", commands.track("unmute", strip=1)))
    rows.append(("play", commands.transport("play")))
    time.sleep(1.0)
    rows.append(("stop", commands.transport("stop")))
    rows.append(("cycle_on", commands.transport("cycle_on")))
    rows.append(("cycle_off", commands.transport("cycle_off")))
    rows.append(("volume -6", commands.mixer_volume(1, None, -6.0)))
    rows.append(("volume 0", commands.mixer_volume(1, None, 0.0)))
    rows.append(("pan +10", commands.mixer_pan(1, None, 10)))
    rows.append(("pan 0", commands.mixer_pan(1, None, 0)))
    rows.append(("bank right", commands.bank("right")))
    rows.append(("bank first", commands.bank("first")))
    for name, r in rows:
        if isinstance(r, dict):
            print(f"{name:12} {r}")
        else:
            print(f"{name:12} ok={r.ok} {r.verified:10} {r.elapsed_ms:4}ms {r.note}")
finally:
    surface.stop()
```

- [ ] **Step 3: scripts/calibrate_fader.py**

```python
"""페이더 raw 값을 훑어 LCD의 dB 텍스트를 읽고 fader_db.json을 만든다. 값 표시 모드 필요.
사용: uv run python scripts/calibrate_fader.py"""
import json
from pathlib import Path

from logic_mcp.logic.faders import MAX_RAW, parse_db_text
from logic_mcp.mcu import protocol as P
from logic_mcp.server.main import build

OUT = Path("src/logic_mcp/logic/fader_db.json")
commands, surface = build()
surface.start()
try:
    assert commands.wait_ready(60).ok, "Logic이 서피스를 설치하지 않음"
    assert commands.configure().ok, "configure 실패"
    original = surface.state.strips[0].fader_raw
    points: list[list] = []
    for raw in list(range(0, MAX_RAW, 64)) + [MAX_RAW]:
        for msg in P.fader_move(0, raw):
            surface.send(msg)
        surface.wait_for(lambda s: abs(s.strips[0].fader_raw - raw) <= 32, 0.8)
        surface.wait_settled(0.5)
        db = parse_db_text(surface.state.strips[0].value_text)
        echoed = surface.state.strips[0].fader_raw
        print(raw, echoed, db)
        if db is not None:
            points.append([echoed, None if db == float("-inf") else db])
    for msg in P.fader_move(0, original):
        surface.send(msg)
    dedup = {}
    for r, d in points:
        dedup[r] = d
    OUT.write_text(json.dumps({"source": "scripts/calibrate_fader.py, Logic Pro 12.0.1",
                               "points": [[r, dedup[r]] for r in sorted(dedup)]}, indent=0))
    print(f"{len(dedup)}점 → {OUT}")
finally:
    surface.stop()
```

- [ ] **Step 4: README.md, .mcp.json.example, docs/mcu-protocol.md**

`README.md`:
```markdown
# logic-mcp

Claude Code가 Logic Pro를 조작하는 MCP 서버. Logic이 공식 지원하는 Mackie Control 프로토콜을 CoreMIDI 가상 포트로 에뮬레이션하고, 모든 명령을 Logic의 LED·페이더·LCD 피드백으로 검증한다.

## 설치 (macOS, Logic Pro 11/12)

1. `uv sync`
2. Claude Code 프로젝트에 `.mcp.json` 추가 (`.mcp.json.example` 참고)
3. Claude Code를 켠 뒤 Logic에서 프로젝트를 연다. Logic이 "LogicMCP" 포트를 Mackie Control로 자동 설치한다.
4. 처음 한 번 `logic_session configure`를 호출한다(트랙 번호 표시, 값 표시 모드, Beats 클락).

## 툴

`logic_transport`, `logic_track`, `logic_mixer`, `logic_bank`, `logic_session`. 리소스 `logic://status`, `logic://transport`, `logic://strips`, `logic://lcd`.

## 개발

`uv run pytest` (실제 Logic 불필요). 실제 검증은 `uv run python scripts/live_check.py`.
설계: `docs/superpowers/specs/`, 프로토콜 실측: `docs/mcu-protocol.md`.
```

`.mcp.json.example`:
```json
{
  "mcpServers": {
    "logic": {
      "command": "uv",
      "args": ["run", "--directory", "/ABSOLUTE/PATH/TO/logic-mcp", "logic-mcp"]
    }
  }
}
```

`docs/mcu-protocol.md`: 스펙 부록 A를 옮기고, 아래 실측 사실을 덧붙인다.
```markdown
# MCU 프로토콜 실측 (Logic Pro 12.0.1, macOS 26.5, 2026-10-13~14)

(스펙 부록 A의 표를 그대로 복사)

## 타이밍
- 버튼 누름 → LED 피드백 15~50ms. LCD "Muted" 텍스트는 LED보다 먼저 온다.
- 페이더 전송 → 에코 ~130ms. 에코값은 양자화된다(10000 → 9990).
- 설치(핸드셰이크) → 전체 redraw → 7.6초 공백 → 환영 애니메이션 약 60초(LCD 점 이동, 링 스윕, 3초 공백 포함) → 전체 redraw → 10초 조용하면 사용 가능. 재바인딩(핸드셰이크 없음)은 1초 조용.

## 동작
- 포트당 기기 1대. Extender가 포트를 점유하면 본체가 설치되지 않는다.
- OPTION+NAME/VALUE: LCD 1행 `번호:이름` 토글. NAME/VALUE: 2행 이름/값 토글.
- OPTION 누름 자체가 SEL2/SEL3/READ_OFF/UNDO LED를 깜빡인다(무해).
- 비ASCII 트랙명은 LCD에서 사라진다("오디오 1" → "1").
- 페이더 최대 14845(+6.0 dB), 0 dB = 12443, 0 = -oo dB.
- V-Pot 한 메시지의 크기 비트가 그대로 스텝 수(+5 → 팬 +5).
```

- [ ] **Step 5: 실제 Logic 검증**

```bash
pkill -f capture2.py; sleep 1
uv run python scripts/live_check.py
```
Expected: `wait_ready` ok(Logic에서 프로젝트를 다시 열어야 할 수 있다), 이어서 각 줄이 `ok=True verified` 또는 `skipped`. `bank right`는 트랙이 8개 이하면 `unverified "LCD 변화 없음"`이 정상이다.

실패하는 줄이 있으면 `scripts/capture.py`로 원시 로그를 떠서 원인을 찾고 코드를 고친 뒤 다시 돈다. 모두 통과한 출력을 `docs/progress.md`에 붙인다.

- [x] **Step 6: BANK/CHANNEL 노트 번호 확인 (트랙 9개 이상 프로젝트)**

결과(2026-10-15, 트랙 22채널): bank left 15→9, bank right 9→15(끝 클램프), channel_right 9→10, channel_left 10→9. 표준 맵 2E/2F/30/31 그대로 맞음, 코드 변경 없음.

Logic에서 트랙을 9개 이상 만든 뒤:
```bash
uv run python scripts/live_check.py 2>&1 | grep -i bank
```
Expected: `bank right`가 `verified`이고 `after.visible_numbers`가 9부터 시작. 만약 1만큼만 움직이면 `protocol.Note`의 BANK_RIGHT(0x2F)와 CHANNEL_LEFT(0x30)가 뒤바뀐 것이므로 `Note.BANK_RIGHT = 0x30, CHANNEL_LEFT = 0x2F`로 고치고 `tests/test_protocol.py`를 맞춘다.

- [ ] **Step 7: 캘리브레이션**

```bash
uv run python scripts/calibrate_fader.py
uv run pytest tests/test_faders.py -q
```
Expected: 200점 이상, `fader_db.json` 교체, 테스트 통과(스팟 포인트 9990/12443/14845가 표에 있어야 한다. 없으면 `points`에 실측 4점을 손으로 추가한다).

- [ ] **Step 8: progress.md 갱신과 커밋**

`docs/progress.md`의 완료 목록에 Task 2~12를 적고, live_check 출력과 캘리브레이션 점 수를 붙인다.

```bash
git add -A
git commit -m "feat: 스크립트, 문서, 실제 Logic 검증, 페이더 캘리브레이션"
```
