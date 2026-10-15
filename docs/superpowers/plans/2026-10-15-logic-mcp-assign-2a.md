# logic-mcp 스펙 2a 구현 계획 — 모드 드라이버 · 값 설정 · EQ · 플러그인

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Claude가 MCU 어사인먼트 모드로 Logic의 Channel EQ와 인서트 플러그인을 읽고 정확한 값으로 바꾸게 한다(`logic_eq`, `logic_plugin`). 센드·번들 데이터 생성·스킬은 계획 2b.

**Architecture:** 스펙 1의 Surface/상태 리듀서/Commands 위에 (1) 뷰 상태(`View`)를 리듀서에 추가하고, (2) 모드 전환·페이지·미리 선택·Flip·PAN 복귀를 소유하는 `ModeDriver`를 두고, (3) 공통 값 파서·매핑·설정 루프(`values.py`, `setter.py`)를 만들고, (4) 그 위에 `EqCommands`·`PluginCommands`를 올려 MCP 도구 2개와 리소스 3개로 노출한다. 테스트는 어사인먼트 모드를 흉내 내는 가짜 Logic(`tests/fake_assign.py`)과 스파이크 원시 로그 픽스처로 한다.

**Tech Stack:** Python ≥3.13, uv, `mcp` 2.3 (`MCPServer`), python-rtmidi, pydantic, pytest + anyio. 새 의존성 없음.

**Spec:** `docs/superpowers/specs/2026-10-15-logic-mcp-assign-design.md` (실측 노트 `~/logic-mcp-spike/스펙2-스파이크.md`)

## Global Constraints

- Python `>=3.13`, 의존성 추가 금지. 테스트는 CoreMIDI를 열지 않는다(`rtmidi`는 `RtMidiTransport.open` 안에서만 임포트).
- MCP는 `from mcp.server import MCPServer`, 툴 속성은 `input_schema`/`structured_content`(v2 이름).
- 모든 도구는 스펙 1 `ToolResult(ok, verified∈{verified,unverified,timeout,skipped}, action, target, before, after, elapsed_ms, note)`를 돌려준다. 예외를 밖으로 던지지 않는다.
- 스펙 2 명령은 **반드시** `ModeDriver.leave()`로 끝난다(finally). 끝난 뒤 뷰는 `pan`, Flip은 off.
- Flip 상태에서 페이더 raw 0을 보내지 않는다(최소 1). V-Pot 틱은 메시지당 크기 ≤63으로 나눈다.
- 오버레이 2.0초: 모드 전환·값 변경 뒤 정착 열을 읽기 전에 `settle_overlay()`를 거친다.
- 플러그인 `insert`는 차 있는 슬롯에서 `replace=True` 없이는 skipped. EQ 채널 뷰 진입은 Channel EQ를 삽입하므로 `eq_get`은 E1 뷰로만 읽는다.
- 주석·docstring·note 문자열은 한국어(기존 코드와 같이). 커밋 메시지 한국어 + `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Logic UI 클릭·AX 자동화 금지. 프로젝트 저장 금지. 기존 MPK mini IV 컨트롤 서피스 설정 불변.

## Review Focus

1. **오버레이가 떠 있는 동안 열을 읽음** → `Low Cut` 같은 이름 조각이 값으로 파싱됨. Task 4 `test_read_value_uses_overlay_then_column_after_redraw`가 고정(오버레이는 전체 값으로, 재묘사 뒤 열로).
2. **깜박임의 공백 위상을 값으로 읽음**(미리 선택 중 2행이 0.75초마다 비어짐). Task 4 `test_read_column_retries_blank_blink`.
3. **다른 스트립에 미리 선택이 남은 채 V-Pot을 누름** → 엉뚱한 플러그인 삽입. Task 8 `test_params_cancels_stale_preselect_before_press`: 편집 뷰 진입 전 PAN→재진입으로 취소.
4. **예외 경로에서 leave() 누락** → Flip이 켜진 채 남아 스펙 1 팬 읽기가 깨짐. Task 6 `test_eq_set_mode_error_still_leaves`.
5. **V-Pot 크기 >63이 조용히 클램프**(실측 사고: -100 → 다른 플러그인 삽입). Task 1 `test_vpot_turn_messages_split_at_63`, Task 4 `test_tick_splits_at_63_and_fader_never_sends_zero`. 드라이버는 `vpot_turn_messages`만 쓴다.

---

## 파일 구조

| 파일 | 역할 |
|---|---|
| `src/logic_mcp/mcu/protocol.py` (수정) | 커서·ZOOM·F1 노트, `vpot_turn_messages`(63 분할) |
| `src/logic_mcp/mcu/state.py` (수정) | `View` 데이터클래스, 2자리 코드+LCD → 뷰 판정, 열·헤더·페이지 추출, 스트립 값 갱신 범위 제한 |
| `src/logic_mcp/logic/values.py` (신규) | `Value`, `parse_value`, `Mapping`, `raw_for`, `infer_mapping`, `within` |
| `src/logic_mcp/logic/modes.py` (신규) | `ModeDriver`, `ModeError` |
| `src/logic_mcp/logic/setter.py` (신규) | `set_numeric`, `set_enum`, `probe_mapping` |
| `src/logic_mcp/logic/assign.py` (신규) | `EqCommands`, `PluginCommands`(상수 표 포함) |
| `src/logic_mcp/logic/plugins/__init__.py`, `cache.py`, `match.py`, `scan.py`, `known.json` (신규) | 목록 캐시·매칭·스캔·번들 |
| `src/logic_mcp/logic/commands.py` (수정) | `Commands.modes/eq/plugin` 속성, `mixer_pan`의 Flip·PAN 복귀, `status()`에 `view_kind` |
| `src/logic_mcp/server/tools.py`, `resources.py` (수정) | `logic_eq`, `logic_plugin`, `logic://plugins|inserts|view` |
| `tests/fixtures/mcu/cap_assign{1,2,3}.log` (신규) | 스파이크 원시 로그(RX 형식으로 변환) |
| `tests/fake_assign.py` (신규) | 어사인먼트 모드 가짜 Logic |
| `tests/test_values.py`, `test_modes.py`, `test_setter.py`, `test_assign_eq.py`, `test_assign_plugin.py`, `test_plugins.py` (신규), `test_protocol.py`, `test_state.py`, `test_server.py`, `test_commands.py` (수정) | |
| `scripts/live_check2.py` (신규), `docs/mcu-protocol.md`, `docs/progress.md`, `README.md` (수정) | 실기 검증·문서 |

---

### Task 1: 프로토콜 확장과 스파이크 픽스처

**Files:**
- Modify: `src/logic_mcp/mcu/protocol.py`
- Create: `tests/fixtures/mcu/cap_assign1.log`, `cap_assign2.log`, `cap_assign3.log`
- Test: `tests/test_protocol.py`

**Interfaces:**
- Produces: `Note.CURSOR_UP=0x60, CURSOR_DOWN=0x61, CURSOR_LEFT=0x62, CURSOR_RIGHT=0x63, ZOOM=0x64, F1=0x36`; `vpot_turn_messages(channel: int, steps: int) -> list[bytes]`.

- [ ] **Step 1: 픽스처 변환 복사**

스파이크 로그는 `ts hex hex …` 형식이다. 스펙 1 `load_fixture`가 읽는 `ts RX hex …` 형식으로 바꿔 복사한다.

```bash
cd ~/Documents/GitHub/logic-mcp
for n in "" 2 3; do
  awk '{printf "%s RX", $1; for(i=2;i<=NF;i++) printf " %s", $i; print ""}' \
    ~/logic-mcp-spike/cap_assign$n.log > tests/fixtures/mcu/cap_assign${n:-1}.log
done
wc -l tests/fixtures/mcu/cap_assign*.log
```
Expected: 777, 873, 1228줄.

- [ ] **Step 2: 실패하는 테스트**

`tests/test_protocol.py` 끝에 추가:

```python
from pathlib import Path


def test_cursor_and_function_notes():
    assert (P.Note.CURSOR_UP, P.Note.CURSOR_DOWN, P.Note.CURSOR_LEFT, P.Note.CURSOR_RIGHT) == (0x60, 0x61, 0x62, 0x63)
    assert P.Note.ZOOM == 0x64 and P.Note.F1 == 0x36
    assert P.NOTE_NAMES[0x62] == "CURSOR_LEFT"


def test_vpot_turn_messages_split_at_63():
    assert P.vpot_turn_messages(0, 100) == [P.vpot_turn(0, 63), P.vpot_turn(0, 37)]
    assert P.vpot_turn_messages(2, -130) == [P.vpot_turn(2, -63), P.vpot_turn(2, -63), P.vpot_turn(2, -4)]
    assert P.vpot_turn_messages(0, 5) == [P.vpot_turn(0, 5)]
    assert P.vpot_turn_messages(0, 0) == []


def test_assign_fixtures_load():
    rows = P.load_fixture(Path(__file__).parent / "fixtures" / "mcu" / "cap_assign2.log")
    assert len(rows) > 800 and rows[0][1] == "RX"
    kinds = {type(P.decode(data)).__name__ for _, _, data in rows}
    assert {"LcdWrite", "AssignDigit", "FaderPos", "Led", "VpotRing"} <= kinds
```

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest tests/test_protocol.py -q`
Expected: 3 failed (`AttributeError: CURSOR_UP`, `vpot_turn_messages`).

- [ ] **Step 4: 구현**

`protocol.py`의 `class Note`에 `SMPTE_BEATS = 0x35` 다음 줄로 추가:

```python
    F1 = 0x36  # F1-F8 = 0x36-0x3D
    CURSOR_UP = 0x60
    CURSOR_DOWN = 0x61
    CURSOR_LEFT = 0x62
    CURSOR_RIGHT = 0x63
    ZOOM = 0x64
```

`vpot_turn` 바로 뒤에 추가:

```python
def vpot_turn_messages(channel: int, steps: int) -> list[bytes]:
    """크기 63 제한을 넘는 틱을 여러 메시지로 나눈다. 드라이버는 vpot_turn 대신 이것만 쓴다."""
    out: list[bytes] = []
    remaining, sign = abs(steps), (1 if steps > 0 else -1)
    while remaining > 0:
        n = min(remaining, 63)
        out.append(vpot_turn(channel, sign * n))
        remaining -= n
    return out
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/test_protocol.py -q`
Expected: 모두 PASS.

- [ ] **Step 6: 커밋**

```bash
git add src/logic_mcp/mcu/protocol.py tests/test_protocol.py tests/fixtures/mcu/cap_assign1.log tests/fixtures/mcu/cap_assign2.log tests/fixtures/mcu/cap_assign3.log
git commit -m "feat(protocol): 커서·ZOOM·F1 노트, V-Pot 틱 63 분할, 스펙 2 스파이크 픽스처

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: 값 파서와 매핑 (`logic/values.py`)

**Files:**
- Create: `src/logic_mcp/logic/values.py`
- Test: `tests/test_values.py`

**Interfaces:**
- Produces:
  - `Value(kind: "number"|"enum"|"none", number: float|None, unit: str|None, text: str)`
  - `parse_value(text: str) -> Value`
  - `Mapping(type: "db_table"|"log"|"linear"|"enum", lo: float, hi: float, options: tuple[str, ...])`
  - `raw_for(m: Mapping, target: float|str, faders: FaderTable|None) -> int` (1..16383)
  - `infer_mapping(lo: Value, hi: Value) -> Mapping|None`
  - `within(actual: float, target: float, tolerance: float) -> bool`
  - `tolerance_for(target: float, unit: str|None) -> float`

- [ ] **Step 1: 실패하는 테스트**

`tests/test_values.py`:

```python
import math

import pytest

from logic_mcp.logic.faders import FaderTable
from logic_mcp.logic.values import Mapping, Value, infer_mapping, parse_value, raw_for, tolerance_for, within


@pytest.mark.parametrize("text,number,unit", [
    ("20.0Hz", 20.0, "Hz"), ("21.6 Hz", 21.6, "Hz"), ("1040Hz", 1040.0, "Hz"), ("625 Hz", 625.0, "Hz"),
    ("20000", 20000.0, None), ("2.5kHz", 2500.0, "Hz"),
    ("-78.4 d", -78.4, "dB"), ("-78.4 dB", -78.4, "dB"), ("+0.0 dB", 0.0, "dB"), ("0.0 dB", 0.0, "dB"),
    ("-oo dB", -math.inf, "dB"), ("-oodB", -math.inf, "dB"),
    ("36 dB/Oct", 36.0, "dB/Oct"), ("0.71", 0.71, None), ("12", 12.0, None), (" 1", 1.0, None),
    ("1100", 1100.0, None), ("-0.5", -0.5, None), ("50 %", 50.0, "%"), ("12.5 ms", 12.5, "ms"),
])
def test_parse_numbers(text, number, unit):
    v = parse_value(text)
    assert v.kind == "number" and v.unit == unit
    assert v.number == number


@pytest.mark.parametrize("text", ["On", "Off", "Post", "Post Pan", "active", "muted", "--", "* 1", "Control #1", "Cha EQ"])
def test_parse_enum(text):
    v = parse_value(text)
    assert v.kind == "enum" and v.text == text.strip() and v.number is None


def test_parse_none():
    assert parse_value("       ").kind == "none"
    assert parse_value("").kind == "none"


def test_raw_for_log_linear_enum():
    assert raw_for(Mapping("log", 20.0, 20000.0), 20.0) == 1          # raw 0은 보내지 않음
    assert abs(raw_for(Mapping("log", 20.0, 20000.0), 632.0) - 8192) <= 20
    assert raw_for(Mapping("log", 20.0, 20000.0), 20000.0) == 16383
    assert raw_for(Mapping("linear", -24.0, 24.0), 0.0) == 8192
    assert raw_for(Mapping("linear", -24.0, 24.0), 30.0) == 16383   # 클램프
    m = Mapping("enum", options=("6", "12", "18", "24", "36", "48"))
    assert raw_for(m, "12") == 3277 and raw_for(m, "24") == 9830 and raw_for(m, "48") == 16383
    assert raw_for(Mapping("enum", options=("Off", "On")), "Off") == 1
    assert raw_for(Mapping("db_table"), -6.0, FaderTable.load()) == FaderTable.load().db_to_raw(-6.0)
    with pytest.raises(ValueError):
        raw_for(m, "7")


def test_infer_mapping():
    assert infer_mapping(parse_value("20.0 Hz"), parse_value("20000 Hz")) == Mapping("log", 20.0, 20000.0)
    assert infer_mapping(parse_value("-24.0 dB"), parse_value("+24.0 dB")) == Mapping("linear", -24.0, 24.0)
    assert infer_mapping(parse_value("0.10"), parse_value("10.0")) == Mapping("linear", 0.1, 10.0)
    assert infer_mapping(parse_value("Off"), parse_value("On")) is None
    assert infer_mapping(parse_value("-oo dB"), parse_value("+6.0 dB")) is None   # 무한대는 선형 아님


def test_tolerance_and_within():
    assert tolerance_for(1000.0, "Hz") == 10.0
    assert tolerance_for(-3.0, "dB") == 0.1
    assert tolerance_for(0.5, None) == 0.01
    assert within(1004.0, 1000.0, 10.0) and not within(1011.0, 1000.0, 10.0)
    assert not within(math.nan, 1.0, 1.0)
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_values.py -q`
Expected: `ModuleNotFoundError: logic_mcp.logic.values`.

- [ ] **Step 3: 구현**

`src/logic_mcp/logic/values.py`:

```python
"""LCD 열(7칸)·오버레이 값 텍스트 파서와 Flip 페이더 매핑. I/O 없음."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from ..mcu.protocol import MAX_FADER
from .faders import FaderTable

_NUM_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?|-oo)\s*([A-Za-z/%]*)\s*$")
_UNITS = {"": None, "hz": "Hz", "khz": "kHz", "db": "dB", "d": "dB", "db/oct": "dB/Oct",
          "ms": "ms", "s": "s", "%": "%", "st": "st", "ct": "ct", "smp": "smp"}


@dataclass(frozen=True)
class Value:
    kind: str                   # number | enum | none
    number: float | None = None
    unit: str | None = None
    text: str = ""


def parse_value(text: str) -> Value:
    """`20.0Hz`, `-78.4 d`(잘림), `-oo dB`, `36 dB/Oct`, `0.71` → number. `On`, `Post Pan`, `--` → enum. 공백 → none."""
    t = text.strip()
    if not t:
        return Value("none", text="")
    m = _NUM_RE.match(t)
    if m and m.group(2).lower() in _UNITS:
        num, unit = m.group(1), _UNITS[m.group(2).lower()]
        n = -math.inf if num == "-oo" else float(num)
        if unit == "kHz":
            n, unit = n * 1000.0, "Hz"
        return Value("number", n, unit, t)
    return Value("enum", text=t)


@dataclass(frozen=True)
class Mapping:
    """Flip 상태에서 페이더 raw(1..16383) ↔ 파라미터 값."""
    type: str                   # db_table | log | linear | enum
    lo: float = 0.0
    hi: float = 1.0
    options: tuple[str, ...] = ()


def raw_for(m: Mapping, target: float | str, faders: FaderTable | None = None) -> int:
    if m.type == "db_table":
        if faders is None:
            raise ValueError("db_table 매핑에는 FaderTable이 필요")
        raw = faders.db_to_raw(float(target))
    elif m.type == "log":
        raw = round(MAX_FADER * math.log(float(target) / m.lo) / math.log(m.hi / m.lo))
    elif m.type == "linear":
        raw = round(MAX_FADER * (float(target) - m.lo) / (m.hi - m.lo))
    elif m.type == "enum":
        if str(target) not in m.options:
            raise ValueError(f"{target!r}는 선택지 {list(m.options)}에 없음")
        raw = round(MAX_FADER * m.options.index(str(target)) / max(1, len(m.options) - 1))
    else:
        raise ValueError(f"모르는 매핑 {m.type}")
    return max(1, min(MAX_FADER, raw))   # raw 0은 Logic이 무시한 사례가 있어 1부터


def infer_mapping(lo: Value, hi: Value) -> Mapping | None:
    """페이더 1·16383에서 읽은 최소·최대 값으로 유형을 추정한다. 열거형은 None."""
    if lo.kind != "number" or hi.kind != "number" or lo.number is None or hi.number is None:
        return None
    if not (math.isfinite(lo.number) and math.isfinite(hi.number)) or lo.number == hi.number:
        return None
    if lo.unit == "Hz" and lo.number > 0:
        return Mapping("log", lo.number, hi.number)
    return Mapping("linear", lo.number, hi.number)


def tolerance_for(target: float, unit: str | None) -> float:
    if unit == "dB":
        return 0.1
    return round(max(abs(target), 1.0) * 0.01, 6)


def within(actual: float, target: float, tolerance: float) -> bool:
    return math.isfinite(actual) and abs(actual - target) <= tolerance
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_values.py -q`
Expected: 모두 PASS. (`raw_for(..., "12")` = round(16383·1/5) = 3277, `"24"` = round(16383·3/5) = 9830.)

- [ ] **Step 5: 커밋**

```bash
git add src/logic_mcp/logic/values.py tests/test_values.py
git commit -m "feat(values): LCD 값 파서와 Flip 페이더 매핑(log/linear/enum/db_table)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: 뷰 상태 모델 (`mcu/state.py`)

**Files:**
- Modify: `src/logic_mcp/mcu/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Produces: `SurfaceState.view: View` with `View(kind, index, page, header, columns)`; `classify_view(display, lcd, mode) -> tuple[str, int | None]`; 상수 `OVERLAY_MARK = "arameter:"`.
- kind 값: `pan | track | eq_mixer | eq_channel | eq_menu | send_mixer | send_channel | send_destlevel | send_menu | plugin_mixer | plugin_channel | plugin_edit | empty_edit | midi_fx | unknown`.
- 규칙: 1행이 채널명이 아닌 뷰(`eq_channel, eq_menu, send_channel, send_menu, plugin_channel, plugin_edit, empty_edit, midi_fx`)에서는 `strips[].number/name`을 갱신하지 않는다. `strips[].value_text`는 `pan/track/unknown`에서만 갱신한다. 모드 전환 오버레이(`arameter:` 포함)가 덮은 열은 이전 번호·이름을 유지한다.

- [ ] **Step 1: 실패하는 테스트**

`tests/test_state.py` 끝에 추가:

