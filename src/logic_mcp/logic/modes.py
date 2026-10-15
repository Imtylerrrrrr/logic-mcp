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
ENTER_TIMEOUT = 3.0      # 모드 버튼 단계 대기. EQ 첫 진입(Channel EQ 자동 삽입)은 `E_`가 0.5~1.0초 지속(실측 P)
TICK_QUIET_S = 0.4       # 틱 뒤 마지막 LCD 쓰기로부터 이만큼 조용해져야 오버레이를 읽는다(실측 S)
LED_TIMEOUT = 0.5
FLIP_LED_TIMEOUT = 1.0   # FLIP LED는 늦게 올 수 있다(실측 Z2). 재누름은 하지 않으므로 넉넉히 기다린다(리뷰 C1)
FADER_TIMEOUT = 0.8
FEEDBACK_TIMEOUT = 0.6
PRESS_HOLD_S = 0.03
HOLD_MENU_S = 0.4
BLINK_RETRY_S = 0.4      # 미리 선택 깜박임 반주기(≈0.75초)보다 짧게
OVERLAY_WIDTH = 21       # 오버레이가 쓰는 열 3칸
EDIT_OPEN_S = 1.5        # 미리 선택 없이 차 있는 슬롯 누름 → 편집 뷰(실측 0.5초 안)
CONFIRM_S = OVERLAY_S + 1.0   # 미리 선택 확정 누름 → 편집 뷰는 ≈2초 뒤(실측 K)
POLL_S = 0.1
_FAMILY_BUTTON = {"eq": P.Note.EQ, "plugin": P.Note.PLUGIN, "send": P.Note.SEND, "track": P.Note.TRACK}
_STEPS: dict[tuple[str, str], int] = {("pan", "track"): 1}
for _fam in ("eq", "plugin", "send"):
    _STEPS.update({("pan", f"{_fam}_mixer"): 1, ("pan", f"{_fam}_channel"): 2,
                   (f"{_fam}_mixer", f"{_fam}_channel"): 1, (f"{_fam}_channel", f"{_fam}_mixer"): 1})
_STEPS.update({("plugin_edit", "plugin_mixer"): 1, ("empty_edit", "plugin_mixer"): 1,
               ("plugin_edit", "plugin_channel"): 2, ("empty_edit", "plugin_channel"): 2})
