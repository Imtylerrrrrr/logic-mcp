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