```python
def lcd_ev(offset: int, text: str) -> P.LcdWrite:
    return P.LcdWrite(offset=offset, text=text.encode("latin1"))


def digit_evs(d: str) -> list[P.AssignDigit]:
    return [P.AssignDigit(index=0, char=d[0], dot=False), P.AssignDigit(index=1, char=d[1], dot=False)]


def apply(st: S.SurfaceState, evs, now: float = 100.0) -> S.SurfaceState:
    for ev in evs:
        st = S.reduce(st, ev, now)
    return st


ROW_NAMES = "15:DCl 16:DCl 17:DCl 18:DCl 19:DCl 20:DCl 21:SOu 24:Mas "
PAN_ROW2 = "0      0      0      0      0      0      0             "
EQ_ROW1 = "LoCutF LoCutS LoCutQ LCO/Of LoShF  LoShGa LoShQ  LSO/Of "
EQ_ROW2 = "20.0Hz 12     0.71   Off    75.0Hz 0.0 dB 1.00   On     "


def ready_pan() -> S.SurfaceState:
    return apply(S.initial_state(), [lcd_ev(0, ROW_NAMES + PAN_ROW2)] + digit_evs("PN"))


def test_view_pan_and_values():
    st = ready_pan()
    assert st.view.kind == "pan" and st.view.index is None
    assert st.strips[0].number == 15 and st.strips[0].value_text == "0"
    assert st.view.columns[7] == ("24:Mas ", "       ")


def test_view_eq_mixer_keeps_values_and_numbers_under_overlay():
    st = ready_pan()
    st = apply(st, digit_evs("E1") + [
        lcd_ev(0, ROW_NAMES + "20.0Hz" + " " * 50),
        lcd_ev(21, " EQ 1 Parameter: Low Cut Frequency"),
    ])
    assert (st.view.kind, st.view.index) == ("eq_mixer", 1)
    assert st.strips[0].value_text == "0"       # 2행은 EQ 값. 팬/볼륨 값으로 받지 않음
    assert st.strips[0].number == 15 and st.strips[4].number == 19   # 오버레이가 덮은 열은 이전 번호 유지
    assert st.view.columns[0] == ("15:DCl ", "20.0Hz ")


def test_view_eq_channel_columns_preserve_strips():
    st = apply(ready_pan(), digit_evs("EQ") + [lcd_ev(0, EQ_ROW1 + EQ_ROW2)])
    assert st.view.kind == "eq_channel"
    assert st.view.columns[1] == ("LoCutS ", "12     ") and st.view.columns[5] == ("LoShGa ", "0.0 dB ")
    assert st.strips[0].number == 15 and st.strips[0].name == "DCl" and st.strips[0].value_text == "0"


def test_view_plugin_kinds():
    st = ready_pan()
    st = apply(st, digit_evs("P1") + [lcd_ev(0, ROW_NAMES + "Cha EQ --     --     --     --     --     --            ")])
    assert (st.view.kind, st.view.index) == ("plugin_mixer", 1)
    st = apply(st, digit_evs("PL") + [lcd_ev(0, "Ins1Pl Ins2Pl Ins3Pl Ins4Pl Ins5Pl Ins6Pl Ins7Pl Ins8Pl "
                                                "Cha EQ --     --     --     --     --     --     --     ")])
    assert st.view.kind == "plugin_channel"
    st = apply(st, digit_evs("P1") + [lcd_ev(0, "LoCutS LoShGa Pea1Ga Pea2Ga Pea3Ga Pea4Ga HiShGa HiCutS "
                                                "12     0.0 dB 0.0 dB 0.0 dB 0.0 dB 0.0 dB 0.0 dB 24     ")])
    assert (st.view.kind, st.view.index, st.view.page) == ("plugin_edit", 1, None)
    assert st.strips[0].number == 15                                  # 편집 뷰 1행은 채널명이 아님
    header = 'Track 15 "15:Deluxe Classic" Ins.1 "Channe      Page 2/6'      # 56칸
    st = apply(st, [lcd_ev(0, header + "LoCutF LoShF  Peak1F Peak2F Peak3F Peak4F HiShF  HiCutF ")])
    assert st.view.kind == "plugin_edit" and st.view.page == (2, 6)
    assert st.view.header.startswith('Track 15 "15:Deluxe Classic" Ins.1')
    st = apply(st, [lcd_ev(0, "-      " * 8 + " " * 56)])
    assert st.view.kind == "empty_edit"
    st = apply(st, digit_evs("M1"))
    assert (st.view.kind, st.view.index) == ("midi_fx", 1)
    st = apply(st, digit_evs("10") + [lcd_ev(0, ROW_NAMES + " " * 56)])
    assert (st.view.kind, st.view.index) == ("plugin_mixer", 10)


def test_view_send_kinds_and_menus():
    st = ready_pan()
    for d, kind, idx in [("S1", "send_mixer", 1), ("SE", "send_channel", None), ("D1", "send_destlevel", 1),
                         ("S_", "send_menu", None), ("E_", "eq_menu", None), ("PN", "pan", None)]:
        st = apply(st, digit_evs(d))
        assert (st.view.kind, st.view.index) == (kind, idx), d


def test_view_unknown_display_keeps_spec1_behaviour():
    st = apply(S.initial_state(), [lcd_ev(0, ROW_NAMES + PAN_ROW2)])      # 2자리 표시가 아직 없음
    assert st.view.kind == "pan" and st.strips[0].number == 15 and st.strips[0].value_text == "0"
    st = apply(st, digit_evs("tr") + [lcd_ev(56, "+0.0dB ")])
    assert st.view.kind == "unknown" and st.strips[0].value_text == "+0.0dB"


def test_fixture_assign1_view_kinds():
    seen, st = set(), S.initial_state()
    for ts, _, data in P.load_fixture(Path(__file__).parent / "fixtures" / "mcu" / "cap_assign1.log"):
        st = S.reduce(st, P.decode(data), ts)
        seen.add(st.view.kind)
    assert {"pan", "eq_mixer", "eq_channel", "eq_menu", "send_mixer", "send_channel", "send_menu",
            "plugin_mixer", "plugin_channel", "plugin_edit", "midi_fx"} <= seen
    assert st.view.kind == "pan"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_state.py -q`
Expected: 새 테스트 7개 실패(`AttributeError: 'SurfaceState' object has no attribute 'view'`).

- [ ] **Step 3: 구현**

`state.py` 상단 상수 뒤(`_TRANSPORT` 다음)에 추가:

```python
OVERLAY_MARK = "arameter:"   # "EQ 1 Parameter: …", "Pan/Surround parameter:" 모드 전환 오버레이 공통 조각
_PAGE_RE = re.compile(r"Page\s*(\d+)/(\d+)")
_NO_NAME_VIEWS = frozenset({"eq_channel", "eq_menu", "send_channel", "send_menu", "plugin_channel",
                            "plugin_edit", "empty_edit", "midi_fx"})          # 1행이 채널명이 아닌 뷰
_VALUE_VIEWS = frozenset({"pan", "track", "unknown"})                        # 2행이 볼륨·팬 값인 뷰
```

`Assignment` 바로 뒤에 `View` 추가:

```python
@dataclass(frozen=True)
class View:
    kind: str = "pan"
    index: int | None = None                     # 센드 번호, 플러그인 슬롯, EQ 파라미터 번호
    page: tuple[int, int] | None = None          # 편집 뷰 헤더 `Page 2/6`
    header: str = ""                             # NAME 모드 1행(트랙·인서트·플러그인 이름)
    columns: tuple[tuple[str, str], ...] = field(default_factory=lambda: tuple(("       ", "       ") for _ in range(8)))
```

`SurfaceState`에 필드 추가(`connection` 앞):

```python
    view: View = View()
```

`parse_column` 뒤에 추가:

```python
def lcd_columns(lcd: tuple[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple((lcd[0][i * COL_W:(i + 1) * COL_W], lcd[1][i * COL_W:(i + 1) * COL_W]) for i in range(LCD_COLS))


def classify_view(display: str, lcd: tuple[str, str], mode: str | None) -> tuple[str, int | None]:
    """2자리 표시 + LCD 레이아웃 → (뷰 종류, 번호). 실측 코드: PN E1 EQ E_ S1 SE D1 S_ P1..P9 10..16 PL M1."""
    d = (display + "  ")[:2]
    row1, row2 = lcd
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
    if d == "PL":
        return "plugin_channel", None
    if d[0] == "M" and d[1].isdigit():
        return "midi_fx", int(d[1])
    slot = int(d[1]) if d[0] == "P" and d[1].isdigit() else (int(d) if d.strip().isdigit() else None)
    if slot is not None:
        if all(c.strip() == "-" for c in cols) and not row2.strip():
            return "empty_edit", slot
        if any(parse_column(c)[0] is not None for c in cols):
            return "plugin_mixer", slot
        if row1.startswith("Ins1Pl"):
            return "plugin_channel", slot
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
```

`_strips_from_lcd`를 다음으로 교체:

```python
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
```

`reduce`의 `LcdWrite` 분기 끝부분을 다음으로 교체:

```python
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
```

`Led` 분기의 `if n in _ASSIGN:` 블록을 다음으로 교체(모드 LED가 바뀌면 뷰도 다시 판정):

```python
        if n in _ASSIGN:
            mode = _ASSIGN[n] if ev.on else (None if st.assignment.mode == _ASSIGN[n] else st.assignment.mode)
            assignment = replace(st.assignment, mode=mode)
            return replace(st, assignment=assignment, view=_view_from(assignment.display, st.lcd, mode))
```

`AssignDigit` 분기를 다음으로 교체:

```python
    if isinstance(ev, P.AssignDigit):
        disp = list(st.assignment.display)
        disp[ev.index] = ev.char
        assignment = replace(st.assignment, display="".join(disp))
        return replace(st, assignment=assignment,
                       view=_view_from(assignment.display, st.lcd, assignment.mode))
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_state.py tests/test_commands.py tests/test_surface.py -q`
Expected: 모두 PASS. 스펙 1 테스트가 깨지면 원인은 `_VALUE_VIEWS`/`_NO_NAME_VIEWS` 범위다. 설치 애니메이션 중 2자리 표시가 `PN`이 아니어도 `unknown`은 값·이름을 모두 갱신하므로 스펙 1 동작이 유지되어야 한다.

- [ ] **Step 5: 커밋**

