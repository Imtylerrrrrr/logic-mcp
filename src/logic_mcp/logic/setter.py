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
    # 틱 미세 보정. Hz·log 매핑(Q 등)은 로그 영역에서 틱당 변화를 추정한다(실측 U: 틱당 비율 일정)
    log_domain = (cur.unit == "Hz" or (mapping is not None and mapping.type == "log")) and target > 0
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
