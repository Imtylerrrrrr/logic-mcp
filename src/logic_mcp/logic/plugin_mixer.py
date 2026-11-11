"""Aux 스트립 슬롯 1 경로: Plug-in Mixer 뷰(P1)에서 V-Pot n = 스트립 n의 슬롯 1(실전 F2).
Aux는 Plug-in Channel 뷰가 직전 트랙 슬롯을 보여 주므로 슬롯 1만 이 뷰로 읽고 넣고 뺀다. PluginCommands가 만든다."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .modes import CONFIRM_S, EDIT_OPEN_S, ModeError
from .plugin import EMPTY_TEXTS, MAX_SLOT
from .plugins.scan import rewind_to_empty, seek_by_name

if TYPE_CHECKING:
    from .commands import ToolResult
    from .plugin import PluginCommands


class AuxMixer:
    def __init__(self, pc: "PluginCommands") -> None:
        self.pc = pc                                         # b·d·cache는 부를 때마다 pc에서 읽는다

    def slot1(self) -> list[str]:
        """Plug-in Mixer 뷰 2행 8열(V-Pot n = 스트립 n의 슬롯 1). 뷰가 다른 슬롯(P<n>)이면 슬롯 1로 돌린 뒤 읽는다
        (Mixer 뷰는 마지막 편집 슬롯을 따른다, 실측 O·실기 10/27). 돌리지 못하면 ModeError."""
        d = self.pc.d
        d.enter("plugin_mixer")
        if d.view.index not in (None, 1):
            self.steer_to_slot1(d.view.index)
        return [d.view.columns[i][1].strip() for i in range(MAX_SLOT)]

    def steer_to_slot1(self, shown: int) -> None:
        """트랙 스트립(선택된 것 먼저)의 PL에서 슬롯 1이 차 있으면 V-Pot 1을 틱 없이 눌러 편집 뷰를 슬롯 1로 열고(실측 F(2):
        값 보존, 미리 선택 없음 → 교체 없음), PLUGIN으로 P1 Mixer 뷰에 간다. 빈 슬롯 누름은 무반응이라(실측 F) 차 있는 트랙만 쓴다.
        틱은 절대 보내지 않는다(틱 = 미리 선택 → 누르면 교체)."""
        b, d = self.pc.b, self.pc.d
        d.leave(keep_select=True)                            # 남은 미리 선택을 모드 전환으로 취소한 뒤 누른다
        state = b.surface.state
        numbered = [ch for ch, s in enumerate(state.strips) if s.number is not None]
        numbered.sort(key=lambda ch: not state.strips[ch].select)
        for ch in numbered:
            if b.strips.kind(d, b.surface.state, ch) != "track":
                continue
            b._channel(ch, "plugin_channel")
            if self.pc._slot_text(1) in EMPTY_TEXTS:
                continue
            if not d.press_vpot_until(0, lambda v: v.kind in ("plugin_edit", "empty_edit") and v.index == 1, EDIT_OPEN_S):
                raise ModeError("mixer", "슬롯 1 편집 뷰(Mixer 뷰를 슬롯 1로)", f"{d.view.kind} {d.view.index or ''}".strip())
            d.settle_smart()
            d.enter("plugin_mixer")
            if d.view.index not in (None, 1):
                raise ModeError("mixer", "Plug-in Mixer 슬롯 1", f"슬롯 1 편집 뒤에도 Mixer 뷰 슬롯이 {d.view.index}")
            return
        raise ModeError("mixer", "Plug-in Mixer 슬롯 1", f"Mixer 뷰 슬롯이 {shown}, 슬롯 1이 찬 트랙 스트립이 없어 슬롯 1로 돌리지 못함")

    def confirm(self, ch: int, before: list[str]) -> tuple[list[str], list[int]]:
        """미리 선택한 V-Pot ch를 눌러 확정하고 Mixer 뷰를 다시 읽는다. 확정 뒤 편집 뷰는 선택 트랙 기준이라(실전 F2)
        헤더로 검증하지 않는다. (다시 읽은 8열, 바뀐 다른 열 번호)."""
        d = self.pc.d
        d.press_vpot_until(ch, lambda w: w.kind in ("plugin_edit", "empty_edit"), CONFIRM_S)
        d.settle_smart()
        if d.view.kind == "plugin_mixer":
            d.leave(keep_select=True)       # 확정이 안 먹었으면 남은 미리 선택의 깜박임을 열 텍스트로 읽지 않도록 모드 전환으로 취소
        after = self.slot1()
        return after, [i + 1 for i in range(MAX_SLOT) if i != ch and after[i] != before[i]]

    def insert(self, action: str, t0: int, target: dict, ch: int, want: str, prefix: bool) -> "ToolResult":
        """Aux 스트립 슬롯 1 삽입: Mixer 뷰 V-Pot ch로 이름 탐색 → 확정 → 열 ch만 바뀌었는지 확인."""
        b, d = self.pc.b, self.pc.d
        before = self.slot1()
        current = before[ch]
        if current not in EMPTY_TEXTS:                       # replace도 막는다: 교체 확정은 Mixer 뷰에서 검증 경로가 없다
            return b._result(action, False, "skipped", t0, target=target,
                             note=f"슬롯 1에 {current!r}가 있음. Aux 스트립은 교체를 지원하지 않음: remove 뒤 insert")
        found, ticks, name = seek_by_name(d, ch, want, prefix)
        if not found:                                        # 누르지 않는다: finally의 leave가 미리 선택을 취소
            return b._result(action, False, "unverified", t0, target=target,
                             note=f"이름 탐색 {ticks}틱 뒤에도 {want!r} 못 찾음(마지막 {name!r}). 설치 목록이 다른 듯. `logic_plugin scan` 권장")
        after, moved = self.confirm(ch, before)
        ok = after[ch] not in EMPTY_TEXTS and not moved
        if ok:
            self.pc.cache.learn_abbrev(after[ch].lstrip("*"), name)
            self.pc.cache.save()
        return b._result(action, ok, "verified" if ok else "unverified", t0, target=target,
                         before={"slot": 1, "text": current},
                         after={"slot": 1, "plugin": name, "abbrev": after[ch], "replaced": None, "path": "mixer"},
                         note=f"name_scan:{ticks}" if ok else
                         f"Mixer 뷰 확인 실패: 열 {ch + 1} {after[ch]!r}, 바뀐 다른 스트립 {moved}")

    def remove(self, action: str, t0: int, target: dict, ch: int) -> "ToolResult":
        """Aux 스트립 슬롯 1 제거: Mixer 뷰 V-Pot ch를 `--`로 되감아 확정 → 열 ch만 비었는지 확인."""
        b, d = self.pc.b, self.pc.d
        before = self.slot1()
        current = before[ch]
        if current in EMPTY_TEXTS:
            return b._result(action, True, "skipped", t0, target=target, after={"slot": 1, "text": current, "path": "mixer"},
                             note="already")
        rewind_to_empty(d, ch)                               # 오버레이 `--` 확인까지
        after, moved = self.confirm(ch, before)
        ok = after[ch] in EMPTY_TEXTS and not moved
        return b._result(action, ok, "verified" if ok else "unverified", t0, target=target,
                         before={"slot": 1, "text": current}, after={"slot": 1, "text": after[ch], "path": "mixer"},
                         note="" if ok else f"Mixer 뷰 확인 실패: 열 {ch + 1} {after[ch]!r}, 바뀐 다른 스트립 {moved}")