```bash
git add src/logic_mcp/mcu/state.py tests/test_state.py
git commit -m "feat(state): 어사인먼트 뷰 판정(View) — 2자리 코드·LCD 레이아웃, 열·헤더·페이지, 스트립 갱신 범위 제한

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: 가짜 Logic(어사인먼트)과 ModeDriver

**Files:**
- Create: `tests/fake_assign.py`, `src/logic_mcp/logic/modes.py`
- Modify: `src/logic_mcp/logic/commands.py` (`Commands.modes`, `mixer_pan` 복귀), `tests/test_commands.py`
- Test: `tests/test_modes.py`

**Interfaces:**
- Consumes: Task 1 `vpot_turn_messages`, Task 2 `parse_value/Value`, Task 3 `SurfaceState.view`, `S.OVERLAY_MARK`, `S.COL_W`.
- Produces:
  - `tests/fake_assign.py`: `Param`, `Track`, `FakeLogic(fake, tracks, clock)` with `sleep(s)`, `redraw()`, `refuse: set[int]`, `blink_on`, `plugin_list`, `tracks`, `view`, `selected`; `make_assign_logic(tracks=None) -> (Surface, FakeTransport, FakeLogic)`; `default_tracks()`; `PLUGIN_LIST`(인덱스 6 = Compressor, 7 = Channel EQ).
  - `logic/modes.py`: `ModeError(step, expected, observed)`; `ModeDriver(surface, sleep)` with `view`, `focus(ch)`, `enter(kind)`, `page_to(page)`, `page_until(pred, forward, max_steps)`, `slot_to(slot)`, `tick(ch, steps) -> bool`, `press_vpot(ch) -> bool`, `fader(ch, raw) -> int | None`, `flip(on)`, `toggle_name_value()`, `hold_menu(button, vpot)`, `read_column(ch) -> (name, Value)`, `read_value(ch) -> Value`, `settle_overlay()`, `settle_smart()`, `leave(keep_select=False)`, `leave_safely()`, `last_leave_error`.
  - `Commands.modes: ModeDriver` (같은 `sleep` 공유). `mixer_pan`은 Flip이 켜져 있거나 PAN이 아니면 `modes.leave_safely()` 뒤 진행.

- [ ] **Step 1: 가짜 Logic 작성**

`tests/fake_assign.py`:

```python
"""어사인먼트 모드(PAN·EQ·PLUG-IN·FLIP)를 흉내 내는 가짜 Logic. FakeTransport.replies에 꽂아 쓴다.
2자리 코드·레이아웃은 스펙 2 부록 A 실측을 따르고, 값 모델(틱당 변화·범위)은 단순화했다.
시간은 sleep()으로만 흐른다: 오버레이 재묘사(2.0초 뒤)와 깜박임 위상이 sleep에서 처리된다."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from logic_mcp.mcu import protocol as P
from logic_mcp.mcu.surface import Surface
from tests.fakes import FakeTransport

OVERLAY_S = 2.0
LCD_SYSEX = bytes.fromhex("F0 00 00 66 14 12")
MAX = P.MAX_FADER
SLOPES = ("6", "12", "18", "24", "36", "48")
PLUGIN_LIST = ["--", "Parametric EQ", "Low Pass Filter", "High Pass Filter", "Chorus", "Flanger",
               "Compressor", "Channel EQ", "Tuner", "Limiter", "Noise Gate", "Space Designer", "DeEsser"]


def lcd_write(offset: int, text: str) -> bytes:
    return LCD_SYSEX + bytes([offset]) + text.encode("latin1") + b"\xF7"


def digits(d: str) -> list[bytes]:
    """2자리 표시: CC 0x4B(왼쪽), 0x4A(오른쪽). 문자 코드는 ASCII & 0x3F (protocol.seg_char의 역)."""
    return [bytes([0xB0, 0x4B, ord(d[0].upper()) & 0x3F]), bytes([0xB0, 0x4A, ord(d[1].upper()) & 0x3F])]


def col(text: str) -> str:
    return text[:7].ljust(7)


def fader_echo(ch: int, raw: int) -> bytes:
    return bytes([0xE0 | ch, raw & 0x7F, raw >> 7])


@dataclass
class Param:
    short: str                  # 6자 축약명(열)
    name: str                   # 전체 이름(오버레이)
    kind: str                   # log | linear | enum
    lo: float = 0.0
    hi: float = 1.0
    value: float = 0.0          # enum이면 선택지 인덱스
    options: tuple[str, ...] = ()
    unit: str = ""              # Hz | dB | "" (enum이면 전체 값 접미사, 예 " dB/Oct")
    step: float = 1.0           # 틱당 변화: log면 비율, linear면 가산, enum이면 1

    def text(self) -> str:
        """7칸 열 텍스트. 실측 형식: 20.0Hz / 100 Hz / 1040Hz / 20000 / 0.0 dB / 0.71 / On."""
        if self.kind == "enum":
            return col(self.options[int(self.value)])
        v = self.value
        if self.unit == "Hz":
            s = f"{v:.1f}Hz" if v < 100 else f"{v:.0f} Hz" if v < 1000 else f"{v:.0f}Hz" if v < 10000 else f"{v:.0f}"
        elif self.unit == "dB":
            s = f"{v:.1f} dB"
        else:
            s = f"{v:.2f}"
        return col(s)

    def full(self) -> str:
        """오버레이 전체 값(단위 포함)."""
        if self.kind == "enum":
            return self.options[int(self.value)] + self.unit
        if self.unit == "Hz":
            return f"{self.value:.1f} Hz"
        if self.unit == "dB":
            return f"{self.value:+.1f} dB"
        return f"{self.value:.2f}"

    def raw(self) -> int:
        if self.kind == "enum":
            return round(MAX * self.value / max(1, len(self.options) - 1))
        if self.kind == "log":
            return round(MAX * math.log(self.value / self.lo) / math.log(self.hi / self.lo))
        return round(MAX * (self.value - self.lo) / (self.hi - self.lo))

    def set_raw(self, raw: int) -> bool:
        """페이더 위치 → 값. 바뀌었으면 True(Logic은 바뀔 때만 에코)."""
        before = self.value
        f = max(0, min(MAX, raw)) / MAX
        if self.kind == "enum":
            self.value = round(f * (len(self.options) - 1))
        elif self.kind == "log":
            self.value = round(self.lo * (self.hi / self.lo) ** f, 1)
        else:
            self.value = round(self.lo + f * (self.hi - self.lo), 2)
        return self.value != before

    def tick(self, n: int) -> None:
        if self.kind == "enum":
            self.value = max(0, min(len(self.options) - 1, self.value + n))
        elif self.kind == "log":
            self.value = round(max(self.lo, min(self.hi, self.value * self.step ** n)), 1)
        else:
            self.value = round(max(self.lo, min(self.hi, self.value + self.step * n)), 2)


_EQ_BANDS = [  # (이름, (freq, gain|slope, q, on) 축약, 기본 freq, 기본 gain|slope, 기본 q, 기본 on, 슬로프 밴드?)
    ("Low Cut", ("LoCutF", "LoCutS", "LoCutQ", "LCO/Of"), 20.0, 12, 0.71, False, True),
    ("Low Shelf", ("LoShF", "LoShGa", "LoShQ", "LSO/Of"), 75.0, 0.0, 1.00, True, False),
    ("Peak 1", ("Peak1F", "Pea1Ga", "Peak1Q", "Pe1On/"), 100.0, 0.0, 0.60, True, False),
    ("Peak 2", ("Peak2F", "Pea2Ga", "Peak2Q", "Pe2On/"), 250.0, 0.0, 0.30, True, False),
    ("Peak 3", ("Peak3F", "Pea3Ga", "Peak3Q", "Pe3On/"), 1040.0, 0.0, 0.41, True, False),
    ("Peak 4", ("Peak4F", "Pea4Ga", "Peak4Q", "Pe4On/"), 2500.0, 0.0, 0.20, True, False),
    ("High Shelf", ("HiShF", "HiShGa", "HiShQ", "HSO/Of"), 7500.0, 0.0, 1.00, True, False),
    ("High Cut", ("HiCutF", "HiCutS", "HiCutQ", "HCO/Of"), 20000.0, 24, 0.71, False, True),
]


def channel_eq() -> list[list[Param]]:
    """8밴드 × (freq, gain|slope, q, on). 축약명은 밴드 1~6 실측, 7·8은 같은 규칙으로 지었다."""
    bands = []
    for name, (f, g, q, o), freq, gain, qv, on, is_slope in _EQ_BANDS:
        gp = (Param(g, f"{name} Slope", "enum", options=SLOPES, value=SLOPES.index(str(gain)), unit=" dB/Oct")
              if is_slope else Param(g, f"{name} Gain", "linear", -24.0, 24.0, gain, unit="dB", step=0.5))
        bands.append([Param(f, f"{name} Frequency", "log", 20.0, 20000.0, freq, unit="Hz", step=1.08), gp,
                      Param(q, f"{name} Q", "linear", 0.1, 10.0, qv, step=0.05),
                      Param(o, f"{name} On/Off", "enum", options=("Off", "On"), value=1 if on else 0)])
    return bands


def channel_eq_edit(bands: list[list[Param]]) -> list[Param]:
    """편집 뷰 순서(실측: 1페이지 슬로프/게인, 2페이지 주파수 …). 같은 Param 객체를 공유한다."""
    flat = [b[1] for b in bands] + [b[0] for b in bands] + [b[2] for b in bands] + [b[3] for b in bands]
    flat += [Param("Analyz", "Analyzer", "enum", options=("Off", "On"), value=0),
             Param("MasGai", "Master Gain", "linear", -24.0, 24.0, 0.0, unit="dB", step=0.5)]
    return flat


def compressor() -> list[Param]:
    return [Param("Thresh", "Threshold", "linear", -60.0, 0.0, -20.0, unit="dB", step=0.5),
            Param("Ratio", "Ratio", "linear", 1.0, 30.0, 2.0, step=0.1),
            Param("Attack", "Attack", "linear", 0.0, 200.0, 20.0, step=1.0),
            Param("Releas", "Release", "linear", 5.0, 5000.0, 100.0, step=5.0),
            Param("Knee", "Knee", "linear", 0.0, 1.0, 0.0, step=0.05),
            Param("MakeUp", "Make Up", "linear", 0.0, 40.0, 0.0, unit="dB", step=0.5),
            Param("Mix", "Mix", "linear", 0.0, 100.0, 100.0, step=1.0),
            Param("Circui", "Circuit Type", "enum", value=0,
                  options=("Platinum", "Studio VCA", "Studio FET", "Classic VCA", "Vintage VCA", "Vintage FET", "Vintage Opto")),
            Param("AutoGa", "Auto Gain", "enum", options=("Off", "-12 dB", "0 dB"), value=0),
            Param("Limit", "Limiter", "enum", options=("Off", "On"), value=0)]


def generic(name: str) -> list[Param]:
    """그 밖의 플러그인: Distortion 실측(Drive/Tone/Output) 모양."""
    return [Param("Drive", f"{name} Drive", "linear", 0.0, 10.0, 10.0, step=0.1),
            Param("Tone", f"{name} Tone", "linear", 0.0, 2000.0, 1100.0, step=10.0),
            Param("Output", f"{name} Output", "linear", -20.0, 20.0, -0.5, unit="dB", step=0.5)]


@dataclass
class Track:
    number: int
    name: str
    inserts: dict[int, str | None] = field(default_factory=lambda: {i: None for i in range(1, 16)})
    params: dict[int, list[Param]] = field(default_factory=dict)   # 슬롯 → 편집 뷰 파라미터
    eq: list[list[Param]] | None = None                           # Channel EQ 밴드(어느 슬롯에 있든)
    bypassed: set[int] = field(default_factory=set)

    def insert(self, slot: int, name: str) -> None:
        if self.inserts[slot] == "Channel EQ":
            self.eq = None
        self.inserts[slot] = name
        if name == "Channel EQ":
            self.eq = channel_eq()
            self.params[slot] = channel_eq_edit(self.eq)
        elif name == "Compressor":
            self.params[slot] = compressor()
        else:
            self.params[slot] = generic(name)

    def remove(self, slot: int) -> None:
        if self.inserts[slot] == "Channel EQ":
            self.eq = None
        self.inserts[slot] = None
        self.params.pop(slot, None)
        self.bypassed.discard(slot)

    def first_empty(self) -> int | None:
        return next((i for i in range(1, 16) if self.inserts[i] is None), None)


class FakeLogic:
    def __init__(self, fake: FakeTransport, tracks: list[Track], clock) -> None:
        self.fake, self.tracks, self.clock = fake, tracks, clock
        self.view = "pan"
        self.selected = 0
        self.slot = 1
        self.page = 1
        self.flip = False
        self.name_mode = False
        self.shift = False
        self.blink_on = True
        self.mode_note = P.Note.PAN
        self.before_midi = "plugin_mixer"
        self.pre: dict[int, int] = {}                  # 스트립 → 미리 선택 위치(반 항목 단위, 0..2·(목록-1)로 포화)
        self.pending: list[float] = []                 # 재묘사 예정 시각
        self.plugin_list = list(PLUGIN_LIST)
        self.refuse: set[int] = set()                  # 반응하지 않을 노트(고장 흉내)
        fake.replies = self.replies

    # ---------- 시간 ----------
    def sleep(self, s: float) -> None:
        """드라이버의 sleep 훅. 시간을 보내고, 만기된 재묘사와 깜박임 위상을 처리한다."""
        self.fake.now += s
        self.blink_on = not self.blink_on
        due = [t for t in self.pending if t <= self.clock()]
        if due:
            self.pending = [t for t in self.pending if t > self.clock()]
            self.redraw()
        elif self.pre and self.view == "plugin_mixer":
            self.redraw()

    def boot(self) -> None:
        self._emit([P.button_down(P.Note.PAN), P.button_down(P.Note.BEATS_LED), P.button_down(P.Note.SELECT)])
        self._emit([fader_echo(ch, 12443) for ch in range(8)])
        self.redraw()

    # ---------- 화면 ----------
    def _emit(self, msgs: list[bytes]) -> None:
        for m in msgs:
            self.fake.on_message(self.clock(), m)

    def _track(self, ch: int) -> Track | None:
        return self.tracks[ch] if ch < len(self.tracks) else None

    def _names_row(self) -> str:
        return "".join(col(f"{t.number}:{t.name}") for t in self.tracks[:8]).ljust(56)

    def _slot_digits(self) -> str:
        return f"P{self.slot}" if self.slot <= 9 else str(self.slot)

    def _abbrev(self, name: str | None, slot: int, track: Track) -> str:
        if name is None:
            return col("--")
        return col(("*" if slot in track.bypassed else "") + name.replace(" ", "")[:6])

    def _pre_index(self, ch: int) -> int:
        return self.pre[ch] // 2                                # 1항목 = 2틱(실측)

    def _edit_params(self) -> list[Param]:
        return self.tracks[self.selected].params.get(self.slot, [])

    def _edit_pages(self) -> int:
        return max(1, math.ceil(len(self._edit_params()) / 8))

    def _edit_page(self) -> list[Param]:
        return self._edit_params()[(self.page - 1) * 8:self.page * 8]

    def _column_param(self, ch: int) -> Param | None:
        t = self.tracks[self.selected]
        if self.view == "eq_channel" and t.eq is not None:
            ps = [p for band in t.eq[2 * self.page - 2:2 * self.page] for p in band]
            return ps[ch] if ch < len(ps) else None
        if self.view == "plugin_edit":
            ps = self._edit_page()
            return ps[ch] if ch < len(ps) else None
        return None

    def _rows(self) -> tuple[str, str, str]:
        """정착 화면 (1행, 2행, 2자리)."""
        t = self.tracks[self.selected]
        if self.view == "pan":
            return self._names_row(), "".join(col("0") for _ in self.tracks[:8]).ljust(56), "PN"
        if self.view == "eq_mixer":
            r2 = "".join(tr.eq[0][0].text() if tr.eq else col("") for tr in self.tracks[:8]).ljust(56)
            return self._names_row(), r2, "E1"
        if self.view == "eq_channel":
            ps = [p for band in t.eq[2 * self.page - 2:2 * self.page] for p in band]
            return "".join(col(p.short) for p in ps).ljust(56), "".join(p.text() for p in ps).ljust(56), "EQ"
        if self.view == "plugin_mixer":
            cells = []
            for ch, tr in enumerate(self.tracks[:8]):
                if ch in self.pre:
                    cells.append(self._abbrev(self.plugin_list[self._pre_index(ch)], 0, tr) if self.blink_on else col(""))
                else:
                    cells.append(self._abbrev(tr.inserts[self.slot], self.slot, tr))
            return self._names_row(), "".join(cells).ljust(56), self._slot_digits()
        if self.view == "plugin_channel":
            r1 = "".join(col(f"Ins{i}Pl") for i in range(1, 9))
            r2 = "".join(self._abbrev(t.inserts[i], i, t) for i in range(1, 9))
            return r1, r2, "PL"
        if self.view == "plugin_edit":
            ps = self._edit_page()
            names = "".join(col(p.short) for p in ps).ljust(56)
            if self.name_mode:
                header = f'Track {t.number} "{t.number}:{t.name}" Ins.{self.slot} "{t.inserts[self.slot]} (s/s)"'
                return header[:48].ljust(48) + f"Page {self.page}/{self._edit_pages()}".rjust(8), names, self._slot_digits()
            return names, "".join(p.text() for p in ps).ljust(56), self._slot_digits()
        if self.view in ("empty_edit", "midi_fx"):
            return "-      " * 8, " " * 56, "M1" if self.view == "midi_fx" else self._slot_digits()
        raise AssertionError(self.view)

    def redraw(self, overlay: tuple[int, str, str] | None = None, mode_overlay: str | None = None) -> None:
        """정착 화면을 그린다. 오버레이가 있으면 오버레이 판을 지금 그리고 2.0초 뒤 재묘사를 예약한다."""
        r1, r2, d = self._rows()
        if overlay is None and mode_overlay is None:
            self._emit([lcd_write(0, r1 + r2)] + digits(d))
            return
        o1, o2 = r1, r2
        if mode_overlay:
            o1 = r1[:56 - len(mode_overlay)] + mode_overlay
        if overlay:
            ch, name, value = overlay
            start = min(ch * 7, 56 - 21)
            o1 = o1[:start] + name[:21].ljust(21) + o1[start + 21:]
            o2 = r2[:start] + value[:21].ljust(21) + r2[start + 21:]
        self._emit([lcd_write(0, o1[:56] + o2[:56])] + digits(d))
        self.pending.append(self.clock() + OVERLAY_S)

    # ---------- 입력 ----------
    def replies(self, data: bytes) -> list[bytes]:
        st = data[0] & 0xF0
        if st == 0x90:
            note, on = data[1], data[2] != 0
            if note in self.refuse:
                return []
            if note == P.Note.SHIFT:
                self.shift = on
            elif on:
                self._button(note)
        elif st == 0xB0 and 0x10 <= data[1] <= 0x17:
            v = data[2]
            self._vpot(data[1] - 0x10, (v & 0x3F) * (-1 if v & 0x40 else 1))
        elif st == 0xE0 and (data[0] & 0x0F) < 8:
            self._fader(data[0] & 0x0F, data[1] | (data[2] << 7))
        return []

    def _set_mode(self, view: str, note: int) -> None:
        if self.mode_note != note:
            self._emit([P.button_up(self.mode_note), P.button_down(note)])
            self.mode_note = note
        self.view, self.page = view, 1
        self.pre.clear()

    def _button(self, note: int) -> None:
        N = P.Note
        if N.SELECT <= note < N.SELECT + 8:
            old, self.selected = self.selected, note - N.SELECT
            self._emit([P.button_up(N.SELECT + old), P.button_down(N.SELECT + self.selected)])
            self.pre.clear()
            self.redraw()
        elif note == N.PAN:
            self._set_mode("pan", N.PAN)
            self.redraw(mode_overlay="    Pan/Surround parameter:")
        elif note == N.EQ:
            if self.view == "eq_mixer":
                t = self.tracks[self.selected]
                if t.eq is None and t.first_empty():
                    t.insert(t.first_empty(), "Channel EQ")      # 실측: 채널 뷰 진입이 Channel EQ 삽입
                self.view, self.page = "eq_channel", 1
                self.redraw()
            elif self.view == "eq_channel":
                self.view = "eq_mixer"
                self.redraw(mode_overlay=" EQ 1 Parameter: Low Cut Frequency")
            else:
                self._set_mode("eq_mixer", N.EQ)
                self.redraw(mode_overlay=" EQ 1 Parameter: Low Cut Frequency")
        elif note == N.PLUGIN:
            if self.view == "plugin_mixer":
                self.view = "plugin_channel"
            elif self.view in ("plugin_channel", "plugin_edit", "empty_edit", "midi_fx"):
                self.view = "plugin_mixer"
            else:
                self._set_mode("plugin_mixer", N.PLUGIN)
            self.pre.clear()
            self.redraw()
        elif note == N.CURSOR_RIGHT:
            self._page(+1)
        elif note == N.CURSOR_LEFT:
            self._page(-1)
        elif note == N.CURSOR_DOWN:
            self._slot(+1)
        elif note == N.CURSOR_UP:
            self._slot(-1)
        elif note == N.FLIP:
            self.flip = not self.flip
            self._emit([P.button_down(N.FLIP) if self.flip else P.button_up(N.FLIP)])
            if self.flip:
                self._emit([fader_echo(ch, p.raw() if (p := self._column_param(ch)) else 0) for ch in range(8)])
            else:
                self._emit([fader_echo(ch, 12443) for ch in range(8)])
        elif note == N.NAME_VALUE:
            self.name_mode = not self.name_mode
            self.redraw()
        elif N.VPOT_PUSH <= note < N.VPOT_PUSH + 8:
            self._push(note - N.VPOT_PUSH)

    def _page(self, delta: int) -> None:
        if self.view == "eq_channel":
            self.page = max(1, min(4, self.page + delta))
        elif self.view == "plugin_edit":
            self.page = max(1, min(self._edit_pages(), self.page + delta))
        else:
            return
        self.redraw()

    def _slot(self, delta: int) -> None:
        if self.view == "midi_fx":
            if delta > 0:
                self.view, self.slot = self.before_midi, 1
        elif self.view in ("plugin_mixer", "plugin_edit", "empty_edit"):
            new = self.slot + delta
            if new < 1:
                self.before_midi, self.view = self.view, "midi_fx"      # 실측: P1에서 ▲ → M1
            else:
                self.slot = min(15, new)
                if self.view in ("plugin_edit", "empty_edit"):
                    self.view = "plugin_edit" if self.tracks[self.selected].inserts[self.slot] else "empty_edit"
                    self.page = 1
        else:
            return
        self.redraw()

    def _vpot(self, ch: int, ticks: int) -> None:
        if self.view == "plugin_mixer":
            t = self._track(ch)
            if t is None:
                return
            if ch not in self.pre:                                      # 실측: 다른 스트립의 미리 선택은 취소됨
                self.pre = {ch: 2 * self.plugin_list.index(t.inserts[self.slot] or "--")}
            self.pre[ch] = max(0, min(2 * (len(self.plugin_list) - 1), self.pre[ch] + ticks))
            self.redraw(overlay=(ch, f"Insert {self.slot} Plug-in", self.plugin_list[self._pre_index(ch)]))
            return
        if self.view == "eq_mixer":
            t = self._track(ch)
            p = t.eq[0][0] if (t and t.eq) else None
        else:
            p = self._column_param(ch)
        if p is None:
            return
        p.tick(ticks)
        self.redraw(overlay=(ch, p.name, p.full()))

    def _push(self, ch: int) -> None:
        if self.view != "plugin_mixer":
            return                                                      # 실측: 편집 뷰 누름은 기본값 리셋 안 함
        t = self._track(ch)
        if t is None:
            return
        if self.shift:
            t.bypassed ^= {self.slot}
            self.redraw()
            return
        if ch in self.pre:
            name = self.plugin_list[self._pre_index(ch)]
            self.pre.clear()
            self.selected = ch
            if name == "--":
                t.remove(self.slot)
                self.view = "empty_edit"
            else:
                if name != t.inserts[self.slot]:
                    t.insert(self.slot, name)                           # 같은 플러그인 확인은 값 보존(실측)
                self.view, self.page = "plugin_edit", 1
            self.redraw()
        elif t.inserts[self.slot]:
            self.selected = ch
            self.view, self.page = "plugin_edit", 1
            self.redraw()

    def _fader(self, ch: int, raw: int) -> None:
        if not self.flip or raw == 0:                                   # raw 0 무시(실측 사례)
            return
        p = self._column_param(ch)
        if p is None or not p.set_raw(raw):
            return
        self._emit([fader_echo(ch, p.raw())])
        self.redraw(overlay=(ch, p.name, p.full()))


def default_tracks() -> list[Track]:
    return [Track(15, "DCl"), Track(16, "DCl"), Track(17, "DCl"), Track(18, "DCl"),
            Track(19, "DCl"), Track(20, "DCl"), Track(21, "SOu"), Track(24, "Mas")]


def make_assign_logic(tracks: list[Track] | None = None) -> tuple[Surface, FakeTransport, FakeLogic]:
    fake = FakeTransport()
    surface = Surface(fake, clock=lambda: fake.now + 1.0, tick_interval=0.01)
    logic = FakeLogic(fake, tracks or default_tracks(), surface.clock)
    logic.boot()
    fake.now += 1.0                 # 조용 1초 → ready
    surface.tick()
    assert surface.state.connection.state == "ready"
    return surface, fake, logic
```

주의: 가짜는 받은 메시지에 대한 응답을 **Surface 클락 시각으로** 직접 `on_message`에 넣고 `replies`는 빈 목록을 돌려준다(실제 포트처럼 ts == clock).

- [ ] **Step 2: 실패하는 테스트**

`tests/test_modes.py`:

```python
import pytest

from logic_mcp.logic.modes import ModeDriver, ModeError
from logic_mcp.mcu import protocol as P
from tests.fake_assign import make_assign_logic


def make():
    surface, fake, logic = make_assign_logic()
    return ModeDriver(surface, sleep=logic.sleep), surface, fake, logic


def test_focus_enter_eq_channel_and_leave_restores_pan_and_selection():
    d, surface, fake, logic = make()
    d.focus(2)
    assert surface.state.strips[2].select and logic.selected == 2
    d.enter("eq_channel")
    assert surface.state.view.kind == "eq_channel" and logic.view == "eq_channel"
    assert surface.state.view.columns[0][0] == "LoCutF "
    assert logic.tracks[2].eq is not None                       # 채널 뷰 진입이 Channel EQ를 삽입
    d.leave()
    assert surface.state.view.kind == "pan" and logic.view == "pan"
    assert logic.selected == 0 and surface.state.strips[0].select   # 이전 선택 복원


def test_enter_waits_out_mode_overlay():
    d, surface, fake, logic = make()
    d.enter("eq_mixer")
    assert "Parameter" not in surface.state.lcd[0]
    assert surface.state.view.columns[4][0] == "19:DCl "


def test_read_value_uses_overlay_then_column_after_redraw():    # Review Focus 1
    d, surface, fake, logic = make()
    d.focus(0)
    d.enter("eq_channel")
    assert d.tick(0, 1)
    v = d.read_value(0)
    assert v.number == 21.6 and v.unit == "Hz" and v.text == "21.6 Hz"
    assert surface.state.lcd[0].startswith("Low Cut Frequency")
    d.settle_overlay()
    name, v2 = d.read_column(0)
    assert name == "LoCutF" and v2.number == 21.6 and v2.text == "21.6Hz"


def test_read_column_retries_blank_blink():                     # Review Focus 2
    d, surface, fake, logic = make()
    d.focus(1)
    d.enter("plugin_mixer")
    d.tick(1, 2)
    d.settle_overlay()
    logic.blink_on = False
    logic.redraw()
    assert surface.state.view.columns[1][1].strip() == ""
    name, v = d.read_column(1)
    assert v.text == "Parame"                                    # 가짜의 6자 축약("Parametric EQ")


def test_tick_splits_at_63_and_fader_never_sends_zero():        # Review Focus 5
    d, surface, fake, logic = make()
    d.focus(0)
    d.enter("eq_channel")
    fake.sent.clear()
    d.tick(1, 70)
    assert [m for m in fake.sent if m[0] == 0xB0] == [P.vpot_turn(1, 63), P.vpot_turn(1, 7)]
    d.flip(True)
    fake.sent.clear()
    d.fader(0, 0)
    assert bytes([0xE0, 1, 0]) in fake.sent and bytes([0xE0, 0, 0]) not in fake.sent


def test_flip_moves_faders_and_fader_sets_value():
    d, surface, fake, logic = make()
    d.focus(0)
    d.enter("eq_channel")
    d.flip(True)
    assert surface.state.assignment.flip
    assert surface.state.strips[0].fader_raw == 0 and surface.state.strips[7].fader_raw == 16383   # 20 Hz 최소, On 최대
    echoed = d.fader(0, 8192)
    assert echoed is not None and abs(logic.tracks[0].eq[0][0].value - 632.5) < 5
    assert d.read_value(0).unit == "Hz"
    d.leave()
    assert not surface.state.assignment.flip and surface.state.view.kind == "pan"


def test_enter_other_family_goes_through_pan_and_cancels_preselect():
    d, surface, fake, logic = make()
    d.focus(1)
    d.enter("plugin_mixer")
    d.tick(1, 2)
    assert logic.pre
    d.enter("eq_channel")
    assert P.button_down(P.Note.PAN) in fake.sent and not logic.pre
    assert surface.state.view.kind == "eq_channel"


def test_mode_error_when_logic_ignores_button_and_leave_safely():
    d, surface, fake, logic = make()
    logic.refuse.add(P.Note.EQ)
    with pytest.raises(ModeError):
        d.enter("eq_mixer")
    d.leave_safely()
    assert surface.state.view.kind == "pan" and d.last_leave_error == ""


def test_slot_page_name_value_navigation_and_restore():
    d, surface, fake, logic = make()
    logic.tracks[0].insert(2, "Compressor")
    d.focus(0)
    d.enter("plugin_mixer")
    d.slot_to(2)
    assert surface.state.view.index == 2 and surface.state.view.columns[0][1] == "Compre "
    assert d.press_vpot(0) and surface.state.view.kind == "plugin_edit"
    d.toggle_name_value()
    assert surface.state.view.page == (1, 2) and 'Ins.2 "Compressor (s/s)"' in surface.state.view.header
    d.page_to(2)
    assert surface.state.view.page == (2, 2)
    d.toggle_name_value()
    assert surface.state.view.columns[0] == ("AutoGa ", "Off    ")
    d.toggle_name_value()
    d.leave()
    assert surface.state.view.kind == "pan" and logic.name_mode is False   # NAME 모드도 되돌림


def test_slot_up_from_one_reaches_midi_fx_and_back():
    d, surface, fake, logic = make()
    d.enter("plugin_mixer")
    with pytest.raises(ModeError):
        d.slot_to(0)
    assert surface.state.view.kind == "midi_fx"
    d.leave()
    assert surface.state.view.kind == "pan"
```

`tests/test_commands.py` 끝에 추가:

```python
from tests.fake_assign import make_assign_logic


def test_mixer_pan_leaves_assign_mode_and_flip_first():
    surface, fake, logic = make_assign_logic()
    cmds = Commands(surface, FaderTable.load(), sleep=logic.sleep, logic_running=lambda: True)
    cmds.modes.enter("eq_channel")
    cmds.modes.flip(True)
    r = cmds.mixer_pan(1, None, 0)
    assert P.button_down(P.Note.FLIP) in fake.sent and P.button_down(P.Note.PAN) in fake.sent
    assert surface.state.view.kind == "pan" and not surface.state.assignment.flip
    assert r.verified == "skipped" and r.note == "already"        # 가짜의 팬 값 0
```

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest tests/test_modes.py tests/test_commands.py -q`
Expected: `ModuleNotFoundError: logic_mcp.logic.modes`, `AttributeError: modes`.

- [ ] **Step 4: ModeDriver 구현**

`src/logic_mcp/logic/modes.py`:

```python
"""어사인먼트 모드 전환·페이지·미리 선택·Flip을 소유한다. 스펙 2 명령은 focus/enter로 들어와 leave()로 나간다.
긴 고정 대기(오버레이 2.0초)는 주입된 sleep으로, 짧은 피드백 대기는 Surface.wait_for로 한다."""
from __future__ import annotations

import time
from collections.abc import Callable

from ..mcu import protocol as P
from ..mcu import state as S
from ..mcu.surface import Surface
from .values import Value, parse_value

OVERLAY_S = 2.0          # 모드 전환·값 변경 오버레이 지속(실측)
MODE_TIMEOUT = 0.6
LED_TIMEOUT = 0.5
FADER_TIMEOUT = 0.8
FEEDBACK_TIMEOUT = 0.6
PRESS_HOLD_S = 0.03
HOLD_MENU_S = 0.4
BLINK_RETRY_S = 0.4      # 미리 선택 깜박임 반주기(≈0.75초)보다 짧게
OVERLAY_WIDTH = 21       # 오버레이가 쓰는 열 3칸
_FAMILY_BUTTON = {"eq": P.Note.EQ, "plugin": P.Note.PLUGIN, "send": P.Note.SEND}
_STEPS: dict[tuple[str, str], int] = {}
for _fam in _FAMILY_BUTTON:
    _STEPS.update({("pan", f"{_fam}_mixer"): 1, ("pan", f"{_fam}_channel"): 2,
                   (f"{_fam}_mixer", f"{_fam}_channel"): 1, (f"{_fam}_channel", f"{_fam}_mixer"): 1})
_STEPS.update({("plugin_edit", "plugin_mixer"): 1, ("empty_edit", "plugin_mixer"): 1,
               ("plugin_edit", "plugin_channel"): 2, ("empty_edit", "plugin_channel"): 2})


class ModeError(Exception):
    def __init__(self, step: str, expected: str, observed: str) -> None:
        super().__init__(f"{step}: 기대 {expected}, 관측 {observed}")
        self.step, self.expected, self.observed = step, expected, observed


class ModeDriver:
    def __init__(self, surface: Surface, sleep: Callable[[float], None] = time.sleep) -> None:
        self.surface = surface
        self._sleep = sleep
        self._since = 0.0
        self._page_hint = 1
        self._focused = False
        self._restore_select: int | None = None
        self._name_mode = False
        self.last_leave_error = ""

    # ---------- 기본 ----------
    @property
    def view(self) -> S.View:
        return self.surface.state.view

    def _mark(self) -> None:
        self._since = self.surface.clock()

    def _press(self, note: int) -> None:
        self.surface.send(P.button_down(note))
        self._sleep(PRESS_HOLD_S)
        self.surface.send(P.button_up(note))

    def _settle(self, extra: float = 0.0) -> None:
        """조각 쓰기가 멈추고(dirty_until) 마지막 LCD 변화 뒤 extra초가 지나도록 시간을 보낸다."""
        c = self.surface.state.connection
        due = max(c.dirty_until, c.last_display_change + extra)
        now = self.surface.clock()
        if due > now:
            self._sleep(due - now + 0.01)

    def _wait_change(self) -> bool:
        ok = self.surface.wait_for(lambda s: s.connection.last_display_change >= self._since, FEEDBACK_TIMEOUT)
        self._settle()
        return ok

    def settle_overlay(self) -> None:
        """내 마지막 동작(_mark) 뒤 2.0초 오버레이가 지나 재묘사될 때까지."""
        due = self._since + OVERLAY_S + 0.05
        now = self.surface.clock()
        if due > now:
            self._sleep(due - now)
        self._settle()

    def settle_smart(self) -> None:
        """모드 전환 오버레이 글자가 보일 때만 2.0초를 기다린다(페이지 이동 뒤)."""
        self._settle()
        if S.OVERLAY_MARK in self.surface.state.lcd[0]:
            self.settle_overlay()

    # ---------- 읽기 ----------
    def read_column(self, ch: int) -> tuple[str, Value]:
        """정착 열(7칸) 읽기. 공백이면 깜박임의 빈 위상일 수 있어 한 번 더 기다려 읽는다."""
        name, text = self.view.columns[ch]
        v = parse_value(text)
        if v.kind == "none":
            self._sleep(BLINK_RETRY_S)
            name, text = self.view.columns[ch]
            v = parse_value(text)
        return name.strip(), v

    def read_value(self, ch: int) -> Value:
        """오버레이(21칸, 단위 포함)가 숫자로 읽히면 그것을, 아니면 열 값을 돌려준다."""
        start = min(ch * S.COL_W, P.LCD_WIDTH - OVERLAY_WIDTH)
        wide = parse_value(self.surface.state.lcd[1][start:start + OVERLAY_WIDTH])
        if wide.kind == "number":
            return wide
        return self.read_column(ch)[1]

    def read_overlay_name(self, ch: int) -> str:
        start = min(ch * S.COL_W, P.LCD_WIDTH - OVERLAY_WIDTH)
        return self.surface.state.lcd[0][start:start + OVERLAY_WIDTH].strip()

    # ---------- 조작 ----------
    def focus(self, ch: int) -> None:
        """대상 스트립 SELECT. 처음 한 번 이전 선택을 기억해 leave()에서 되돌린다."""
        strips = self.surface.state.strips
        if not self._focused:
            self._focused = True
            self._restore_select = next((i for i, s in enumerate(strips) if s.select), None)
        if strips[ch].select:
            return
        self._mark()
        self._press(P.Note.SELECT + ch)
        if not self.surface.wait_for(lambda s: s.strips[ch].select, LED_TIMEOUT):
            raise ModeError("focus", f"SELECT{ch + 1} LED", "변화 없음")
        self._settle()

    def enter(self, kind: str) -> None:
        cur = self.view.kind
        if cur == kind:
            return
        fam = kind.split("_")[0]
        if fam not in _FAMILY_BUTTON:
            raise ModeError("enter", kind, "enter로 갈 수 없는 뷰(pan은 leave, edit는 press_vpot)")
        if cur.split("_")[0] != fam or cur.endswith("_menu") or cur in ("midi_fx", "unknown"):
            self.leave(keep_select=True)
            cur = "pan"
        steps = _STEPS.get((cur, kind))
        if steps is None:
            raise ModeError("enter", kind, f"{cur}에서 전환 경로 없음")
        for _ in range(steps):
            before = self.view.kind
            self._mark()
            self._press(_FAMILY_BUTTON[fam])
            if not self.surface.wait_for(lambda s: s.view.kind != before, MODE_TIMEOUT):
                raise ModeError("enter", kind, f"{before}에서 버튼 반응 없음")
        if self.view.kind != kind:
            raise ModeError("enter", kind, self.view.kind)
        self._page_hint = 1
        self.settle_overlay()

    def page_to(self, page: int) -> None:
        """Cursor ◀▶로 페이지 이동. 편집 뷰 NAME 모드는 헤더 `Page n/N`, 그 밖은 드라이버가 센 힌트로."""
        for _ in range(16):
            cur = self.view.page[0] if self.view.page else self._page_hint
            if cur == page:
                return
            forward = cur < page
            cols_before = self.view.columns
            self._mark()
            self._press(P.Note.CURSOR_RIGHT if forward else P.Note.CURSOR_LEFT)
            if not self.surface.wait_for(lambda s: s.view.columns != cols_before, MODE_TIMEOUT):
                raise ModeError("page_to", f"page {page}", f"페이지 {cur}에서 커서 반응 없음")
            self._page_hint = cur + (1 if forward else -1)
            self.settle_smart()
        raise ModeError("page_to", f"page {page}", "16회 안에 못 감")

    def page_until(self, pred: Callable[[S.View], bool], forward: bool = True, max_steps: int = 8) -> bool:
        """열 이름 조건이 맞는 페이지까지 커서를 누른다(헤더가 없는 EQ 채널 뷰용)."""
        for _ in range(max_steps):
            if pred(self.view):
                return True
            cols_before = self.view.columns
            self._mark()
            self._press(P.Note.CURSOR_RIGHT if forward else P.Note.CURSOR_LEFT)
            if not self.surface.wait_for(lambda s: s.view.columns != cols_before, MODE_TIMEOUT):
                return pred(self.view)
            self._page_hint += 1 if forward else -1
            self.settle_smart()
        return pred(self.view)

    def slot_to(self, slot: int) -> None:
        """Cursor ▼로 다음 슬롯, ▲로 이전 슬롯. 1에서 ▲는 MIDI FX(M1)라 slot<1은 ModeError."""
        for _ in range(20):
            kind, cur = self.view.kind, self.view.index
            if kind not in ("plugin_mixer", "plugin_edit", "empty_edit") or cur is None:
                raise ModeError("slot_to", f"slot {slot}", kind)
            if cur == slot:
                return
            self._mark()
            self._press(P.Note.CURSOR_DOWN if cur < slot else P.Note.CURSOR_UP)
            if not self.surface.wait_for(lambda s: s.view.index != cur or s.view.kind == "midi_fx", MODE_TIMEOUT):
                raise ModeError("slot_to", f"slot {slot}", f"슬롯 {cur}에서 커서 반응 없음")
            self._settle()
        raise ModeError("slot_to", f"slot {slot}", "20회 안에 못 감")

    def tick(self, ch: int, steps: int) -> bool:
        """V-Pot 틱(63씩 분할). LCD가 반응하면 True."""
        if steps == 0:
            return True
        self._mark()
        for msg in P.vpot_turn_messages(ch, steps):
            self.surface.send(msg)
        return self._wait_change()

    def press_vpot(self, ch: int) -> bool:
        self._mark()
        self._press(P.Note.VPOT_PUSH + ch)
        return self._wait_change()

    def fader(self, ch: int, raw: int) -> int | None:
        """Flip 상태에서 페이더로 절대값. 에코된 raw, 반응이 없으면 None. raw 0은 보내지 않는다."""
        raw = max(1, min(P.MAX_FADER, raw))
        before = self.surface.state.strips[ch].fader_raw
        self._mark()
        for msg in P.fader_move(ch, raw):
            self.surface.send(msg)
        ok = self.surface.wait_for(lambda s: s.strips[ch].fader_raw != before
                                   or s.connection.last_display_change >= self._since, FADER_TIMEOUT)
        self._settle()
        return self.surface.state.strips[ch].fader_raw if ok else None

    def flip(self, on: bool) -> None:
        if self.surface.state.assignment.flip == on:
            return
        self._mark()
        self._press(P.Note.FLIP)
        if not self.surface.wait_for(lambda s: s.assignment.flip == on, LED_TIMEOUT):
            raise ModeError("flip", "on" if on else "off", "FLIP LED 변화 없음")
        self._sleep(0.1)                      # 페이더 위치 에코가 오는 시간

    def toggle_name_value(self) -> None:
        self._mark()
        self._press(P.Note.NAME_VALUE)
        if not self._wait_change():
            raise ModeError("name_value", "LCD 변화", "없음")
        self._name_mode = not self._name_mode

    def hold_menu(self, button: int, vpot: int) -> None:
        """버튼을 누른 채 V-Pot을 눌러 홀드 메뉴 항목을 고른다(EQ·SEND)."""
        self._mark()
        self.surface.send(P.button_down(button))
        self._sleep(HOLD_MENU_S)
        self._press(P.Note.VPOT_PUSH + vpot)
        self._sleep(0.1)
        self.surface.send(P.button_up(button))
        self._wait_change()
        self.settle_overlay()

    def leave(self, keep_select: bool = False) -> None:
        """NAME 모드 복원 → Flip 해제 → PAN → (선택 복원). 모든 명령의 finally에서 호출."""
        if self._name_mode:
            self.toggle_name_value()
        if self.surface.state.assignment.flip:
            self.flip(False)
        if self.view.kind != "pan":
            for _ in range(2):
                self._mark()
                self._press(P.Note.PAN)
                if self.surface.wait_for(lambda s: s.view.kind == "pan", MODE_TIMEOUT):
                    break
            else:
                raise ModeError("leave", "pan", self.view.kind)
            self.settle_overlay()
        if keep_select or not self._focused:
            return
        prev, self._focused, self._restore_select = self._restore_select, False, None
        strips = self.surface.state.strips
        if prev is not None and strips[prev].number is not None and not strips[prev].select:
            self._mark()
            self._press(P.Note.SELECT + prev)
            self.surface.wait_for(lambda s: s.strips[prev].select, LED_TIMEOUT)
            self._settle()

    def leave_safely(self) -> None:
        try:
            self.leave()
            self.last_leave_error = ""
        except ModeError as e:
            self.last_leave_error = str(e)
```

- [ ] **Step 5: Commands 연동**

`commands.py` 임포트에 `from .modes import ModeDriver` 추가. `Commands.__init__` 끝에:

```python
        self.modes = ModeDriver(surface, sleep)
```

`mixer_pan`에서 다음 블록을

```python
            mode = self.surface.state.assignment.mode
            if mode != "pan":
                return self._result(action, False, "skipped", t0,
                                    note=f"V-Pot 할당 모드가 {mode}. PAN 모드에서만 팬을 보냄(스펙 2 logic_assign)")
```

이렇게 교체한다:

```python
            st0 = self.surface.state
            if st0.assignment.flip or st0.view.kind != "pan" or st0.assignment.mode != "pan":
                self.modes.leave_safely()
            mode = self.surface.state.assignment.mode
            if mode != "pan" or self.surface.state.view.kind != "pan":
                return self._result(action, False, "skipped", t0,
                                    note=f"V-Pot 할당 모드가 {mode}/{self.surface.state.view.kind}. PAN 복귀 실패: {self.modes.last_leave_error}")
```

- [ ] **Step 6: 통과 확인**

Run: `uv run pytest -q`
Expected: 전부 PASS(스펙 1 66개 + 새 테스트). `test_mixer_pan_pan_mode_only` 같은 기존 테스트가 note 문구를 검사하면 새 문구(`PAN 복귀 실패`)에 맞춘다. 가짜 PAN 뷰의 팬 값은 `0`이라 `already`.

- [ ] **Step 7: 커밋**

```bash
git add tests/fake_assign.py src/logic_mcp/logic/modes.py src/logic_mcp/logic/commands.py tests/test_modes.py tests/test_commands.py
git commit -m "feat(modes): ModeDriver(전환·페이지·슬롯·틱·Flip·복귀)와 어사인먼트 가짜 Logic

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: 값 설정 루프 (`logic/setter.py`)

**Files:**
- Create: `src/logic_mcp/logic/setter.py`
- Test: `tests/test_setter.py`

**Interfaces:**
- Consumes: `ModeDriver.flip/fader/tick/read_value/read_column`, `values.Mapping/raw_for/infer_mapping/within`.
- Produces:
  - `SetOutcome(ok: bool, value: Value, rounds: int, note: str)`
  - `set_numeric(d: ModeDriver, ch: int, target: float, mapping: Mapping | None, tolerance: float, faders: FaderTable | None = None) -> SetOutcome`
  - `set_enum(d: ModeDriver, ch: int, target: str, max_steps: int = 16) -> SetOutcome`
  - `probe_mapping(d: ModeDriver, ch: int) -> tuple[Mapping | None, Value, Value]` (Flip이 켜져 있어야 함, 값이 바뀌므로 호출자가 이어서 set으로 목표를 맞춘다)
  - `enum_matches(v: Value, target: str) -> bool`

- [ ] **Step 1: 실패하는 테스트**

`tests/test_setter.py`:

```python
import pytest

from logic_mcp.logic.modes import ModeDriver
from logic_mcp.logic.setter import enum_matches, probe_mapping, set_enum, set_numeric
from logic_mcp.logic.values import Mapping, parse_value
from tests.fake_assign import make_assign_logic


def eq_driver():
    surface, fake, logic = make_assign_logic()
    logic.tracks[0].insert(1, "Channel EQ")
    d = ModeDriver(surface, sleep=logic.sleep)
    d.focus(0)
    d.enter("eq_channel")
    return d, logic, logic.tracks[0].eq


def test_set_numeric_with_log_mapping_uses_fader_once():
    d, logic, eq = eq_driver()
    out = set_numeric(d, 0, 1000.0, Mapping("log", 20.0, 20000.0), tolerance=10.0)
    assert out.ok and out.rounds == 0 and out.note == "fader"
    assert abs(eq[0][0].value - 1000.0) <= 10 and out.value.unit == "Hz"


def test_set_numeric_linear_mapping_then_already():
    d, logic, eq = eq_driver()
    out = set_numeric(d, 5, -3.0, Mapping("linear", -24.0, 24.0), tolerance=0.1)
    assert out.ok and eq[1][1].value == -3.0
    again = set_numeric(d, 5, -3.0, Mapping("linear", -24.0, 24.0), tolerance=0.1)
    assert again.ok and again.note == "already" and again.rounds == 0


def test_set_numeric_without_mapping_ticks_in_log_domain():
    d, logic, eq = eq_driver()
    out = set_numeric(d, 0, 1000.0, None, tolerance=100.0)
    assert out.ok and out.rounds <= 3 and abs(eq[0][0].value - 1000.0) <= 100


def test_set_numeric_without_mapping_ticks_linear():
    d, logic, eq = eq_driver()
    out = set_numeric(d, 5, -3.0, None, tolerance=0.1)
    assert out.ok and out.rounds == 2 and eq[1][1].value == -3.0


def test_set_numeric_gives_up_after_six_rounds():
    d, logic, eq = eq_driver()
    eq[1][1].step = 7.0                              # 틱이 너무 거칠어 0.1 안에 못 들어감
    out = set_numeric(d, 5, -3.0, None, tolerance=0.1)
    assert out.ok is False and out.rounds == 6 and "못 맞춤" in out.note


def test_set_enum_forward_and_reverse():
    d, logic, eq = eq_driver()
    out = set_enum(d, 1, "36")                       # 슬로프 12 → 18 → 24 → 36
    assert out.ok and out.rounds == 3 and eq[0][1].value == 4
    out = set_enum(d, 1, "6")                        # 되돌아가기
    assert out.ok and eq[0][1].value == 0
    out = set_enum(d, 3, "On")
    assert out.ok and eq[0][3].value == 1
    assert set_enum(d, 3, "On").note == "already"
    bad = set_enum(d, 3, "Maybe", max_steps=4)
    assert bad.ok is False and "Maybe" in bad.note


def test_enum_matches():
    assert enum_matches(parse_value("36 dB/Oct"), "36")
    assert enum_matches(parse_value("On"), "On") and not enum_matches(parse_value("Off"), "On")
    assert enum_matches(parse_value("Post Pan"), "Post Pan") and not enum_matches(parse_value("Post Pan"), "Post")


def test_probe_mapping_reads_min_max():
    d, logic, eq = eq_driver()
    d.flip(True)
    m, lo, hi = probe_mapping(d, 5)
    assert m == Mapping("linear", -24.0, 24.0) and lo.text == "-24.0 dB" and hi.text == "+24.0 dB"
    m2, lo2, hi2 = probe_mapping(d, 0)
    assert m2 == Mapping("log", 20.0, 20000.0)
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_setter.py -q`
Expected: `ModuleNotFoundError: logic_mcp.logic.setter`.

- [ ] **Step 3: 구현**

`src/logic_mcp/logic/setter.py`:

```python
"""값 설정 루프: Flip 페이더로 거친 위치(+관측 오차 1회 보정) → V-Pot 틱으로 미세 보정 → 읽어서 검증."""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..mcu.protocol import MAX_FADER
from .faders import FaderTable
from .modes import ModeDriver
from .values import Mapping, Value, infer_mapping, raw_for, within

MAX_ROUNDS = 6


@dataclass
class SetOutcome:
    ok: bool
    value: Value
    rounds: int
    note: str = ""


def _num(v: Value) -> float | None:
    return v.number if v.kind == "number" and v.number is not None and math.isfinite(v.number) else None


def probe_mapping(d: ModeDriver, ch: int) -> tuple[Mapping | None, Value, Value]:
    """Flip 상태에서 페이더를 1·16383으로 보내 최소·최대를 읽는다. 값이 바뀌므로 이어서 set_*로 목표를 맞춘다."""
    d.fader(ch, 1)
    lo = d.read_value(ch)
    d.fader(ch, MAX_FADER)
    hi = d.read_value(ch)
    return infer_mapping(lo, hi), lo, hi


def set_numeric(d: ModeDriver, ch: int, target: float, mapping: Mapping | None, tolerance: float,
                faders: FaderTable | None = None) -> SetOutcome:
    cur = d.read_value(ch)
    if (n := _num(cur)) is not None and within(n, target, tolerance):
        return SetOutcome(True, cur, 0, "already")
    rounds = 0
    if mapping is not None:
        d.flip(True)
        raw = raw_for(mapping, target, faders)
        d.fader(ch, raw)
        cur = d.read_value(ch)
        if (n := _num(cur)) is not None and within(n, target, tolerance):
            return SetOutcome(True, cur, 0, "fader")
        if mapping.type in ("log", "linear") and (n := _num(cur)) is not None and n > 0 or mapping.type == "linear":
            # 관측 오차로 페이더 위치를 한 번 보정(시컨트)
            n = _num(cur)
            if n is not None:
                if mapping.type == "log" and n > 0 and target > 0:
                    delta, span = math.log(target / n), math.log(mapping.hi / mapping.lo)
                else:
                    delta, span = target - n, mapping.hi - mapping.lo
                raw = max(1, min(MAX_FADER, raw + round(delta / span * MAX_FADER)))
                d.fader(ch, raw)
                cur = d.read_value(ch)
                rounds = 1
                if (n := _num(cur)) is not None and within(n, target, tolerance):
                    return SetOutcome(True, cur, rounds, "fader+보정")
    # 틱 미세 보정. Hz는 로그 영역에서 틱당 변화를 추정한다(실측: 20.0 → 21.6 Hz, 비율 일정)
    log_domain = cur.unit == "Hz" and target > 0
    dom = (lambda v: math.log(v)) if log_domain else (lambda v: v)
    per_tick: float | None = None
    for _ in range(MAX_ROUNDS - rounds):
        rounds += 1
        n = _num(cur)
        if n is None or (log_domain and n <= 0):
            ticks = 1                                     # -oo 같은 값에서 벗어나 본다
        else:
            err = dom(target) - dom(n)
            if not per_tick:
                ticks = 1 if err > 0 else -1
            else:
                ticks = max(-63, min(63, round(err / per_tick))) or (1 if err > 0 else -1)
        if not d.tick(ch, ticks):
            return SetOutcome(False, cur, rounds, "V-Pot 틱에 LCD 반응 없음")
        new = d.read_value(ch)
        nn, n = _num(new), _num(cur)
        if nn is not None and n is not None and nn != n and not (log_domain and (nn <= 0 or n <= 0)):
            per_tick = (dom(nn) - dom(n)) / ticks
        cur = new
        if (n := _num(cur)) is not None and within(n, target, tolerance):
            return SetOutcome(True, cur, rounds, "")
    return SetOutcome(False, cur, rounds, f"{MAX_ROUNDS}회 안에 허용 오차 {tolerance} 안으로 못 맞춤 (마지막 {cur.text!r})")


def enum_matches(v: Value, target: str) -> bool:
    if v.text == target:
        return True
    if v.number is not None:
        try:
            return float(target) == v.number
        except ValueError:
            return False
    return False


def set_enum(d: ModeDriver, ch: int, target: str, max_steps: int = 16) -> SetOutcome:
    """틱 1씩 움직여 텍스트가 맞을 때까지. 끝에 닿아 값이 안 바뀌면 반대로 돈다."""
    cur = d.read_value(ch)
    if enum_matches(cur, target):
        return SetOutcome(True, cur, 0, "already")
    seen = [cur.text]
    direction = 1
    for n in range(1, max_steps + 1):
        d.tick(ch, direction)
        cur = d.read_value(ch)
        if enum_matches(cur, target):
            return SetOutcome(True, cur, n, "")
        if cur.text == seen[-1]:
            direction = -direction
        seen.append(cur.text)
    return SetOutcome(False, cur, max_steps, f"선택지에서 {target!r}를 못 찾음. 본 값: {seen}")
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_setter.py -q`
Expected: 모두 PASS. `test_set_numeric_without_mapping_ticks_linear`: 첫 틱은 오차 방향 -1(0 → -0.5 dB) → 틱당 0.5 → -5틱 → -3.0, 2라운드. 로그 영역: +1 틱(20 → 21.6) → ln 1.08 → 50틱 → ≈1013 Hz(허용 100 안), 2라운드.

- [ ] **Step 5: 커밋**

```bash
git add src/logic_mcp/logic/setter.py tests/test_setter.py
git commit -m "feat(setter): 값 설정 루프 — Flip 페이더 거친 위치+보정, 틱 미세 보정(로그/선형), 열거형 스텝, 프로빙

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: `EqCommands` (`logic/assign.py`)와 `Commands.eq`

**Files:**
- Create: `src/logic_mcp/logic/assign.py`
- Modify: `src/logic_mcp/logic/commands.py` (`Commands.eq`, `Commands.plugin` 자리)
- Test: `tests/test_assign_eq.py`

**Interfaces:**
- Consumes: Task 4 `ModeDriver`, Task 5 `set_numeric/set_enum/probe_mapping`, 스펙 1 `Commands._lock/_require_ready/_resolve/_result/_target/_now_ms`.
- Produces:
  - `EqCommands(base: Commands)` with `get(strip, number) -> ToolResult`, `set(strip, number, band: int, param: str, value, allow_insert: bool = True) -> ToolResult`
  - 상수 `EQ_SHORT: dict[int, tuple[str, str, str, str]]`, `EQ_PARAM_COL = {"freq": 0, "gain": 1, "slope": 1, "q": 2, "on": 3}`, `EQ_MAPPING`, `SLOPES`.
  - `Commands.eq: EqCommands` (`Commands.__init__`에서 지연 임포트로 생성). Task 7의 `PluginCommands`도 같은 파일에 추가된다.
  - `get`의 `after`: `{"has_eq": bool, "bands": {"1": {"band": 1, "freq": 20.0, "slope": 12, "q": 0.71, "on": False, "text": ["20.0Hz", "12", "0.71", "Off"]}, "2": {... "gain": 0.0 ...}, …}}`
  - `set`의 `before/after`: `{"band": 3, "param": "freq", "value": 1001.8 | None, "text": "1001.8 Hz"}`

- [ ] **Step 1: 실패하는 테스트**

`tests/test_assign_eq.py`:

```python
import pytest

from logic_mcp.logic.commands import Commands
from logic_mcp.logic.faders import FaderTable
from logic_mcp.mcu import protocol as P
from tests.fake_assign import make_assign_logic


def make():
    surface, fake, logic = make_assign_logic()
    cmds = Commands(surface, FaderTable.load(), sleep=logic.sleep, logic_running=lambda: True)
    return cmds, surface, fake, logic


def test_eq_get_without_eq_does_not_insert():
    cmds, surface, fake, logic = make()
    r = cmds.eq.get(strip=2, number=None)
    assert r.ok and r.verified == "verified" and r.after == {"has_eq": False, "bands": {}}
    assert logic.tracks[1].eq is None and surface.state.view.kind == "pan"
    assert r.target == {"strip": 2, "number": 16, "name": "DCl"}


def test_eq_get_reads_all_bands_and_leaves():
    cmds, surface, fake, logic = make()
    logic.tracks[0].insert(1, "Channel EQ")
    r = cmds.eq.get(strip=1, number=None)
    assert r.verified == "verified" and r.after["has_eq"]
    b = r.after["bands"]
    assert len(b) == 8
    assert b["1"]["freq"] == 20.0 and b["1"]["slope"] == 12 and b["1"]["on"] is False and b["1"]["q"] == 0.71
    assert b["2"]["gain"] == 0.0 and b["5"]["freq"] == 1040.0 and b["8"]["slope"] == 24
    assert b["3"]["text"] == ["100 Hz", "0.0 dB", "0.60", "On"]
    assert surface.state.view.kind == "pan" and logic.selected == 0


def test_eq_set_freq_inserts_when_allowed_and_verifies():
    cmds, surface, fake, logic = make()
    r = cmds.eq.set(strip=1, number=None, band=3, param="freq", value=1000.0)
    assert r.ok and r.verified == "verified" and "Channel EQ 삽입됨" in r.note
    assert abs(logic.tracks[0].eq[2][0].value - 1000.0) <= 10
    assert r.before["text"] == "100 Hz" and r.after["value"] == pytest.approx(1000.0, abs=10)
    assert surface.state.view.kind == "pan" and not surface.state.assignment.flip


def test_eq_set_refuses_insert_when_not_allowed():
    cmds, surface, fake, logic = make()
    r = cmds.eq.set(strip=1, number=None, band=3, param="gain", value=-3.0, allow_insert=False)
    assert r.verified == "skipped" and "allow_insert" in r.note
    assert logic.tracks[0].eq is None and surface.state.view.kind == "pan"


def test_eq_set_gain_slope_on_q():
    cmds, surface, fake, logic = make()
    logic.tracks[0].insert(1, "Channel EQ")
    eq = logic.tracks[0].eq
    assert cmds.eq.set(1, None, 2, "gain", -3.0).after["value"] == -3.0 and eq[1][1].value == -3.0
    r = cmds.eq.set(1, None, 1, "slope", 36)
    assert r.verified == "verified" and r.after["text"].startswith("36") and eq[0][1].value == 4
    r = cmds.eq.set(1, None, 1, "on", True)
    assert r.verified == "verified" and r.after["text"] == "On" and eq[0][3].value == 1
    assert cmds.eq.set(1, None, 1, "on", True).verified == "skipped"            # already
    r = cmds.eq.set(1, None, 4, "q", 2.0)
    assert r.ok and abs(eq[3][2].value - 2.0) <= 0.05
    assert surface.state.view.kind == "pan" and not surface.state.assignment.flip


def test_eq_set_by_number_other_strip():
    cmds, surface, fake, logic = make()
    r = cmds.eq.set(None, 19, 2, "gain", 2.0)
    assert r.ok and logic.tracks[4].eq[1][1].value == 2.0 and r.target["strip"] == 5
    assert logic.selected == 0                                                   # 선택 복원


def test_eq_set_validation_sends_nothing():
    cmds, surface, fake, logic = make()
    n = len(fake.sent)
    assert cmds.eq.set(1, None, 9, "freq", 100.0).verified == "skipped"
    assert cmds.eq.set(1, None, 1, "gain", 1.0).verified == "skipped"        # 밴드 1은 slope
    assert cmds.eq.set(1, None, 3, "slope", 12).verified == "skipped"
    assert cmds.eq.set(1, None, 1, "slope", 7).verified == "skipped"
    assert cmds.eq.set(1, None, 3, "hue", 1.0).verified == "skipped"
    assert len(fake.sent) == n


def test_eq_set_mode_error_still_leaves():            # Review Focus 4
    cmds, surface, fake, logic = make()
    logic.tracks[0].insert(1, "Channel EQ")
    logic.refuse.add(P.Note.CURSOR_RIGHT)
    r = cmds.eq.set(1, None, 5, "gain", -2.0)
    assert r.ok is False and r.verified == "unverified" and "page" in r.note
    assert surface.state.view.kind == "pan" and not surface.state.assignment.flip
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_assign_eq.py -q`
Expected: `AttributeError: 'Commands' object has no attribute 'eq'`.

- [ ] **Step 3: 구현**

`src/logic_mcp/logic/assign.py`:

```python
"""EQ·플러그인 명령. Commands(스펙 1)의 주소 해석·결과 형식·락을 빌려 쓰고 ModeDriver로 뷰를 오간다.
모든 공개 메서드는 ToolResult를 돌려주고 finally에서 leave_safely()로 PAN·Flip off로 돌아간다."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .modes import ModeError
from .setter import probe_mapping, set_enum, set_numeric
from .values import Mapping, Value, parse_value, tolerance_for