TRACK_MENU_OUTPUT = (4, "Output")      # TRACK 홀드 메뉴 항목(실측 Z5). 6(DisplP)·7(Setup)은 뱅크 구성을 바꾸므로 금지
TRACK_MENU_VOLUME = (0, "Volume")


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
        self._cs_dirty = False        # TRACK 홀드 메뉴에서 Volume 아닌 항목을 눌렀고 아직 되돌리지 않음
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

    def settle_quiet(self) -> None:
        """마지막 LCD 쓰기 뒤 TICK_QUIET_S 조용해질 때까지(늦게 도착하는 오버레이 쓰기를 기다림)."""
        self._settle(extra=TICK_QUIET_S)

    def pause(self, seconds: float) -> None:
        self._sleep(seconds)

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

    def read_overlay_text(self, ch: int) -> str:
        """오버레이 2행(21칸) 원문. 플러그인 이름처럼 숫자가 아닌 값에 쓴다."""
        start = min(ch * S.COL_W, P.LCD_WIDTH - OVERLAY_WIDTH)
        return self.surface.state.lcd[1][start:start + OVERLAY_WIDTH].strip()

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
            # EQ는 down에 `E_`(메뉴)가 먼저 뜨고 up 뒤에 뷰가 온다(실측 A). 메뉴·과도기(unknown)는 지나쳐 기다린다.
            if not self.surface.wait_for(lambda s: s.view.kind != before and not s.view.kind.endswith("_menu")
                                         and s.view.kind != "unknown", ENTER_TIMEOUT):
                raise ModeError("enter", kind, f"{before}에서 버튼 반응 없음({self.view.kind})")
        # 2자리 표시와 LCD가 따로 도착하는 과도기를 지나 목표 뷰가 되기를 잠깐 더 기다린다.
        if not self.surface.wait_for(lambda s: s.view.kind == kind, MODE_TIMEOUT):
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

    def probe_pages(self) -> int:
        """편집 뷰 NAME 모드 1페이지에서 페이지 수. 헤더에 `Page n/N`이 보이면 N. 긴 헤더는 1페이지에서 잘리므로(실측 L)
        Cursor ▶로 2페이지에 가서 `Page 2/N`을 읽고 ◀로 돌아온다. ▶에 LCD가 안 바뀌면 1페이지."""
        if self.view.page:
            return self.view.page[1]
        lcd_before = self.surface.state.lcd
        self._mark()
        self._press(P.Note.CURSOR_RIGHT)
        if not self.surface.wait_for(lambda s: s.lcd != lcd_before, MODE_TIMEOUT):
            self._settle()
            return 1
        self.settle_smart()
        if not self.view.page:
            raise ModeError("pages", "2페이지 헤더 `Page 2/N`", self.surface.state.lcd[0].strip()[:40] or "빈 헤더")
        pages = self.view.page[1]
        self._page_hint = self.view.page[0]
        self.page_to(1)
        return pages

    def wait_view(self, pred: Callable[[S.View], bool], timeout: float) -> bool:
        """느린 뷰 전환(확정 누름 ≈2초)을 sleep 단위로 기다린다. 맞으면 조각 쓰기가 멈출 때까지 정착."""
        end = self.surface.clock() + timeout
        while not pred(self.view):
            if self.surface.clock() >= end:
                return False
            self._sleep(POLL_S)
        self._settle()
        return True

    def press_vpot_until(self, ch: int, pred: Callable[[S.View], bool], timeout: float) -> bool:
        """V-Pot 누름 뒤 뷰 조건을 timeout까지 기다린다(편집 뷰 열기·확정)."""
        self._mark()
        self._press(P.Note.VPOT_PUSH + ch)
        return self.wait_view(pred, timeout)

    def tick(self, ch: int, steps: int) -> bool:
        """V-Pot 틱(63씩 분할). LCD가 반응하면 True. 직전 동작의 늦은 오버레이 쓰기가 반응으로 오인되거나
        목표 틱의 오버레이를 읽기 전에 끝나지 않도록, 마지막 LCD 쓰기 뒤 TICK_QUIET_S 조용해질 때까지 기다린다(실측 S)."""
        if steps == 0:
            return True
        self._mark()
        for msg in P.vpot_turn_messages(ch, steps):
            self.surface.send(msg)
        ok = self._wait_change()
        self.settle_quiet()
        return ok

    def press_vpot(self, ch: int) -> bool:
        self._mark()
        self._press(P.Note.VPOT_PUSH + ch)
        return self._wait_change()

    def shift_press_vpot(self, ch: int) -> bool:
        """SHIFT를 누른 채 V-Pot 누름(플러그인 바이패스 토글, Apple 문서·라이브 체크 대상)."""
        self._mark()
        self.surface.send(P.button_down(P.Note.SHIFT))
        self._press(P.Note.VPOT_PUSH + ch)
        self.surface.send(P.button_up(P.Note.SHIFT))
        return self._wait_change()

    def fader(self, ch: int, raw: int) -> int | None:
        """Flip 상태에서 페이더로 절대값. 에코된 raw, 반응이 없으면 None. raw 0은 보내지 않는다.
        Flip이 꺼진 채 보내면 페이더가 트랙 볼륨을 움직이므로, 메시지를 보내기 직전마다(재전송 포함) Flip을 확인한다."""
        raw = max(1, min(P.MAX_FADER, raw))
        before = self.surface.state.strips[ch].fader_raw
        ok = False
        for _ in range(2):                    # 에코도 LCD도 없으면 이동이 통째로 무시된 것: 한 번 더 보낸다(실측 Z1)
            if not self.surface.state.assignment.flip:
                raise ModeError("fader", "flip on", "Flip 꺼짐 — 볼륨을 움직일 수 있어 보내지 않음")
            self._mark()
            for msg in P.fader_move(ch, raw):
                self.surface.send(msg)
            ok = self.surface.wait_for(lambda s: s.strips[ch].fader_raw != before, FADER_TIMEOUT)
            # 에코 뒤에 LCD 값 쓰기가 늦게 올 수 있다(실측 X): 에코만 보고 끝내면 이동 전 값을 읽는다. 값이 안 바뀌면 안 올 수도 있다.
            shown = self.surface.wait_for(lambda s: s.connection.last_display_change >= self._since, FEEDBACK_TIMEOUT)
            if ok or shown or raw == before:  # 이미 그 위치면 에코가 올 이유가 없다: 재전송하지 않는다
                break
        self._settle()
        return self.surface.state.strips[ch].fader_raw if ok else None

    def flip(self, on: bool) -> None:
        """FLIP 한 번 누르고 LED를 FLIP_LED_TIMEOUT 기다린다. 재누름 없음: 늦은 LED와 겹치면 Flip이 꺼진 채 페이더가 볼륨을 움직인다(리뷰 C1)."""
        if self.surface.state.assignment.flip == on:
            return
        self._mark()
        self._press(P.Note.FLIP)
        if not self.surface.wait_for(lambda s: s.assignment.flip == on, FLIP_LED_TIMEOUT):
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

    def track_param(self, index: int, label: str) -> list[str]:
        """PAN에서 TRACK 버튼을 누른 채 홀드 메뉴(`C_`, 2행 라벨 8개)의 index 항목을 고른다(실측 Z5 경로, 리뷰 M7).
        2행 index 열 라벨이 label과 다르면 누르지 않고 버튼을 놓은 뒤 ModeError(항목 6 DisplP·7 Setup은 뱅크 구성을 바꾼다).
        놓은 뒤 CS 뷰(`track`)가 아니거나 고른 항목이 2행에 보이지 않으면 ModeError(리뷰 C1: 누름 드롭 시 Volume `+0.0dB`가
        남아 출력·Master 판별이 거짓으로 통과함). 성공하면 CS 뷰 2행(스트립별 값 8개, strip)을 돌려준다."""
        if self.view.kind != "pan":
            self.leave(keep_select=True)
        self._mark()
        self.surface.send(P.button_down(P.Note.TRACK))
        self._sleep(HOLD_MENU_S)
        shown = self.view.columns[index][1].strip() if self.view.kind == "track_menu" else ""
        if shown != label:
            self.surface.send(P.button_up(P.Note.TRACK))
            self._wait_change()
            raise ModeError("track_menu", f"항목 {index} = {label!r}", f"{self.view.kind} {shown!r}")
        if index != TRACK_MENU_VOLUME[0]:
            self._cs_dirty = True                 # 그룹 설정 "채널 스트립 파라미터"가 바뀌었을 수 있다 → Volume 복원 필요
        self._press(P.Note.VPOT_PUSH + index)
        self._sleep(0.1)
        self.surface.send(P.button_up(P.Note.TRACK))
        self._wait_change()
        self.settle_overlay()
        texts = [c[1].strip() for c in self.view.columns]
        if self.view.kind != "track":
            raise ModeError("track_param", f"{label} 선택 뒤 CS 뷰", self.view.kind)
        has_db = any(parse_value(t).unit == "dB" for t in texts)
        if label == TRACK_MENU_OUTPUT[1] and has_db:
            raise ModeError("track_param", "Output 열(dB 값 없음)",
                            f"2행에 dB 값 {texts!r} — Output 누름이 무시된 듯(스트립 종류 판별 실패)")
        if label == TRACK_MENU_VOLUME[1]:
            if not has_db:
                raise ModeError("track_param", "Volume 열(dB 값)", f"2행 {texts!r} — Volume 복원 확인 안 됨")
            self._cs_dirty = False
        return texts

    def read_strip_outputs(self) -> list[str]:
        """스트립 8개의 Output 텍스트(`St Out` 등). 출력·Master 스트립은 빈칸(실측 Z5).
        PAN에서 홀드 → Output → 읽기 → PAN → 다시 PAN에서 홀드 → Volume → PAN. Output 판별·Volume 복원 중 하나라도
        확인되지 않으면 ModeError를 던진다(호출자는 unverified로 보고, 리뷰 C1)."""
        self._cs_dirty = False
        try:
            outs = self.track_param(*TRACK_MENU_OUTPUT)
            self.leave(keep_select=True)
            return outs
        finally:
            try:
                if self._cs_dirty:
                    self.leave(keep_select=True)
                    self.track_param(*TRACK_MENU_VOLUME)
            finally:
                self.leave(keep_select=True)

    def leave(self, keep_select: bool = False) -> None:
        """NAME 모드 복원 → Flip 해제 → PAN → (선택 복원). 모든 명령의 finally에서 호출.
        한 단계가 실패해도 나머지를 모두 시도하고, 실패는 모아 마지막에 ModeError 하나로 던진다(리뷰 I2)."""
        errors: list[str] = []
        steps: list[tuple[str, Callable[[], None]]] = [("name", self._leave_name), ("flip off", self._leave_flip),
                                                       ("pan", self._leave_pan)]
        for label, step in steps:
            try:
                step()
            except ModeError as e:
                errors.append(f"{label}: {e}")
        if not keep_select and self._focused:
            prev, self._focused, self._restore_select = self._restore_select, False, None   # 성공·실패와 무관하게 초기화(리뷰 m7)
            strips = self.surface.state.strips
            if prev is not None and strips[prev].number is not None and not strips[prev].select:
                self._mark()
                self._press(P.Note.SELECT + prev)
                self.surface.wait_for(lambda s: s.strips[prev].select, LED_TIMEOUT)
                self._settle()
        if errors:
            raise ModeError("leave", "pan/flip off/name", "; ".join(errors))

    def _leave_name(self) -> None:
        if self._name_mode:
            self.toggle_name_value()

    def _leave_flip(self) -> None:
        if self.surface.state.assignment.flip:
            self.flip(False)

    def _leave_pan(self) -> None:
        if self.view.kind != "pan":
            for _ in range(2):
                self._mark()
                self._press(P.Note.PAN)
                if self.surface.wait_for(lambda s: s.view.kind == "pan", MODE_TIMEOUT):
                    break
            else:
                raise ModeError("leave", "pan", self.view.kind)
            self.settle_overlay()

    def leave_safely(self) -> None:
        try:
            self.leave()
            self.last_leave_error = ""
        except ModeError as e:
            self.last_leave_error = str(e)
