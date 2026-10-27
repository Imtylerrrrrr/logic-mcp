"""LCD 열(7칸)·오버레이 값 텍스트 파서와 Flip 페이더 매핑. I/O 없음."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from ..mcu.protocol import MAX_FADER
from .faders import FaderTable

# 숫자·단위 사이 공백 1칸까지: 21칸 창에 이웃 열이 섞인 '1.00   High'를 숫자로 읽지 않게(실측 2026-10-20)
_NUM_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?|-oo) ?([A-Za-z/%:0-9]*)\s*$")
_UNITS = {"": None, "hz": "Hz", "khz": "kHz", "db": "dB", "d": "dB", "db/oct": "dB/Oct",
          "db/o": "dB/Oct", "db/oc": "dB/Oct",        # 7자 열에서 잘린 `18 dB/O`(실측 R)
          "ms": "ms", "s": "s", "%": "%", "st": "st", "ct": "ct", "smp": "smp", ":1": ":1"}
LCD_CELL = 6            # LCD 한 칸 폭(열 7칸 중 값 6자). 칸을 채운 표시는 단위가 잘렸을 수 있다(실측 2026-10-27 Compressor Release '5000.0')


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
    if m:
        # 앞 토큰이 숫자면 단위가 표에 없어도 숫자로 읽는다(단위 표는 정규화만 맡음, 실측 R)
        num, raw_unit = m.group(1), m.group(2)
        unit = _UNITS[raw_unit.lower()] if raw_unit.lower() in _UNITS else raw_unit
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


def _unit_compatible(lo: Value, hi: Value) -> bool:
    """같은 단위이거나, 짧은 단위가 없거나(None) 긴 단위의 접두('m'은 'ms')이고 양쪽 텍스트가 칸 폭을 채우면
    잘림으로 보고 같은 단위로 친다('5.0 ms'/'5000.0', '5.0 ms'/'160.0 m'). '3 dB'처럼 짧은 표시는 잘림이 아니다."""
    if lo.unit == hi.unit:
        return True
    short, long_ = sorted((lo, hi), key=lambda v: len(v.unit or ""))
    if short.unit is not None and not (long_.unit or "").startswith(short.unit):
        return False
    return len(short.text) >= LCD_CELL and len(long_.text) >= LCD_CELL


def infer_mapping(lo: Value, hi: Value) -> Mapping | None:
    """페이더 1·16383에서 읽은 최소·최대 값으로 유형을 추정한다. 열거형은 None."""
    if lo.kind != "number" or hi.kind != "number" or lo.number is None or hi.number is None:
        return None
    if not (math.isfinite(lo.number) and math.isfinite(hi.number)) or lo.number == hi.number:
        return None
    # 's'↔'ms'처럼 단위가 바뀌는 표시는 선형 표로 못 쓴다(실측 2026-10-20 Space Designer Length: 1→'91.4 s', 16383→'183 ms')
    if not _unit_compatible(lo, hi):
        return None
    if lo.number > 0 and hi.number > 0 and max(lo.number, hi.number) / min(lo.number, hi.number) > 100:
        return Mapping("log", lo.number, hi.number)    # 넓은 양수 범위는 로그(실측 2026-10-27 Compressor Release 5~5000 ms). 비율 100(0.10~10.0)은 선형 유지
    if lo.unit == "Hz" and lo.number > 0:
        return Mapping("log", lo.number, hi.number)
    return Mapping("linear", lo.number, hi.number)


def tolerance_for(target: float, unit: str | None) -> float:
    """기본 허용 오차. 실전 F4(10/24): dB 0.1은 페이더 보정이 ±0.2 안에서 흔들려(+3.2) 실패, Hz 1 %는 3500→3380·5000→5200에서 실패."""
    if unit == "dB":
        return 0.2
    if unit is None:                                   # Q 등 단위 없는 숫자: 표시가 유효숫자 3자리라 2 %(실측 T)
        return round(max(abs(target) * 0.02, 0.01), 6)
    return round(max(abs(target), 1.0) * 0.02, 6)


def within(actual: float, target: float, tolerance: float) -> bool:
    return math.isfinite(actual) and abs(actual - target) <= tolerance