if TYPE_CHECKING:
    from .commands import Commands, ToolResult

EQ_SHORT: dict[int, tuple[str, str, str, str]] = {   # 밴드 → (freq, gain|slope, q, on) 축약명. 1~6 실측, 7·8 라이브 체크로 확인
    1: ("LoCutF", "LoCutS", "LoCutQ", "LCO/Of"), 2: ("LoShF", "LoShGa", "LoShQ", "LSO/Of"),
    3: ("Peak1F", "Pea1Ga", "Peak1Q", "Pe1On/"), 4: ("Peak2F", "Pea2Ga", "Peak2Q", "Pe2On/"),
    5: ("Peak3F", "Pea3Ga", "Peak3Q", "Pe3On/"), 6: ("Peak4F", "Pea4Ga", "Peak4Q", "Pe4On/"),
    7: ("HiShF", "HiShGa", "HiShQ", "HSO/Of"), 8: ("HiCutF", "HiCutS", "HiCutQ", "HCO/Of"),
}
EQ_PARAM_COL = {"freq": 0, "gain": 1, "slope": 1, "q": 2, "on": 3}
EQ_MAPPING = {"freq": Mapping("log", 20.0, 20000.0), "gain": Mapping("linear", -24.0, 24.0)}
SLOPES = ("6", "12", "18", "24", "36", "48")
SLOPE_BANDS = (1, 8)


