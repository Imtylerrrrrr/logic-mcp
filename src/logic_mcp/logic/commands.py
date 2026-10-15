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
from .modes import ModeDriver

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
        self.modes = ModeDriver(surface, sleep)

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
            st0 = self.surface.state
            if st0.assignment.flip or st0.view.kind != "pan" or st0.assignment.mode != "pan":
                self.modes.leave_safely()
            mode = self.surface.state.assignment.mode
            if mode != "pan" or self.surface.state.view.kind != "pan":
                return self._result(action, False, "skipped", t0,
                                    note=f"V-Pot 할당 모드가 {mode}/{self.surface.state.view.kind}. PAN 복귀 실패: {self.modes.last_leave_error}")
            ch = self._resolve(strip, number, action, t0)
            if isinstance(ch, ToolResult):
                return ch
            before = self._strip_view(ch)
            current = parse_pan_text(self.surface.state.strips[ch].value_text)
            revealed = False
            if current is None:
                self.surface.send(P.vpot_turn(ch, 1))
                self.surface.wait_for(lambda s: parse_pan_text(s.strips[ch].value_text) is not None, PAN_TIMEOUT)
                self.surface.wait_settled(0.3)
                current = parse_pan_text(self.surface.state.strips[ch].value_text)
                revealed = True
            if current is None:
                return self._result(action, False, "skipped", t0, target=self._target(ch),
                                    note="LCD 2행이 팬 값이 아님. `logic_session configure`로 값 표시 모드 확인")
            if current == pan and not revealed:
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
                                before=before, after=after,
                                note=(("LCD에 팬 값을 드러내려고 +1 돌린 뒤 보정. " if revealed else "") +
                                 ("" if ok else "LCD 팬 값이 목표와 다름")))

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
            if st.connection.state != "ready":
                return self._result(action, False, "skipped", t0,
                                    note=f"상태가 {st.connection.state}. 먼저 logic_session wait_ready")
            done: list[str] = []
            # 1) 번호 접두사
            if not any(s.number is not None for s in st.strips):
                self._move_bank(lambda: self._press_with_option(P.Note.NAME_VALUE))
                if not any(s.number is not None for s in self.surface.state.strips):
                    self._move_bank(lambda: self._press_with_option(P.Note.NAME_VALUE))
                    return self._result(action, False, "unverified", t0, after=self.status(),
                                        note="OPTION+NAME/VALUE 뒤에도 LCD에 번호가 없음 (되돌려 눌렀음)")
                done.append("numbers")
            if not self.surface.state.strips[0].fader_known:
                return self._result(action, False, "unverified", t0, after=self.status(),
                                    note="페이더 1 위치를 아직 못 받음. 페이더 1을 살짝 움직이거나 프로젝트를 다시 연 뒤 configure를 다시 실행")
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
                    self._press(P.Note.NAME_VALUE)
                    self.surface.wait_settled(0.5)
                    return self._result(action, False, "unverified", t0, after=self.status(),
                                        note="NAME/VALUE 뒤에도 LCD 2행에 dB 값이 안 보임 (되돌려 눌렀음)")
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