def _band_dict(columns, band: int) -> dict:
    off = 0 if band % 2 == 1 else 4
    cols = columns[off:off + 4]
    vals = [parse_value(c[1]) for c in cols]
    out = {"band": band, "freq": vals[0].number, "q": vals[2].number, "on": vals[3].text == "On",
           "text": [c[1].strip() for c in cols], "names": [c[0].strip() for c in cols]}
    if band in SLOPE_BANDS:
        out["slope"] = int(vals[1].number) if vals[1].number is not None else None
    else:
        out["gain"] = vals[1].number
    return out


def _value_dict(band: int, param: str, v: Value) -> dict:
    return {"band": band, "param": param, "value": v.number, "text": v.text}


class EqCommands:
    def __init__(self, base: "Commands") -> None:
        self.b = base
        self.d = base.modes

    def _goto_page(self, band: int) -> None:
        page = (band + 1) // 2
        want = EQ_SHORT[2 * page - 1][0]
        self.d.page_to(page)
        if self.d.view.columns[0][0].strip() != want:
            found = (self.d.page_until(lambda v: v.columns[0][0].strip() == want, forward=True, max_steps=4)
                     or self.d.page_until(lambda v: v.columns[0][0].strip() == want, forward=False, max_steps=4))
            if not found:
                raise ModeError("page", f"{want} 열(밴드 {2 * page - 1})", self.d.view.columns[0][0].strip() or "빈 열")

    def _has_eq(self, ch: int) -> bool:
        """E1(EQ Mixer view)에서 해당 스트립 2행이 비어 있으면 Channel EQ 없음. 삽입을 일으키지 않는다."""
        self.d.enter("eq_mixer")
        return self.d.read_column(ch)[1].kind != "none"

    def get(self, strip: int | None, number: int | None) -> "ToolResult":
        b, d, action = self.b, self.d, "eq_get"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = b._resolve(strip, number, action, t0)
            if not isinstance(ch, int):
                return ch
            target = b._target(ch)
            try:
                d.focus(ch)
                if not self._has_eq(ch):
                    return b._result(action, True, "verified", t0, target=target, after={"has_eq": False, "bands": {}})
                d.enter("eq_channel")
                bands: dict[str, dict] = {}
                for band in (1, 3, 5, 7):
                    self._goto_page(band)
                    bands[str(band)] = _band_dict(d.view.columns, band)
                    bands[str(band + 1)] = _band_dict(d.view.columns, band + 1)
                return b._result(action, True, "verified", t0, target=target, after={"has_eq": True, "bands": bands})
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
            finally:
                d.leave_safely()

    def set(self, strip: int | None, number: int | None, band: int, param: str, value,
            allow_insert: bool = True) -> "ToolResult":
        b, d, action = self.b, self.d, "eq_set"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            if not 1 <= band <= 8:
                return b._result(action, False, "skipped", t0, note="band는 1-8")
            if param not in EQ_PARAM_COL:
                return b._result(action, False, "skipped", t0, note=f"param은 {list(EQ_PARAM_COL)} 중 하나")
            if (band in SLOPE_BANDS) != (param == "slope") and param in ("gain", "slope"):
                return b._result(action, False, "skipped", t0,
                                 note=f"밴드 {band}는 {'slope' if band in SLOPE_BANDS else 'gain'}만 받음")
            if param == "slope" and str(int(value)) not in SLOPES:
                return b._result(action, False, "skipped", t0, note=f"slope는 {SLOPES} 중 하나")
            ch = b._resolve(strip, number, action, t0)
            if not isinstance(ch, int):
                return ch
            target = b._target(ch)
            inserted = False
            try:
                d.focus(ch)
                if not self._has_eq(ch):
                    if not allow_insert:
                        return b._result(action, False, "skipped", t0, target=target,
                                         note="Channel EQ 없음. allow_insert=true면 삽입하고 설정")
                    inserted = True
                d.enter("eq_channel")                                    # 없던 트랙이면 여기서 삽입됨(실측)
                self._goto_page(band)
                col = (0 if band % 2 == 1 else 4) + EQ_PARAM_COL[param]
                before = _value_dict(band, param, d.read_column(col)[1])
                if param == "on":
                    want = "On" if (value is True or str(value).lower() in ("on", "true", "1")) else "Off"
                    out = set_enum(d, col, want)
                elif param == "slope":
                    out = set_enum(d, col, str(int(value)))
                elif param == "q":
                    d.flip(True)
                    mapping, _lo, _hi = probe_mapping(d, col)             # Q 범위는 밴드마다 달라 프로빙(실측)
                    out = set_numeric(d, col, float(value), mapping, tolerance_for(float(value), None))
                else:
                    unit = "Hz" if param == "freq" else "dB"
                    out = set_numeric(d, col, float(value), EQ_MAPPING[param], tolerance_for(float(value), unit))
                after = _value_dict(band, param, out.value)
                note = ("Channel EQ 삽입됨. " if inserted else "") + out.note
                if out.ok and out.note == "already" and not inserted:
                    return b._result(action, True, "skipped", t0, target=target, before=before, after=after, note="already")
                return b._result(action, out.ok, "verified" if out.ok else "unverified", t0, target=target,
                                 before=before, after=after, note=note.strip())
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target,
                                 note=("Channel EQ 삽입됨. " if inserted else "") + str(e))
            finally:
                d.leave_safely()
```

`commands.py`의 `Commands.__init__` 끝(`self.modes = …` 다음)에:

```python
        from .assign import EqCommands, PluginCommands   # 지연 임포트(순환 방지)
        self.eq = EqCommands(self)
        self.plugin = PluginCommands(self)
```

Task 7 전까지 `PluginCommands`가 없으므로 이 태스크에서는 임시로 `assign.py`에 빈 클래스를 둔다:

```python
class PluginCommands:
    def __init__(self, base: "Commands") -> None:
        self.b = base
        self.d = base.modes
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest -q`
Expected: 전부 PASS.

- [ ] **Step 5: 커밋**

```bash
git add src/logic_mcp/logic/assign.py src/logic_mcp/logic/commands.py tests/test_assign_eq.py
git commit -m "feat(eq): EqCommands get/set — E1로 유무 확인, 채널 뷰 페이지, Flip+틱 설정, Q 프로빙

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: 플러그인 목록 캐시·매칭·번들 (`logic/plugins/`)

**Files:**
- Create: `src/logic_mcp/logic/plugins/__init__.py`(빈 파일), `cache.py`, `match.py`, `known.json`
- Test: `tests/test_plugins.py`

**Interfaces:**
- Produces:
  - `cache.logic_version(plist: Path = LOGIC_PLIST) -> str`
  - `cache.PluginCache(version, bundled_list, user_list, abbrev, params, scanned_at, path)` with `items`(사용자 목록 우선), `source`, `load(version=None, user_dir=USER_DIR, bundled=BUNDLED)`, `save()`, `to_resource() -> dict`, `learn_abbrev(abbrev, name)`, `param_table(name) -> dict | None`
  - `match.normalize(name) -> str`, `match.find(items, query) -> tuple[int | None, list[str]]`
  - `known.json`: `{"logic_version", "generated", "complete": false, "list": [...], "abbrev": {...}, "params": {...}}`

- [ ] **Step 1: 실패하는 테스트**

`tests/test_plugins.py`:

```python
import json
from pathlib import Path

from logic_mcp.logic.plugins.cache import BUNDLED, PluginCache, logic_version
from logic_mcp.logic.plugins.match import find, normalize


def test_bundled_known_json_shape():
    data = json.loads(BUNDLED.read_text())
    assert data["list"][0] == "--" and "Channel EQ" in data["list"] and "Compressor" in data["list"]
    assert data["list"].index("Channel EQ") == 55 and data["list"].index("DeEsser") == 20   # 실측 인덱스
    assert data["abbrev"]["Cha EQ"] == "Channel EQ"
    assert data["params"]["Channel EQ"]["pages"] == 6
    assert data["params"]["Channel EQ"]["items"][0] == {"index": 1, "short": "LoCutS", "name": "Low Cut Slope",
                                                        "map": {"type": "enum", "options": ["6", "12", "18", "24", "36", "48"]}}
    assert data["complete"] is False


def test_logic_version_reads_plist(tmp_path):
    import plistlib
    p = tmp_path / "Info.plist"
    p.write_bytes(plistlib.dumps({"CFBundleShortVersionString": "12.0.1"}))
    assert logic_version(p) == "12.0.1"
    assert logic_version(tmp_path / "missing.plist") == "unknown"


def test_cache_merges_bundled_and_user(tmp_path):
    c = PluginCache.load(version="12.0.1", user_dir=tmp_path)
    assert c.source == "bundled" and c.items[55] == "Channel EQ" and c.scanned_at is None
    assert c.path == tmp_path / "plugins-12.0.1.json"
    c.user_list = ["--", "Compressor", "Channel EQ", "FabFilter Pro-Q 3 (s/"]
    c.scanned_at = "2026-10-15T12:00:00"
    c.learn_abbrev("Compre", "Compressor")
    c.save()
    c2 = PluginCache.load(version="12.0.1", user_dir=tmp_path)
    assert c2.source == "scan" and c2.items[2] == "Channel EQ" and c2.abbrev["Compre"] == "Compressor"
    assert c2.abbrev["Cha EQ"] == "Channel EQ"                     # 번들 축약은 유지
    assert c2.param_table("Channel EQ")["pages"] == 6 and c2.param_table("Nope") is None
    res = c2.to_resource()
    assert res["source"] == "scan" and res["scanned_count"] == 4 and res["items"][1] == {"index": 1, "name": "Compressor"}


def test_normalize_strips_channel_suffix_and_truncation():
    assert normalize("Channel EQ (s/s)") == "channeleq"
    assert normalize("High Pass Filter (s/s") == "highpassfilter"
    assert normalize("  Space-Designer ") == "spacedesigner"
    assert normalize("EVOC 20 TrackOscillat") == "evoc20trackoscillat"


def test_find_exact_prefix_partial_and_ambiguous():
    items = ["--", "Parametric EQ", "Compressor", "Silver Compressor (s/", "Channel EQ", "EVOC 20 TrackOscillat"]
    assert find(items, "Compressor") == (2, ["Compressor"])
    assert find(items, "channel eq (s/s)") == (4, ["Channel EQ"])
    assert find(items, "EVOC 20 TrackOscillator") == (5, ["EVOC 20 TrackOscillat"])   # 21자 잘림
    idx, cands = find(items, "EQ")
    assert idx is None and set(cands) == {"Parametric EQ", "Channel EQ"}
    assert find(items, "Tuner") == (None, [])
    assert find(items, "--") == (None, [])
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_plugins.py -q`
Expected: `ModuleNotFoundError: logic_mcp.logic.plugins`.

- [ ] **Step 3: 번들 데이터**

`src/logic_mcp/logic/plugins/known.json` (실측 목록: 스파이크 3차 스캔, 인덱스 1~66. `complete: false`는 전 범위 스캔 전이라는 뜻):

```json
{
  "logic_version": "12.0.1",
  "generated": "2026-10-15",
  "complete": false,
  "list": ["--", "Parametric EQ", "Low Pass Filter", "High Pass Filter", "Low Shelving EQ", "High Shelving EQ",
           "Chorus", "Flanger", "Tape Delay", "Echo", "Stereo Delay", "SilverVerb", "PlatinumVerb", "Phaser",
           "Microphaser", "Compressor", "Fuzz-Wah", "Expander", "Enveloper", "Pitch Shifter", "DeEsser", "Ensemble",
           "AutoFilter", "Bitcrusher", "Distortion", "Overdrive", "EnVerb", "DJ EQ", "Spectral Gate", "High Cut",
           "Low Cut", "Fat EQ", "Silver EQ", "Silver Compressor", "GoldVerb", "Noise Gate", "Silver Gate",
           "Modulation Delay", "Gain", "Tremolo", "SubBass", "EVOC 20 TrackOscillator", "Clip Distortion", "AVerb",
           "Adaptive Limiter", "Multipressor", "Denoiser", "Phase Distortion", "Exciter", "Limiter",
           "EVOC 20 Filterbank", "Distortion II", "Scanner Vibrato", "Space Designer", "Pitch Correction",
           "Channel EQ", "Tuner", "Linear Phase EQ", "Guitar Amp Pro", "Match EQ", "Delay Designer",
           "Vocal Transformer", "Grooveshifter", "Ringshifter", "Test Oscillator", "Level Meter", "Bass Amp"],
  "abbrev": {"Cha EQ": "Channel EQ", "Distrt": "Distortion"},
  "params": {
    "Channel EQ": {
      "pages": 6,
      "items": [
        {"index": 1, "short": "LoCutS", "name": "Low Cut Slope", "map": {"type": "enum", "options": ["6", "12", "18", "24", "36", "48"]}},
        {"index": 2, "short": "LoShGa", "name": "Low Shelf Gain", "map": {"type": "linear", "lo": -24.0, "hi": 24.0}},
        {"index": 3, "short": "Pea1Ga", "name": "Peak 1 Gain", "map": {"type": "linear", "lo": -24.0, "hi": 24.0}},
        {"index": 4, "short": "Pea2Ga", "name": "Peak 2 Gain", "map": {"type": "linear", "lo": -24.0, "hi": 24.0}},
        {"index": 5, "short": "Pea3Ga", "name": "Peak 3 Gain", "map": {"type": "linear", "lo": -24.0, "hi": 24.0}},
        {"index": 6, "short": "Pea4Ga", "name": "Peak 4 Gain", "map": {"type": "linear", "lo": -24.0, "hi": 24.0}},
        {"index": 7, "short": "HiShGa", "name": "High Shelf Gain", "map": {"type": "linear", "lo": -24.0, "hi": 24.0}},
        {"index": 8, "short": "HiCutS", "name": "High Cut Slope", "map": {"type": "enum", "options": ["6", "12", "18", "24", "36", "48"]}},
        {"index": 9, "short": "LoCutF", "name": "Low Cut Frequency", "map": {"type": "log", "lo": 20.0, "hi": 20000.0}},
        {"index": 10, "short": "LoShF", "name": "Low Shelf Frequency", "map": {"type": "log", "lo": 20.0, "hi": 20000.0}},
        {"index": 11, "short": "Peak1F", "name": "Peak 1 Frequency", "map": {"type": "log", "lo": 20.0, "hi": 20000.0}},
        {"index": 12, "short": "Peak2F", "name": "Peak 2 Frequency", "map": {"type": "log", "lo": 20.0, "hi": 20000.0}},
        {"index": 13, "short": "Peak3F", "name": "Peak 3 Frequency", "map": {"type": "log", "lo": 20.0, "hi": 20000.0}},
        {"index": 14, "short": "Peak4F", "name": "Peak 4 Frequency", "map": {"type": "log", "lo": 20.0, "hi": 20000.0}},
        {"index": 15, "short": "HiShF", "name": "High Shelf Frequency", "map": {"type": "log", "lo": 20.0, "hi": 20000.0}},
        {"index": 16, "short": "HiCutF", "name": "High Cut Frequency", "map": {"type": "log", "lo": 20.0, "hi": 20000.0}}
      ]
    }
  }
}
```

- [ ] **Step 4: 구현**

`src/logic_mcp/logic/plugins/cache.py`:

```python
"""플러그인 목록·축약·파라미터 캐시. 번들(known.json)과 사용자(~/.logic-mcp/plugins-<Logic 버전>.json)를 병합한다.
사용자 목록이 있으면 목록은 사용자 것을 쓰고(설치된 플러그인에 따라 순서가 다름), 축약·파라미터 표는 둘을 합친다."""
from __future__ import annotations

import json
import plistlib
from dataclasses import dataclass
from pathlib import Path

BUNDLED = Path(__file__).with_name("known.json")
USER_DIR = Path.home() / ".logic-mcp"
LOGIC_PLIST = Path("/Applications/Logic Pro.app/Contents/Info.plist")


def logic_version(plist: Path = LOGIC_PLIST) -> str:
    try:
        with plist.open("rb") as f:
            return str(plistlib.load(f).get("CFBundleShortVersionString", "unknown"))
    except (OSError, plistlib.InvalidFileException, ValueError):
        return "unknown"


@dataclass
class PluginCache:
    version: str
    bundled_list: list[str]
    user_list: list[str]
    abbrev: dict[str, str]          # LCD 6자 축약(strip) → 전체 이름
    params: dict[str, dict]         # 플러그인 이름 → {"pages": n, "items": [{"index","short","name","map"}]}
    scanned_at: str | None
    path: Path

    @property
    def items(self) -> list[str]:
        return self.user_list or self.bundled_list

    @property
    def source(self) -> str:
        return "scan" if self.user_list else "bundled"

    @classmethod
    def load(cls, version: str | None = None, user_dir: Path = USER_DIR, bundled: Path = BUNDLED) -> "PluginCache":
        version = version or logic_version()
        b = json.loads(bundled.read_text())
        path = user_dir / f"plugins-{version}.json"
        u = json.loads(path.read_text()) if path.exists() else {}
        return cls(version=version, bundled_list=list(b.get("list", [])), user_list=list(u.get("list", [])),
                   abbrev={**b.get("abbrev", {}), **u.get("abbrev", {})},
                   params={**b.get("params", {}), **u.get("params", {})},
                   scanned_at=u.get("scanned_at"), path=path)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"logic_version": self.version, "scanned_at": self.scanned_at,
                                         "list": self.user_list, "abbrev": self.abbrev, "params": self.params},
                                        ensure_ascii=False, indent=1))

    def learn_abbrev(self, abbrev: str, name: str) -> None:
        if abbrev.strip() and name:
            self.abbrev[abbrev.strip()] = name

    def param_table(self, name: str) -> dict | None:
        return self.params.get(name)

    def to_resource(self) -> dict:
        return {"logic_version": self.version, "source": self.source, "bundled_count": len(self.bundled_list),
                "scanned_count": len(self.user_list), "scanned_at": self.scanned_at, "path": str(self.path),
                "items": [{"index": i, "name": n} for i, n in enumerate(self.items)],
                "known_params": sorted(self.params)}
```

`src/logic_mcp/logic/plugins/match.py`:

```python
"""플러그인 이름 매칭. LCD는 `(s/s)` 같은 채널 구성 접미를 붙이고 21자에서 자른다."""
from __future__ import annotations

import re

_SUFFIX_RE = re.compile(r"\s*\((?:s/s|m/s|m/m|s|m|st|mono|stereo|dual mono)[^)]*\)?\s*$", re.IGNORECASE)
_JUNK_RE = re.compile(r"[\s\-_]+")


def normalize(name: str) -> str:
    return _JUNK_RE.sub("", _SUFFIX_RE.sub("", name.strip())).lower()


def find(items: list[str], query: str) -> tuple[int | None, list[str]]:
    """정규화 뒤 정확 일치 → 접두 일치(잘린 이름 포함) → 부분 일치. (인덱스, 후보). 후보 2개 이상이면 인덱스 None."""
    q = normalize(query)
    if not q or query.strip() == "--":
        return None, []
    norm = [(i, normalize(n)) for i, n in enumerate(items) if n != "--"]
    rules = (lambda a, b: a == b,
             lambda a, b: a.startswith(b) or b.startswith(a),
             lambda a, b: b in a)
    for rule in rules:
        hits = [i for i, n in norm if rule(n, q)]
        if len(hits) == 1:
            return hits[0], [items[hits[0]]]
        if len(hits) > 1:
            return None, [items[i] for i in hits]
    return None, []
```

`src/logic_mcp/logic/plugins/__init__.py`는 빈 파일.

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/test_plugins.py -q`
Expected: 모두 PASS. `known.json`이 패키지에 포함되는지도 확인: `uv run python -c "from logic_mcp.logic.plugins.cache import BUNDLED; print(BUNDLED.exists())"` → True.

- [ ] **Step 6: 커밋**

```bash
git add src/logic_mcp/logic/plugins tests/test_plugins.py
git commit -m "feat(plugins): 목록 캐시(번들+사용자 병합), 이름 매칭, 실측 번들 known.json

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: `PluginCommands` — list / params / get / set

**Files:**
- Modify: `src/logic_mcp/logic/assign.py`(`PluginCommands` 본문), `src/logic_mcp/logic/modes.py`(`read_overlay_text`), `src/logic_mcp/logic/plugins/match.py`(`strip_suffix`), `src/logic_mcp/logic/commands.py`(`plugin_cache` 인자)
- Test: `tests/test_assign_plugin.py`

**Interfaces:**
- Consumes: Task 4 드라이버, Task 5 setter, Task 7 캐시·매칭.
- Produces:
  - `ModeDriver.read_overlay_text(ch) -> str` (오버레이 2행 21칸 원문)
  - `match.strip_suffix(name) -> str`
  - `Commands(surface, faders, sleep, logic_running, plugin_cache: PluginCache | None = None)`; `Commands.plugin: PluginCommands`
  - `PluginCommands(base, cache)` with `cache`, `inventory: dict[str, dict[str, dict | None]]`, `list(strip, number)`, `params(strip, number, slot)`, `get(strip, number, slot, param)`, `set(strip, number, slot, param, value, tolerance=None)`
  - 결과 `after`: list → `{"tracks": {"15": {"1": {"text": "Cha EQ", "name": "Channel EQ" | None}, "2": None, …}}}`; params → `{"plugin", "abbrev", "slot", "pages", "params": [{"index", "short", "name", "value", "text"}]}`; get/set → `{"plugin", "slot", "index", "short", "name", "value", "text"}`
  - 핵심 절차 `_open_edit(ch, slot) -> (full_name, abbrev, pages)`: P<slot>에서 **+1 틱(반 항목)으로 현재 항목의 전체 이름을 오버레이로 드러내고** V-Pot을 눌러 편집 뷰로 들어간다(실측: 같은 플러그인 확인은 값 보존). NAME 모드로 바꿔 `Page n/N`에서 페이지 수를 읽는다.
  - 모든 명령은 시작할 때 뷰가 PAN이 아니면 `leave(keep_select=True)`로 초기화한다(남은 미리 선택 취소, Review Focus 3).

- [ ] **Step 1: 실패하는 테스트**

`tests/test_assign_plugin.py`:

```python
import pytest

from logic_mcp.logic.commands import Commands
from logic_mcp.logic.faders import FaderTable
from logic_mcp.logic.plugins.cache import PluginCache
from logic_mcp.mcu import protocol as P
from tests.fake_assign import PLUGIN_LIST, make_assign_logic


def make(tmp_path):
    surface, fake, logic = make_assign_logic()
    cache = PluginCache("fake", list(PLUGIN_LIST), [], {}, {}, None, tmp_path / "plugins-fake.json")
    cmds = Commands(surface, FaderTable.load(), sleep=logic.sleep, logic_running=lambda: True, plugin_cache=cache)
    return cmds, surface, fake, logic, cache


def test_list_inventory_whole_bank(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(1, "Channel EQ")
    logic.tracks[2].insert(3, "Compressor")
    cache.learn_abbrev("Compre", "Compressor")
    r = cmds.plugin.list(None, None)
    assert r.verified == "verified"
    t = r.after["tracks"]
    assert t["15"]["1"] == {"text": "Channe", "name": None} and t["15"]["2"] is None
    assert t["17"]["3"] == {"text": "Compre", "name": "Compressor"}
    assert len(t) == 8 and len(t["15"]) == 15
    assert cmds.plugin.inventory == t and surface.state.view.kind == "pan"


def test_list_single_track(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[4].insert(2, "Limiter")
    r = cmds.plugin.list(None, 19)
    assert list(r.after["tracks"]) == ["19"] and r.after["tracks"]["19"]["2"]["text"] == "Limite"


def test_params_reads_all_pages_learns_and_keeps_values(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    r = cmds.plugin.params(strip=1, number=None, slot=2)
    assert r.verified == "verified" and r.after["plugin"] == "Compressor" and r.after["pages"] == 2
    ps = r.after["params"]
    assert len(ps) == 10
    assert ps[0] == {"index": 1, "short": "Thresh", "name": None, "value": -20.0, "text": "-20.0 d"}   # 7칸 잘림
    assert ps[9]["short"] == "Limit" and ps[9]["text"] == "Off" and ps[9]["value"] is None
    assert cache.abbrev["Compre"] == "Compressor" and cache.param_table("Compressor")["pages"] == 2
    assert cache.param_table("Compressor")["items"][9]["short"] == "Limit" and cache.path.exists()
    assert logic.tracks[0].params[2][0].value == -20.0           # 같은 플러그인 재확인이 값을 리셋하지 않음
    assert surface.state.view.kind == "pan" and logic.name_mode is False


def test_params_empty_slot_skipped(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    r = cmds.plugin.params(1, None, 3)
    assert r.verified == "skipped" and "비어" in r.note and surface.state.view.kind == "pan"


def test_params_cancels_stale_preselect_before_press(tmp_path):      # Review Focus 3
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(1, "Channel EQ")
    cmds.modes.enter("plugin_mixer")
    cmds.modes.tick(1, 6)                                           # 스트립 2에 미리 선택(3항목) 잔류
    assert logic.pre
    r = cmds.plugin.params(1, None, 1)
    assert r.verified == "verified" and r.after["plugin"] == "Channel EQ"
    assert logic.tracks[1].inserts[1] is None                       # 스트립 2에 아무것도 삽입되지 않음


def test_get_and_set_by_index_and_name(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    g = cmds.plugin.get(1, None, 2, 1)
    assert g.verified == "verified" and g.after["value"] == -20.0 and g.after["short"] == "Thresh"
    s = cmds.plugin.set(1, None, 2, "Thresh", -30.0)
    assert s.verified == "verified" and logic.tracks[0].params[2][0].value == -30.0
    assert s.before["value"] == -20.0 and s.after["value"] == -30.0
    assert cache.param_table("Compressor")["items"][0]["map"] == {"type": "linear", "lo": -60.0, "hi": 0.0}  # 프로빙 학습
    s2 = cmds.plugin.set(1, None, 2, 10, "On")                      # 2페이지 열거형(Limiter)
    assert s2.verified == "verified" and logic.tracks[0].params[2][9].value == 1 and s2.after["text"] == "On"
    assert surface.state.view.kind == "pan" and not surface.state.assignment.flip


def test_set_uses_known_mapping_without_probe(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    cache.params["Compressor"] = {"pages": 2, "items": [
        {"index": 1, "short": "Thresh", "name": "Threshold", "map": {"type": "linear", "lo": -60.0, "hi": 0.0}}]}
    logic.tracks[0].insert(2, "Compressor")
    n0 = len(fake.sent)
    s = cmds.plugin.set(1, None, 2, "Threshold", -12.0)
    assert s.ok and logic.tracks[0].params[2][0].value == -12.0 and s.after["name"] == "Threshold"
    assert len([m for m in fake.sent[n0:] if m[0] == 0xE0]) == 1   # 프로빙(2회) 없이 페이더 1회


def test_param_missing_or_ambiguous(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    r = cmds.plugin.set(1, None, 2, "Zzz", 1.0)
    assert r.verified == "skipped" and "Thresh" in r.note and surface.state.view.kind == "pan"
    assert cmds.plugin.get(1, None, 2, 11).verified == "skipped"     # 인덱스 범위 밖
    assert cmds.plugin.get(1, None, 16, 1).verified == "skipped"     # 슬롯 범위 밖
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_assign_plugin.py -q`
Expected: `TypeError: ... unexpected keyword argument 'plugin_cache'`.

- [ ] **Step 3: 드라이버·매칭·Commands 보강**

`modes.py`의 `read_overlay_name` 뒤에 추가:

```python
    def read_overlay_text(self, ch: int) -> str:
        """오버레이 2행(21칸) 원문. 플러그인 이름처럼 숫자가 아닌 값에 쓴다."""
        start = min(ch * S.COL_W, P.LCD_WIDTH - OVERLAY_WIDTH)
        return self.surface.state.lcd[1][start:start + OVERLAY_WIDTH].strip()
```

`match.py` 끝에 추가:

```python
def strip_suffix(name: str) -> str:
    """`Channel EQ (s/s)` → `Channel EQ`. 잘린 `(s/` 도 떼어낸다."""
    return _SUFFIX_RE.sub("", name.strip()).strip()
```

`commands.py`의 `Commands.__init__` 시그니처에 `plugin_cache=None`을 추가하고(타입은 `"PluginCache | None"`, `TYPE_CHECKING`으로 임포트) 생성부를 바꾼다:

```python
        from .assign import EqCommands, PluginCommands   # 지연 임포트(순환 방지)
        self.eq = EqCommands(self)
        self.plugin = PluginCommands(self, plugin_cache)
```

- [ ] **Step 4: PluginCommands 구현**

`assign.py`의 임시 `PluginCommands`를 다음으로 교체(임포트에 `import re`, `from .plugins.cache import PluginCache`, `from .plugins.match import find, normalize, strip_suffix`, `from .values import ..., within` 추가):

```python
class SlotEmpty(Exception):
    pass


class ParamNotFound(Exception):
    def __init__(self, note: str) -> None:
        super().__init__(note)
        self.note = note


def _map_from(d: dict | None) -> Mapping | None:
    if not d:
        return None
    return Mapping(d["type"], d.get("lo", 0.0), d.get("hi", 1.0), tuple(d.get("options", ())))


def _map_to(m: Mapping) -> dict:
    out: dict = {"type": m.type}
    if m.type in ("log", "linear"):
        out.update(lo=m.lo, hi=m.hi)
    if m.type == "enum":
        out["options"] = list(m.options)
    return out


class PluginCommands:
    def __init__(self, base: "Commands", cache: PluginCache | None = None) -> None:
        self.b = base
        self.d = base.modes
        self.cache = cache or PluginCache.load()
        self.inventory: dict[str, dict[str, dict | None]] = {}

    # ---------- 공통 ----------
    def _fresh(self) -> None:
        """남은 미리 선택·Flip·NAME 모드를 지우고 PAN에서 시작한다."""
        if self.d.view.kind != "pan" or self.b.surface.state.assignment.flip:
            self.d.leave(keep_select=True)

    def _slot_text(self, ch: int) -> str:
        return self.d.read_column(ch)[1].text

    def _open_edit(self, ch: int, slot: int) -> tuple[str, str, int]:
        d = self.d
        d.enter("plugin_mixer")
        d.slot_to(slot)
        abbrev = self._slot_text(ch)
        if abbrev in ("", "--"):
            raise SlotEmpty(slot)
        d.tick(ch, 1)                                   # 반 항목: 현재 항목의 전체 이름이 오버레이로 뜬다(실측)
        full = strip_suffix(d.read_overlay_text(ch))
        d.press_vpot(ch)
        if d.view.kind != "plugin_edit":
            raise ModeError("edit", "plugin_edit", d.view.kind)
        d.settle_smart()
        if full and full != "--":
            self.cache.learn_abbrev(abbrev, full)
        d.toggle_name_value()                           # NAME 모드: 1행 헤더 `Page n/N`, 2행 축약명
        pages = d.view.page[1] if d.view.page else 1
        return full or abbrev, abbrev, pages

    def _read_pages(self, pages: int) -> list[dict]:
        """NAME 모드에서 시작. 페이지마다 축약명(NAME)과 값(VALUE)을 읽고 NAME 모드로 돌아온다."""
        d, items = self.d, []
        for page in range(1, pages + 1):
            d.page_to(page)
            shorts = [c[1].strip() for c in d.view.columns]
            d.toggle_name_value()
            values = [parse_value(c[1]) for c in d.view.columns]
            d.toggle_name_value()
            for i, short in enumerate(shorts):
                if short:
                    items.append({"index": (page - 1) * 8 + i + 1, "short": short, "value": values[i].number,
                                  "text": values[i].text})
        return items

    def _table(self, full: str, pages: int) -> dict:
        return self.cache.params.setdefault(full, {"pages": pages, "items": []})

    def _merge_items(self, full: str, pages: int, observed: list[dict]) -> None:
        table = self._table(full, pages)
        table["pages"] = pages
        by_index = {it["index"]: it for it in table["items"]}
        for ob in observed:
            it = by_index.get(ob["index"])
            if it is None:
                it = {"index": ob["index"], "short": ob["short"], "name": None, "map": None}
                table["items"].append(it)
                by_index[ob["index"]] = it
            else:
                it["short"] = ob["short"]
        table["items"].sort(key=lambda x: x["index"])

    def _locate(self, full: str, pages: int, param) -> dict:
        """param(인덱스 또는 이름) → 표 항목 {"index","short","name","map"}. 표에 없으면 페이지를 읽어 채운다."""
        table = self._table(full, pages)
        if isinstance(param, int) or (isinstance(param, str) and param.strip().isdigit()):
            index = int(param)
            if not 1 <= index <= pages * 8:
                raise ParamNotFound(f"index {index}는 1-{pages * 8} 밖")
            it = next((x for x in table["items"] if x["index"] == index), None)
            if it is None:
                self._merge_items(full, pages, self._read_pages(pages))
                it = next((x for x in table["items"] if x["index"] == index), None)
            if it is None:
                raise ParamNotFound(f"index {index} 자리가 비어 있음")
            return it
        q = normalize(str(param))

        def hits(items: list[dict]) -> list[dict]:
            out = []
            for x in items:
                n, s = normalize(x.get("name") or ""), normalize(x["short"])
                if q and (n == q or s == q or (n and (n.startswith(q) or q.startswith(n))) or q.startswith(s) or s.startswith(q)):
                    out.append(x)
            return out
        found = hits(table["items"])
        if not found:
            self._merge_items(full, pages, self._read_pages(pages))
            found = hits(table["items"])
        exact = [x for x in found if normalize(x.get("name") or "") == q or normalize(x["short"]) == q]
        if len(exact) == 1:
            return exact[0]
        if len(found) == 1:
            return found[0]
        shorts = [x["short"] for x in table["items"]]
        if not found:
            raise ParamNotFound(f"{param!r}에 맞는 파라미터 없음. 축약명: {shorts}")
        raise ParamNotFound(f"{param!r}가 여럿에 맞음: {[x['short'] for x in found]}")

    def _goto_param(self, item: dict) -> int:
        """NAME 모드에서 해당 페이지로 가고 VALUE 모드로 바꾼 뒤 열 번호를 돌려준다."""
        page = (item["index"] - 1) // 8 + 1
        self.d.page_to(page)
        self.d.toggle_name_value()
        return (item["index"] - 1) % 8

    def _param_dict(self, full: str, slot: int, item: dict, v: Value) -> dict:
        return {"plugin": full, "slot": slot, "index": item["index"], "short": item["short"],
                "name": item.get("name"), "value": v.number, "text": v.text}

    # ---------- 명령 ----------
    def list(self, strip: int | None, number: int | None) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_list"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            only: int | None = None
            if strip is not None or number is not None:
                ch = b._resolve(strip, number, action, t0)
                if not isinstance(ch, int):
                    return ch
                only = ch
            try:
                self._fresh()
                d.enter("plugin_mixer")
                tracks: dict[str, dict[str, dict | None]] = {}
                for slot in range(1, 16):
                    d.slot_to(slot)
                    for ch, s in enumerate(b.surface.state.strips):
                        if s.number is None or (only is not None and ch != only):
                            continue
                        text = d.view.columns[ch][1].strip()
                        row = tracks.setdefault(str(s.number), {})
                        row[str(slot)] = None if text in ("", "--") else {"text": text, "name": self.cache.abbrev.get(text)}
                self.inventory.update(tracks)
                return b._result(action, True, "verified", t0, after={"tracks": tracks})
            except ModeError as e:
                return b._result(action, False, "unverified", t0, note=str(e))
            finally:
                d.leave_safely()

    def _begin(self, action: str, strip, number, slot, t0):
        if not 1 <= slot <= 15:
            return self.b._result(action, False, "skipped", t0, note="slot은 1-15")
        ch = self.b._resolve(strip, number, action, t0)
        return ch

    def params(self, strip: int | None, number: int | None, slot: int) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_params"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = self._begin(action, strip, number, slot, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "slot": slot}
            try:
                self._fresh()
                d.focus(ch)
                full, abbrev, pages = self._open_edit(ch, slot)
                observed = self._read_pages(pages)
                self._merge_items(full, pages, observed)
                self.cache.save()
                table = {x["index"]: x for x in self._table(full, pages)["items"]}
                out = [{"index": o["index"], "short": o["short"], "name": table[o["index"]].get("name"),
                        "value": o["value"], "text": o["text"]} for o in observed]
                return b._result(action, True, "verified", t0, target=target,
                                 after={"plugin": full, "abbrev": abbrev, "slot": slot, "pages": pages, "params": out})
            except SlotEmpty:
                return b._result(action, False, "skipped", t0, target=target, note=f"슬롯 {slot}이 비어 있음")
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
            finally:
                d.leave_safely()

    def get(self, strip: int | None, number: int | None, slot: int, param) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_get"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = self._begin(action, strip, number, slot, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "slot": slot}
            try:
                self._fresh()
                d.focus(ch)
                full, _abbrev, pages = self._open_edit(ch, slot)
                item = self._locate(full, pages, param)
                col = self._goto_param(item)
                v = d.read_column(col)[1]
                return b._result(action, True, "verified", t0, target=target, after=self._param_dict(full, slot, item, v))
            except SlotEmpty:
                return b._result(action, False, "skipped", t0, target=target, note=f"슬롯 {slot}이 비어 있음")
            except ParamNotFound as e:
                return b._result(action, False, "skipped", t0, target=target, note=e.note)
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
            finally:
                d.leave_safely()

    def set(self, strip: int | None, number: int | None, slot: int, param, value,
            tolerance: float | None = None) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_set"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = self._begin(action, strip, number, slot, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "slot": slot}
            try:
                self._fresh()
                d.focus(ch)
                full, _abbrev, pages = self._open_edit(ch, slot)
                item = self._locate(full, pages, param)
                col = self._goto_param(item)
                before_v = d.read_column(col)[1]
                before = self._param_dict(full, slot, item, before_v)
                numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
                if not numeric and isinstance(value, str):
                    try:
                        value, numeric = float(value), True
                    except ValueError:
                        numeric = False
                if numeric:
                    mapping = _map_from(item.get("map"))
                    if mapping is None:
                        d.flip(True)
                        mapping, _lo, _hi = probe_mapping(d, col)          # 범위를 모르면 페이더 1·16383으로 프로빙
                        if mapping is not None:
                            item["map"] = _map_to(mapping)
                            self.cache.save()
                    tol = tolerance if tolerance is not None else tolerance_for(float(value), before_v.unit)
                    out = set_numeric(d, col, float(value), mapping, tol, b.faders)
                else:
                    want = ("On" if value else "Off") if isinstance(value, bool) else str(value)
                    out = set_enum(d, col, want)
                after = self._param_dict(full, slot, item, out.value)
                if out.ok and out.note == "already":
                    return b._result(action, True, "skipped", t0, target=target, before=before, after=after, note="already")
                return b._result(action, out.ok, "verified" if out.ok else "unverified", t0, target=target,
                                 before=before, after=after, note=out.note)
            except SlotEmpty:
                return b._result(action, False, "skipped", t0, target=target, note=f"슬롯 {slot}이 비어 있음")
            except ParamNotFound as e:
                return b._result(action, False, "skipped", t0, target=target, note=e.note)
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
            finally:
                d.leave_safely()
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest -q`
Expected: 전부 PASS. `test_params_…`의 `"text": "-20.0 d"`는 7칸 열 잘림(실측 규칙)이다. `get(…, 11)`은 `pages*8=16` 안이라 `_locate`가 페이지를 읽어도 11번 자리가 비어 있어 `ParamNotFound` → skipped.

- [ ] **Step 6: 커밋**

```bash
git add src/logic_mcp/logic/assign.py src/logic_mcp/logic/modes.py src/logic_mcp/logic/plugins/match.py src/logic_mcp/logic/commands.py tests/test_assign_plugin.py
git commit -m "feat(plugin): PluginCommands list/params/get/set — 반 틱 이름 드러내기, 편집 뷰 페이지 읽기, 표 학습·프로빙

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: `PluginCommands` — insert / remove / bypass / scan

**Files:**
- Create: `src/logic_mcp/logic/plugins/scan.py`
- Modify: `src/logic_mcp/logic/assign.py`, `src/logic_mcp/logic/modes.py`(`shift_press_vpot`)
- Test: `tests/test_assign_plugin.py`(추가)

**Interfaces:**
- Produces:
  - `ModeDriver.shift_press_vpot(ch) -> bool`
  - `scan.rewind_to_empty(d, ch) -> None` (오버레이가 `--`가 될 때까지 -63씩, 최대 80회), `scan.scan_list(d, ch) -> list[str]` (`--`부터 +2씩, 같은 이름 3회 또는 `--` 재등장에서 끝)
  - `PluginCommands.insert(strip, number, slot, plugin, replace=False)`, `remove(strip, number, slot)`, `bypass(strip, number, slot, on)`, `scan(force=False)`
  - `insert`의 `after`: `{"slot", "plugin", "abbrev", "replaced": str | None}`; `scan`의 `after`: `{"count", "path", "strip", "slot"}`

- [ ] **Step 1: 실패하는 테스트**

`tests/test_assign_plugin.py` 끝에 추가:

```python
def test_insert_by_name_rewinds_and_confirms(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    r = cmds.plugin.insert(strip=2, number=None, slot=1, plugin="compressor")
    assert r.verified == "verified" and logic.tracks[1].inserts[1] == "Compressor"
    assert r.after == {"slot": 1, "plugin": "Compressor", "abbrev": "Compre", "replaced": None}
    assert cache.abbrev["Compre"] == "Compressor" and surface.state.view.kind == "pan" and logic.selected == 0


def test_insert_refuses_occupied_then_replaces_with_flag(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[1].insert(1, "Channel EQ")
    r = cmds.plugin.insert(2, None, 1, "Compressor")
    assert r.verified == "skipped" and "replace" in r.note and logic.tracks[1].inserts[1] == "Channel EQ"
    r = cmds.plugin.insert(2, None, 1, "Compressor", replace=True)
    assert r.verified == "verified" and logic.tracks[1].inserts[1] == "Compressor" and r.after["replaced"] == "Channe"


def test_insert_unknown_or_ambiguous_name_sends_nothing(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    n = len(fake.sent)
    r = cmds.plugin.insert(2, None, 1, "Zebra")
    assert r.verified == "skipped" and "scan" in r.note
    r = cmds.plugin.insert(2, None, 1, "EQ")
    assert r.verified == "skipped" and "Parametric EQ" in r.note and "Channel EQ" in r.note
    assert len(fake.sent) == n


def test_remove_and_bypass(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(1, "Channel EQ")
    r = cmds.plugin.bypass(1, None, 1, True)
    assert r.verified == "verified" and 1 in logic.tracks[0].bypassed and r.after["text"].startswith("*")
    assert cmds.plugin.bypass(1, None, 1, True).verified == "skipped"
    assert cmds.plugin.bypass(1, None, 1, False).verified == "verified" and not logic.tracks[0].bypassed
    r = cmds.plugin.remove(1, None, 1)
    assert r.verified == "verified" and logic.tracks[0].inserts[1] is None and logic.tracks[0].eq is None
    assert cmds.plugin.remove(1, None, 1).verified == "skipped"
    assert cmds.plugin.bypass(1, None, 1, True).verified == "skipped"
    assert surface.state.view.kind == "pan"


def test_scan_builds_list_without_inserting(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    r = cmds.plugin.scan()
    assert r.verified == "verified" and r.after["count"] == len(PLUGIN_LIST) and r.after["slot"] == 1
    assert cache.items == PLUGIN_LIST and cache.source == "scan" and cache.path.exists() and cache.scanned_at
    assert all(v is None for t in logic.tracks for v in t.inserts.values())
    assert surface.state.view.kind == "pan"
    assert cmds.plugin.scan().verified == "skipped"
    assert cmds.plugin.scan(force=True).verified == "verified"


def test_scan_needs_an_empty_slot(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    for t in logic.tracks:
        for i in range(1, 16):
            t.insert(i, "Tuner")
    r = cmds.plugin.scan()
    assert r.verified == "skipped" and "빈 슬롯" in r.note and surface.state.view.kind == "pan"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_assign_plugin.py -q`
Expected: `AttributeError: 'PluginCommands' object has no attribute 'insert'`.

- [ ] **Step 3: 구현**

`modes.py`의 `press_vpot` 뒤에 추가:

```python
    def shift_press_vpot(self, ch: int) -> bool:
        """SHIFT를 누른 채 V-Pot 누름(플러그인 바이패스 토글, Apple 문서·라이브 체크 대상)."""
        self._mark()
        self.surface.send(P.button_down(P.Note.SHIFT))
        self._press(P.Note.VPOT_PUSH + ch)
        self.surface.send(P.button_up(P.Note.SHIFT))
        return self._wait_change()
```

`src/logic_mcp/logic/plugins/scan.py`:

```python
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
        if not changed or text == names[-1] or not text:
            stale += 1
            if stale >= STALE_LIMIT:
                break
            continue
        stale = 0
        if text == "--":
            break                                     # 한 바퀴 돌아 처음으로
        names.append(text)
    return names
```

`assign.py`의 `PluginCommands`에 메서드 추가(임포트에 `from datetime import datetime`, `from .plugins.scan import rewind_to_empty, scan_list` 추가):

```python
    def insert(self, strip: int | None, number: int | None, slot: int, plugin: str,
               replace: bool = False) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_insert"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            idx, cands = find(self.cache.items, plugin)
            if idx is None:
                note = (f"{plugin!r}가 여럿에 맞음: {cands}" if cands
                        else f"{plugin!r}가 목록({self.cache.source}, {len(self.cache.items)}개)에 없음. `logic_plugin scan` 뒤 다시 시도")
                return b._result(action, False, "skipped", t0, note=note)
            ch = self._begin(action, strip, number, slot, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "slot": slot}
            want = self.cache.items[idx]
            try:
                self._fresh()
                d.focus(ch)
                d.enter("plugin_mixer")
                d.slot_to(slot)
                current = self._slot_text(ch)
                occupied = current not in ("", "--")
                if occupied and not replace:
                    return b._result(action, False, "skipped", t0, target=target,
                                     note=f"슬롯 {slot}에 {current!r}가 있음. 교체하려면 replace=true")
                rewind_to_empty(d, ch)
                d.tick(ch, 2 * idx)
                shown = strip_suffix(d.read_overlay_text(ch))
                for _ in range(3):                                   # 목록이 캐시와 조금 어긋나면 근처에서 찾는다
                    if normalize(shown) == normalize(want):
                        break
                    j, _c = find(self.cache.items, shown)
                    if j is None:
                        break
                    d.tick(ch, 2 * (idx - j))
                    shown = strip_suffix(d.read_overlay_text(ch))
                if normalize(shown) != normalize(want):
                    return b._result(action, False, "unverified", t0, target=target,
                                     note=f"목록 위치 {idx}에 {shown!r}가 보임(기대 {want!r}). 설치된 플러그인이 달라진 듯. `logic_plugin scan` 권장")
                d.press_vpot(ch)
                if d.view.kind != "plugin_edit":
                    return b._result(action, False, "unverified", t0, target=target,
                                     note=f"확인 뒤 편집 뷰가 아니라 {d.view.kind}")
                d.settle_smart()
                d.enter("plugin_mixer")
                d.slot_to(slot)
                abbrev = self._slot_text(ch)
                self.cache.learn_abbrev(abbrev, want)
                self.cache.save()
                return b._result(action, True, "verified", t0, target=target, before={"slot": slot, "text": current},
                                 after={"slot": slot, "plugin": want, "abbrev": abbrev,
                                        "replaced": current if occupied else None})
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
            finally:
                d.leave_safely()

    def remove(self, strip: int | None, number: int | None, slot: int) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_remove"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = self._begin(action, strip, number, slot, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "slot": slot}
            try:
                self._fresh()
                d.focus(ch)
                d.enter("plugin_mixer")
                d.slot_to(slot)
                current = self._slot_text(ch)
                if current in ("", "--"):
                    return b._result(action, True, "skipped", t0, target=target, note="already")
                rewind_to_empty(d, ch)
                d.press_vpot(ch)                                     # `--` 확정 = 제거(실측: 빈 편집 뷰 상태가 됨)
                d.enter("plugin_mixer")
                d.slot_to(slot)
                after = self._slot_text(ch)
                ok = after in ("", "--")
                return b._result(action, ok, "verified" if ok else "unverified", t0, target=target,
                                 before={"slot": slot, "text": current}, after={"slot": slot, "text": after},
                                 note="" if ok else "제거 뒤에도 슬롯에 이름이 보임")
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
            finally:
                d.leave_safely()

    def bypass(self, strip: int | None, number: int | None, slot: int, on: bool) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_bypass"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = self._begin(action, strip, number, slot, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "slot": slot}
            try:
                self._fresh()
                d.focus(ch)
                d.enter("plugin_mixer")
                d.slot_to(slot)
                current = self._slot_text(ch)
                if current in ("", "--"):
                    return b._result(action, False, "skipped", t0, target=target, note=f"슬롯 {slot}이 비어 있음")
                if current.startswith("*") == on:
                    return b._result(action, True, "skipped", t0, target=target, after={"slot": slot, "text": current}, note="already")
                d.shift_press_vpot(ch)
                after = self._slot_text(ch)
                ok = after.startswith("*") == on
                return b._result(action, ok, "verified" if ok else "unverified", t0, target=target,
                                 before={"slot": slot, "text": current}, after={"slot": slot, "text": after},
                                 note="" if ok else "SHIFT+V-Pot 뒤 `*` 표시가 기대와 다름")
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
            finally:
                d.leave_safely()

    def scan(self, force: bool = False) -> "ToolResult":
        b, d, action = self.b, self.d, "plugin_scan"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            if self.cache.user_list and not force:
                return b._result(action, True, "skipped", t0, after=self.cache.to_resource(),
                                 note=f"already: {self.cache.scanned_at}에 스캔한 {len(self.cache.user_list)}개. 다시 하려면 force=true")
            try:
                self._fresh()
                d.enter("plugin_mixer")
                found: tuple[int, int] | None = None
                for slot in range(1, 16):
                    d.slot_to(slot)
                    for ch, s in enumerate(b.surface.state.strips):
                        if s.number is not None and d.view.columns[ch][1].strip() == "--":
                            found = (ch, slot)
                            break
                    if found:
                        break
                if found is None:
                    return b._result(action, False, "skipped", t0, note="스캔에 쓸 빈 슬롯이 보이는 뱅크에 없음. 빈 슬롯이 있는 트랙을 뱅크에 띄우고 다시")
                ch, slot = found
                names = scan_list(d, ch)
                self.cache.user_list = names
                self.cache.scanned_at = datetime.now().isoformat(timespec="seconds")
                self.cache.save()
                d.leave(keep_select=True)                            # 미리 선택 취소(삽입 없음)
                d.enter("plugin_mixer")
                d.slot_to(slot)
                still_empty = d.view.columns[ch][1].strip() == "--"
                return b._result(action, still_empty, "verified" if still_empty else "unverified", t0,
                                 after={"count": len(names), "path": str(self.cache.path), "strip": ch + 1, "slot": slot},
                                 note="" if still_empty else "스캔 뒤 슬롯이 비어 있지 않음(확인 누름이 섞였을 수 있음)")
            except ModeError as e:
                return b._result(action, False, "unverified", t0, note=str(e))
            finally:
                d.leave_safely()
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest -q`
Expected: 전부 PASS. 가짜의 미리 선택 위치는 0..2·(목록-1)에서 포화하므로 되감기(-63)는 한 번에 `--`에 닿고, 끝에서 +2는 같은 이름을 반복해 3회 뒤 멈춘다.

- [ ] **Step 5: 커밋**

```bash
git add src/logic_mcp/logic/plugins/scan.py src/logic_mcp/logic/assign.py src/logic_mcp/logic/modes.py tests/test_assign_plugin.py
git commit -m "feat(plugin): insert/remove/bypass/scan — 되감기·틱 이동·오버레이 이름 확인·확정, 목록 스캔 캐시

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: MCP 도구·리소스 노출

**Files:**
- Modify: `src/logic_mcp/server/tools.py`, `src/logic_mcp/server/resources.py`, `src/logic_mcp/logic/commands.py`(`status()`에 `view_kind`)
- Test: `tests/test_server.py`

**Interfaces:**
- Produces: 툴 `logic_eq(action: get|set, strip, number, band, param, value, allow_insert)`, `logic_plugin(action: list|params|get|set|insert|remove|bypass|scan, strip, number, slot, param, value, plugin, replace, on, tolerance, force)`; 리소스 `logic://plugins`, `logic://inserts`, `logic://view`; `status()["view_kind"]`.

- [ ] **Step 1: 실패하는 테스트**

`tests/test_server.py` 끝에 추가:

```python
from logic_mcp.logic.plugins.cache import PluginCache
from tests.fake_assign import PLUGIN_LIST, make_assign_logic


@pytest.fixture
def assign_setup(tmp_path):
    surface, fake, logic = make_assign_logic()
    cache = PluginCache("fake", list(PLUGIN_LIST), [], {}, {}, None, tmp_path / "plugins-fake.json")
    cmds = Commands(surface, FaderTable.load(), sleep=logic.sleep, logic_running=lambda: True, plugin_cache=cache)
    return create_server(cmds, start_surface=False), logic


@pytest.mark.anyio
async def test_spec2_tools_and_resources_listed(setup):
    mcp, fake = setup
    async with Client(mcp) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        assert {"logic_eq", "logic_plugin"} <= set(tools)
        props = set(tools["logic_plugin"].input_schema["properties"])
        assert {"action", "strip", "number", "slot", "param", "value", "plugin", "replace", "on", "tolerance", "force"} <= props
        assert set(tools["logic_eq"].input_schema["properties"]) >= {"action", "band", "param", "value", "allow_insert"}
        uris = {str(r.uri) for r in (await client.list_resources()).resources}
        assert {"logic://plugins", "logic://inserts", "logic://view"} <= uris


@pytest.mark.anyio
async def test_spec2_calls_via_client(assign_setup):
    mcp, logic = assign_setup
    async with Client(mcp) as client:
        r = await client.call_tool("logic_eq", {"action": "get", "strip": 2})
        assert r.structured_content["after"] == {"has_eq": False, "bands": {}}
        r = await client.call_tool("logic_eq", {"action": "set", "strip": 2})
        assert r.structured_content["verified"] == "skipped" and "band" in r.structured_content["note"]
        r = await client.call_tool("logic_eq", {"action": "set", "strip": 2, "band": 3, "param": "gain", "value": -3})
        assert r.structured_content["verified"] == "verified" and logic.tracks[1].eq[2][1].value == -3.0
        r = await client.call_tool("logic_plugin", {"action": "insert", "strip": 2, "slot": 2, "plugin": "Compressor"})
        assert r.structured_content["verified"] == "verified" and logic.tracks[1].inserts[2] == "Compressor"
        r = await client.call_tool("logic_plugin", {"action": "set", "strip": 2, "slot": 2, "param": "Thresh", "value": -30})
        assert r.structured_content["verified"] == "verified"
        r = await client.call_tool("logic_plugin", {"action": "params", "strip": 2})
        assert r.structured_content["verified"] == "skipped" and "slot" in r.structured_content["note"]
        r = await client.call_tool("logic_plugin", {"action": "list"})
        assert r.structured_content["after"]["tracks"]["16"]["2"]["name"] == "Compressor"
        view = json.loads((await client.read_resource("logic://view")).contents[0].text)
        assert view["kind"] == "pan" and view["flip"] is False
        plugins = json.loads((await client.read_resource("logic://plugins")).contents[0].text)
        assert plugins["items"][6] == {"index": 6, "name": "Compressor"} and plugins["source"] == "bundled"
        inserts = json.loads((await client.read_resource("logic://inserts")).contents[0].text)
        assert inserts["16"]["2"]["text"] == "Compre"
        status = await client.call_tool("logic_session", {"action": "status"})
        assert status.structured_content["after"]["view_kind"] == "pan"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_server.py -q`
Expected: 두 테스트 실패(`logic_eq` 없음).

- [ ] **Step 3: 구현**

`tools.py`에 추가(기존 `Strip`, `Number` 아래):

```python
Slot = Annotated[int | None, Field(ge=1, le=15, description="인서트 슬롯 1-15")]
```

`register_tools` 끝에 추가:

```python
    @mcp.tool(name="logic_eq", annotations=ToolAnnotations(idempotent_hint=True),
              description="Channel EQ. get: 8밴드 전체(EQ가 없으면 has_eq=false, 삽입하지 않음). "
                          "set: band 1-8, param freq|gain|slope|q|on, value. 밴드 1·8은 gain 대신 slope(6/12/18/24/36/48). "
                          "EQ가 없으면 allow_insert=true일 때만 Channel EQ를 삽입한다. 끝나면 PAN 모드로 돌아간다.")
    def logic_eq(
        action: Literal["get", "set"],
        strip: Strip = None,
        number: Number = None,
        band: Annotated[int | None, Field(ge=1, le=8)] = None,
        param: Literal["freq", "gain", "slope", "q", "on"] | None = None,
        value: Annotated[float | bool | None, Field(description="freq Hz, gain dB, slope 6..48, q 수치, on 불")] = None,
        allow_insert: bool = True,
    ) -> ToolResult:
        if action == "get":
            return commands.eq.get(strip, number)
        if band is None or param is None or value is None:
            return ToolResult(ok=False, verified="skipped", action="eq_set", note="set에는 band, param, value가 필요")
        return commands.eq.set(strip, number, band, param, value, allow_insert)

    @mcp.tool(name="logic_plugin",
              description="인서트 플러그인. list: 인벤토리(strip/number 없으면 뱅크 전체). params: 플러그인 파라미터 전체(인덱스·축약명·값). "
                          "get/set: param은 이름(부분 일치) 또는 인덱스, value는 숫자 또는 선택지 텍스트. insert: plugin 이름(부분 일치), "
                          "차 있으면 replace=true 필요. remove. bypass(on). scan: 삽입 메뉴 전 범위 스캔(30~90초, 삽입 없음, 빈 슬롯 필요). "
                          "편집 뷰 진입 시 Logic이 플러그인 창을 열고 닫는다. 끝나면 PAN 모드로 돌아간다.")
    def logic_plugin(
        action: Literal["list", "params", "get", "set", "insert", "remove", "bypass", "scan"],
        strip: Strip = None,
        number: Number = None,
        slot: Slot = None,
        param: Annotated[str | int | None, Field(description="파라미터 이름(부분 일치) 또는 1부터 인덱스")] = None,
        value: Annotated[float | str | bool | None, Field(description="set: 숫자 또는 선택지 텍스트(예: \"On\")")] = None,
        plugin: Annotated[str | None, Field(description="insert: 플러그인 이름(부분 일치)")] = None,
        replace: bool = False,
        on: Annotated[bool | None, Field(description="bypass: true=바이패스")] = None,
        tolerance: Annotated[float | None, Field(gt=0, description="set: 허용 오차(기본 dB 0.1, 그 밖 1%)")] = None,
        force: bool = False,
    ) -> ToolResult:
        name = f"plugin_{action}"
        if action == "scan":
            return commands.plugin.scan(force)
        if action == "list":
            return commands.plugin.list(strip, number)
        if slot is None:
            return ToolResult(ok=False, verified="skipped", action=name, note="slot(1-15)이 필요")
        if action == "params":
            return commands.plugin.params(strip, number, slot)
        if action == "get":
            if param is None:
                return ToolResult(ok=False, verified="skipped", action=name, note="get에는 param(이름 또는 인덱스)이 필요")
            return commands.plugin.get(strip, number, slot, param)
        if action == "set":
            if param is None or value is None:
                return ToolResult(ok=False, verified="skipped", action=name, note="set에는 param과 value가 필요")
            return commands.plugin.set(strip, number, slot, param, value, tolerance)
        if action == "insert":
            if not plugin:
                return ToolResult(ok=False, verified="skipped", action=name, note="insert에는 plugin 이름이 필요")
            return commands.plugin.insert(strip, number, slot, plugin, replace)
        if action == "remove":
            return commands.plugin.remove(strip, number, slot)
        if on is None:
            return ToolResult(ok=False, verified="skipped", action=name, note="bypass에는 on(true/false)이 필요")
        return commands.plugin.bypass(strip, number, slot, on)
```

`resources.py`의 `register_resources` 끝에 추가:

```python
    @mcp.resource("logic://plugins", description="플러그인 목록 캐시(번들+스캔 병합)와 알려진 파라미터 표")
    def plugins() -> str:
        return json.dumps(commands.plugin.cache.to_resource(), ensure_ascii=False)

    @mcp.resource("logic://inserts", description="마지막 logic_plugin list 결과(트랙 번호 → 슬롯 → 플러그인)")
    def inserts() -> str:
        return json.dumps(commands.plugin.inventory, ensure_ascii=False)

    @mcp.resource("logic://view", description="현재 어사인먼트 뷰(종류·번호·페이지·열)와 Flip")
    def view() -> str:
        st = commands.surface.state
        v = st.view
        return json.dumps({"kind": v.kind, "index": v.index, "page": v.page, "header": v.header,
                           "columns": [list(c) for c in v.columns], "flip": st.assignment.flip}, ensure_ascii=False)
```

`commands.py`의 `status()` 딕셔너리에 `"view_kind": st.view.kind,` 추가(`"assignment_mode"` 다음 줄).

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest -q`
Expected: 전부 PASS.

- [ ] **Step 5: 커밋**

```bash
git add src/logic_mcp/server/tools.py src/logic_mcp/server/resources.py src/logic_mcp/logic/commands.py tests/test_server.py
git commit -m "feat(server): logic_eq·logic_plugin 툴, logic://plugins|inserts|view 리소스, status.view_kind

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: 실기 검증 스크립트와 문서

**Files:**
- Create: `scripts/live_check2.py`
- Modify: `docs/mcu-protocol.md`, `docs/progress.md`, `README.md`

**Interfaces:**
- Consumes: 전체.
- 실기 실행은 **컨트롤러(Fable)가 한다**(Logic·CoreMIDI 접근). 구현자는 스크립트와 문서만 쓴다. 사용자 트랙 22채널 테스트 프로젝트(저장 안 함)에서 돌린다.

- [ ] **Step 1: 스크립트**

`scripts/live_check2.py`:

```python
"""스펙 2a 실기 검증: EQ·플러그인 명령을 실제 Logic에서 돌려 결과 표를 찍는다. 테스트 프로젝트(저장 안 함)에서 실행.
사용: uv run python scripts/live_check2.py [strip=1] [--scan]"""
import sys

from logic_mcp.server.main import build

args = [a for a in sys.argv[1:] if not a.startswith("--")]
strip = int(args[0]) if args else 1
commands, surface = build()
surface.start()


def run(name, fn):
    r = fn()
    print(f"{name:30} ok={r.ok!s:5} {r.verified:10} {r.elapsed_ms:5}ms {r.note[:90]}")
    return r


try:
    print("Logic이 서피스를 설치하기를 기다리는 중…")
    print(commands.wait_ready(60).model_dump())
    run("configure", commands.configure)
    r = run("eq get (before)", lambda: commands.eq.get(strip, None))
    print("  has_eq:", r.after and r.after.get("has_eq"))
    run("eq set b3 freq 1000", lambda: commands.eq.set(strip, None, 3, "freq", 1000.0))
    run("eq set b3 gain -3", lambda: commands.eq.set(strip, None, 3, "gain", -3.0))
    run("eq set b1 slope 24", lambda: commands.eq.set(strip, None, 1, "slope", 24))
    run("eq set b8 on False", lambda: commands.eq.set(strip, None, 8, "on", False))
    run("eq set b4 q 2.0", lambda: commands.eq.set(strip, None, 4, "q", 2.0))
    r = run("eq get (after)", lambda: commands.eq.get(strip, None))
    for k in ("1", "3", "4", "7", "8"):
        print(f"  band {k}:", r.after and r.after.get("bands", {}).get(k))
    r = run("plugin list (bank)", lambda: commands.plugin.list(None, None))
    print("  inserts:", r.after and {n: {s: v and v["text"] for s, v in row.items() if v} for n, row in r.after["tracks"].items()})
    run("plugin insert Compressor s2", lambda: commands.plugin.insert(strip, None, 2, "Compressor"))
    r = run("plugin params s2", lambda: commands.plugin.params(strip, None, 2))
    print("  pages:", r.after and r.after.get("pages"))
    print("  params:", [(p["index"], p["short"], p["text"]) for p in (r.after or {}).get("params", [])])
    run("plugin set Thresh -20", lambda: commands.plugin.set(strip, None, 2, "Thresh", -20.0))
    run("plugin get Thresh", lambda: commands.plugin.get(strip, None, 2, "Thresh"))
    run("plugin bypass s2 on", lambda: commands.plugin.bypass(strip, None, 2, True))
    run("plugin bypass s2 off", lambda: commands.plugin.bypass(strip, None, 2, False))
    run("plugin remove s2", lambda: commands.plugin.remove(strip, None, 2))
    run("plugin remove s1 (Channel EQ)", lambda: commands.plugin.remove(strip, None, 1))
    if "--scan" in sys.argv:
        r = run("plugin scan (force)", lambda: commands.plugin.scan(force=True))
        print("  scan:", r.after)
    st = commands.status()
    print("status:", {k: st[k] for k in ("state", "assignment_mode", "flip", "view_kind")})
finally:
    surface.stop()
```

- [ ] **Step 2: 문서**

`docs/mcu-protocol.md` 끝에 "## 스펙 2 추가 실측(어사인먼트 모드)" 절을 추가하고 스펙 2 설계 문서 **부록 A** 내용을 그대로 옮긴다(2자리 코드, 오버레이 2.0초, 깜박임, V-Pot N/2, Flip 매핑, 뷰별 LCD 레이아웃, 목록 순서).

`README.md`의 툴 표에 `logic_eq`, `logic_plugin` 행과 리소스 `logic://plugins|inserts|view`를 추가하고, "플러그인 목록은 번들(Logic 12.0.1 내장) + `logic_plugin scan`(사용자 캐시 `~/.logic-mcp/plugins-<버전>.json`)" 한 문단, 부작용(선택 변경·Channel EQ 자동 삽입·플러그인 창) 한 문단을 적는다.

`docs/progress.md`에 "## 스펙 2a" 절: Task 1~11 완료 표시 자리, 실기 결과 자리(컨트롤러가 채움), 다음(2b: 센드·번들 생성·스킬).

- [ ] **Step 3: 커밋(구현자)**

```bash
git add scripts/live_check2.py docs/mcu-protocol.md docs/progress.md README.md
git commit -m "docs(2a): live_check2 스크립트, 프로토콜 실측 추가, README 툴 표, 진행 기록

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 4: 실기 검증(컨트롤러)**

Logic에 트랙 22채널 테스트 프로젝트가 열린 상태에서:

```bash
uv run python scripts/live_check2.py 1 2>&1 | tee /tmp/live_check2.log
```
Expected: 모든 줄이 `verified` 또는 `skipped(already)`. 확인할 실측 미확정 사항: (1) EQ 밴드 7·8 열 축약명(`HiShF HiShGa HiShQ HSO/Of`, `HiCutF HiCutS HiCutQ HCO/Of` 추정) — 다르면 `EQ_SHORT`와 가짜를 고친다, (2) `bypass`의 SHIFT+V-Pot이 `*`를 붙이는지 — 안 되면 unverified로 두고 progress.md에 기록, (3) 스트립 7·8의 오버레이 시작 열(`min(ch*7, 35)` 가정) — `eq set`을 strip 7에서 한 번 더, (4) `plugin params`의 페이지 헤더 `Page n/N` 위치와 NAME/VALUE 전환 뒤 LCD, (5) `--scan`으로 전 범위 스캔 시간과 항목 수(캐시 파일 생성 확인). 결함이 나오면 ruling으로 코드를 고치고 테스트를 추가한 뒤 재실행한다. 결과는 `docs/progress.md`에 적는다.

