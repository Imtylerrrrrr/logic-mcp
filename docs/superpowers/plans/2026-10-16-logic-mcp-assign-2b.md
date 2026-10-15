# logic-mcp 스펙 2b 구현 계획 — 출력 스트립 가드(수정 8) · 센드 · 캐시 · 캘리브레이션 · 스킬

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) 출력·Master 스트립을 대상으로 한 EQ·플러그인 명령이 엉뚱한 트랙을 바꾸는 결함(실측 Z4)을 막고, (2) Claude가 센드 1~8의 목적지·레벨·위치·뮤트를 읽고 바꾸게 하며(`logic_send`), (3) 번들 파라미터 표를 만드는 캘리브레이션 경로와 캐시 저장 규칙(리뷰 m4)을 고치고, (4) 스킬 문서를 둔다.

**Architecture:** 2a의 `ModeDriver`·`setter`·`values` 위에 (a) TRACK 모드(`C_`/`CS`) 진입과 홀드 메뉴 읽기를 드라이버에 더해 스트립 종류(실제 트랙 / 출력·마스터)를 판별하는 `StripKinds`를 두고 모든 채널 뷰 명령의 입구(`_channel`)에서 막는다. (b) 센드는 SE(센드 채널) 뷰 한 곳에서만 다루는 `SendCommands`(`logic/sends.py`)로 만든다: 열 위치로만 해석, 목적지는 1틱=1항목 + 버스 번호 모델, 레벨은 Flip 페이더(볼륨 dB 표), pos·mute는 틱. (c) `PluginCache.save`는 번들과 다른 항목만 사용자 파일에 쓴다. (d) `PluginCommands.calibrate`가 편집 뷰에서 이름·매핑·선택지를 모으고 `scripts/calibrate_plugin.py`가 `known.json`에 합친다. 테스트는 가짜 Logic(`tests/fake_assign.py`)에 TRACK 모드·센드 모델·출력 스트립을 더해 한다.

**Tech Stack:** Python ≥3.13, uv, `mcp` 2.3 (`MCPServer`), python-rtmidi, pydantic, pytest + anyio. 새 의존성 없음.

**Spec:** `docs/superpowers/specs/2026-10-15-logic-mcp-assign-design.md` §4.3·4.4·6·7·8. 실측은 `docs/mcu-protocol.md` "실기 9차 실측"(Z3~Z7)과 "센드 실측"(S1~S11). 이 계획은 아래 "스펙 보정"대로 스펙을 고쳐 읽는다(Task 9에서 스펙 파일에도 반영).

## 스펙 보정 (2026-10-16 실측 반영 — 스펙 본문과 다를 때 이 표가 우선)

| 스펙 | 보정 | 근거 |
|---|---|---|
| §4.3 "SE 뷰에서 FLIP … 안 되면 D1 뷰" | SE 뷰 Flip 페이더로 확정. D1 경로 없음. 센드 dB 표 = 볼륨 표(`fader_db.json`) 그대로 | S6 |
| §4.3 `set_dest` "목적지 목록 인덱스 차이만큼 틱" | 목록 스캔 없음. 목적지는 **버스 번호**(1~256) 또는 `--`. `--`로 되감은 뒤 `번호+2` 틱 → 오버레이 `Bus m` 읽고 `번호-m` 보정(≤4회) → 누름 | S4·S5 |
| §4.3 `set_pos` "틱 1씩 텍스트 일치까지(≤3)" | 순서 고정 Pre→Post→Post Pan: 인덱스 차이만큼 한 번에 틱, 정착 열 `Pre`/`Post`/`PosPan` 확인 | S8 |
| §4.3 `mute` | +1 = muted, -1 = active. dest 열 `*` 접두가 뮤트 표시 | S9 |
| §6.3 센드 목적지 목록 스캔 | **삭제**. 버스 외 목적지(목록 앞 `1`, `2`)는 비범위 | S4 |
| §6.1 `scripts/calibrate_plugin.py` | `PluginCommands.calibrate`(편집 뷰에서 이름·매핑·선택지 수집)를 스크립트가 호출해 `known.json`에 합침. 10종 실기 수집은 계획 밖 작업(컨트롤러가 Logic 켜진 세션에서 실행) | §6.1 |
| §8 `scripts/calibrate_send.py` | **삭제**(볼륨 표와 같음) | S6 |
| §7 안전 | 추가: **출력(Stereo Out)·Master 스트립은 채널 뷰(PL·SE·EQ)가 따라가지 않는다 → 그 스트립 대상 명령은 skipped**(`eq get`은 E1 뷰 `has_eq`만). 판별은 TRACK 모드 홀드 메뉴 `Output` 열(빈칸 = 출력·마스터) | Z4·Z5 |
| §4.4 리소스 | 추가 없음(센드 결과는 `logic_send get`의 after로만) | — |

## Global Constraints

- Python `>=3.13`, 의존성 추가 금지. 테스트는 CoreMIDI를 열지 않는다(`rtmidi`는 `RtMidiTransport.open` 안에서만 임포트).
- MCP는 `from mcp.server import MCPServer`, 툴 속성은 `input_schema`/`structured_content`(v2 이름).
- 모든 도구는 스펙 1 `ToolResult(ok, verified∈{verified,unverified,timeout,skipped}, action, target, before, after, elapsed_ms, note)`를 돌려준다. 예외를 밖으로 던지지 않는다.
- 스펙 2 명령은 **반드시** `ModeDriver.leave()`로 끝난다(finally). 끝난 뒤 뷰는 `pan`, Flip은 off.
- Flip 상태에서 페이더 raw 0을 보내지 않는다(최소 1). V-Pot 틱은 메시지당 크기 ≤63으로 나눈다(`vpot_turn_messages`).
- 오버레이 2.0초: 모드 전환·값 변경 뒤 정착 열을 읽기 전에 `settle_overlay()`를 거친다.
- 센드는 1~8만. 출력·Master 스트립(TRACK 모드 Output 열 빈칸)은 EQ 채널 뷰·PL·SE 명령 모두 skipped.
- TRACK 홀드 메뉴는 **항목 0(Volume)·4(Output)만** 누른다. 항목 6(DisplP)·7(Setup)은 뱅크 구성을 바꾸므로 절대 누르지 않는다(Z5). 누르기 전에 2행 메뉴 라벨을 확인하고, 끝나면 항목 0으로 되돌린다.
- 주석·docstring·note 문자열은 한국어(기존 코드와 같이). 커밋 메시지 한국어 + `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Logic UI 클릭·AX 자동화 금지. 프로젝트 저장 금지. 기존 MPK mini IV 컨트롤 서피스 설정 불변. "기본값 재형성" 금지.

## Review Focus

1. **출력·Master 스트립 대상 insert/eq set/set_dest가 직전 실제 트랙을 바꿈**(Z4). Task 2 `test_insert_on_output_strip_is_skipped_and_touches_nothing`, Task 4 `test_set_dest_on_output_strip_is_skipped`: 가드가 뷰 진입 전에 막고 어떤 트랙도 안 바뀐다.
2. **목적지 목록 앞 항목 수가 프로젝트마다 다르면 엉뚱한 버스에 확정**. Task 4 `test_set_dest_adjusts_when_prefix_count_differs`(접두 0개·4개)와 `test_set_dest_does_not_press_when_overlay_mismatches`.
3. **Flip이 켜진 채 레벨 설정이 실패**하면 다음 스펙 1 볼륨 명령이 센드 레벨을 움직임. Task 5 `test_set_level_mode_error_still_leaves_flip_off`.
4. **SE 뷰가 마지막 페이지를 기억**(S3)해 1페이지로 가정하면 다른 센드를 읽음. Task 4 `test_get_reads_from_remembered_page`.
5. **TRACK 홀드 메뉴 라벨 확인 없이 V-Pot을 누르면** 항목 6(DisplP)처럼 뱅크 구성을 바꿀 수 있음(Z5). Task 1 `test_track_param_refuses_when_menu_label_differs`: 라벨이 다르면 누르지 않고 ModeError.

---

## 파일 구조

| 파일 | 역할 |
|---|---|
| `src/logic_mcp/mcu/state.py` (수정) | 2자리 `C_` → `track_menu`, `CS` → `track`; `track_menu`는 이름 갱신 제외 |
| `src/logic_mcp/logic/modes.py` (수정) | `enter("track")`, `track_param(index, label)`, `read_strip_outputs()` |
| `src/logic_mcp/logic/strips.py` (신규) | `StripKinds`(번호·이름 키 캐시, `ensure(d, state, ch)`), `StripUnsupported` |
| `src/logic_mcp/logic/assign.py` (수정) | `_channel`·EQ 입구 가드, `list` 뱅크 `unsupported`, `calibrate()` |
| `src/logic_mcp/logic/sends.py` (신규) | 열 해석 헬퍼 + `SendCommands`(get/set_dest/remove/set_level/set_pos/mute) |
| `src/logic_mcp/logic/commands.py` (수정) | `Commands.strips`, `Commands.send` |
| `src/logic_mcp/logic/plugins/cache.py` (수정) | 번들과 다른 항목만 저장(m4), `merge_bundled()` |
| `src/logic_mcp/server/tools.py` (수정) | `logic_send` |
| `scripts/calibrate_plugin.py` (신규), `scripts/live_check2.py` (수정) | 캘리브레이션·실기 검증 |
| `skills/logic-plugins/SKILL.md` (신규), `README.md`, `docs/progress.md`, 스펙 (수정) | 문서 |
| `tests/fake_assign.py` (수정) | 트랙 종류(`kind`), TRACK 모드·홀드 메뉴, 센드 모델(S_·S1·SE·미리 선택·Flip·틱) |
| `tests/test_state.py`, `test_modes.py`, `test_assign_plugin.py`, `test_assign_eq.py`, `test_plugins.py`, `test_server.py` (수정), `tests/test_strips.py`, `tests/test_sends.py`, `tests/test_assign_send.py`, `tests/test_calibrate.py` (신규) | |

---

### Task 1: TRACK 모드 뷰·드라이버·가짜 Logic

**Files:**
- Modify: `src/logic_mcp/mcu/state.py:classify_view`, `_NO_NAME_VIEWS`
- Modify: `src/logic_mcp/logic/modes.py` (`_FAMILY_BUTTON`, `_STEPS`, `track_param`, `read_strip_outputs`)
- Modify: `tests/fake_assign.py` (`Track.kind`, TRACK 버튼·홀드 메뉴·CS 뷰)
- Test: `tests/test_state.py`, `tests/test_modes.py`

**Interfaces:**
- Consumes: `ModeDriver.hold_menu` 패턴, `P.Note.TRACK=0x28`.
- Produces: `View.kind in {"track", "track_menu"}`; `ModeDriver.track_param(index: int, label: str) -> list[str]`(8열 2행 텍스트, strip 됨), `ModeDriver.read_strip_outputs() -> list[str]`(Output 열 8개, 끝나면 Volume으로 되돌리고 PAN으로 나감); 가짜 `Track(kind="track"|"output"|"master")`, `Track.follows`(bool), `FakeLogic.cs_param`, `FakeLogic.menu_labels`(기본 `TRACK_MENU`).

- [ ] **Step 1: 실패하는 테스트 — 뷰 판정**

`tests/test_state.py`의 `test_view_send_kinds_and_menus` 바로 뒤에 추가:

```python
def test_view_track_menu_and_channel_strip_codes():                 # 실측 Z5
    st = ready_pan()
    st = apply(st, digit_evs("C_") + [lcd_ev(0, " " * 56 + "Volume Pan    TrkFmt Input  Output Auto   DisplP Setup  ")])
    assert (st.view.kind, st.view.index) == ("track_menu", None)
    assert st.strips[0].number == 15                                  # 홀드 메뉴 1행(빈칸)은 채널명이 아님
    st = apply(st, digit_evs("CS") + [lcd_ev(0, ROW_NAMES + "+0.0dB +0.0dB +0.0dB +0.0dB                             ")])
    assert (st.view.kind, st.view.index) == ("track", None)
    assert st.strips[0].value_text == "+0.0dB"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_state.py::test_view_track_menu_and_channel_strip_codes -v`
Expected: FAIL (`track_menu` 대신 `track` 또는 `unknown`).

- [ ] **Step 3: state.py 수정**

`classify_view`에서 `if d == "PL":` 앞에 추가:

```python
    if d == "C_":
        return "track_menu", None     # TRACK down: 2행이 홀드 메뉴(실측 Z5)
    if d == "CS":
        return "track", None          # Channel Strip 뷰: 1행 이름, 2행 스트립별 값(실측 Z5)
```

`_NO_NAME_VIEWS`에 `"track_menu"`를 더한다:

```python
_NO_NAME_VIEWS = frozenset({"eq_channel", "eq_menu", "send_channel", "send_menu", "plugin_channel",
                            "plugin_edit", "empty_edit", "midi_fx", "track_menu"})          # 1행이 채널명이 아닌 뷰
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_state.py -v`
Expected: 전부 PASS.

- [ ] **Step 5: 실패하는 테스트 — 드라이버·가짜**

`tests/test_modes.py` 끝에 추가:

```python
def test_enter_track_reads_outputs_and_restores_volume():               # 실측 Z5
    from tests.fake_assign import Track
    tracks = [Track(1, "1"), Track(2, "DeCl"), Track(3, "StOu", kind="output"), Track(6, "Mast", kind="master")]
    surface, fake, logic = make_assign_logic(tracks)
    d = ModeDriver(surface, sleep=logic.sleep)
    outs = d.read_strip_outputs()
    assert outs == ["St Out", "St Out", "", "", "", "", "", ""]
    assert logic.cs_param == 0 and surface.state.view.kind == "pan" and logic.view == "pan"
    pushes = [m for m in fake.sent if m[0] == 0x90 and P.Note.VPOT_PUSH <= m[1] < P.Note.VPOT_PUSH + 8 and m[2]]
    assert [m[1] - P.Note.VPOT_PUSH for m in pushes] == [4, 0]           # Output 선택 → Volume 복원, 그 밖은 누르지 않음


def test_track_param_refuses_when_menu_label_differs():                 # Review Focus 5
    from tests.fake_assign import Track
    surface, fake, logic = make_assign_logic([Track(1, "1"), Track(2, "DeCl")])
    logic.menu_labels = ["Volume", "Pan", "TrkFmt", "Input", "DisplP", "Auto", "Output", "Setup"]   # 다른 Logic 버전 흉내
    d = ModeDriver(surface, sleep=logic.sleep)
    with pytest.raises(ModeError):
        d.read_strip_outputs()
    pushes = [m for m in fake.sent if m[0] == 0x90 and P.Note.VPOT_PUSH <= m[1] < P.Note.VPOT_PUSH + 8 and m[2]]
    assert pushes == [] and logic.cs_param == 0
    assert not logic.track_held                                          # 버튼을 놓고 나온다
    d.leave_safely()
    assert surface.state.view.kind == "pan"
```

- [ ] **Step 6: 실패 확인**

Run: `uv run pytest tests/test_modes.py -k "track" -v`
Expected: FAIL (`read_strip_outputs` 없음 / `Track()`에 `kind` 없음).

- [ ] **Step 7: modes.py 수정**

상수·전환표를 바꾼다:

```python
_FAMILY_BUTTON = {"eq": P.Note.EQ, "plugin": P.Note.PLUGIN, "send": P.Note.SEND, "track": P.Note.TRACK}
_STEPS: dict[tuple[str, str], int] = {("pan", "track"): 1}
for _fam in ("eq", "plugin", "send"):
    _STEPS.update({("pan", f"{_fam}_mixer"): 1, ("pan", f"{_fam}_channel"): 2,
                   (f"{_fam}_mixer", f"{_fam}_channel"): 1, (f"{_fam}_channel", f"{_fam}_mixer"): 1})
_STEPS.update({("plugin_edit", "plugin_mixer"): 1, ("empty_edit", "plugin_mixer"): 1,
               ("plugin_edit", "plugin_channel"): 2, ("empty_edit", "plugin_channel"): 2})
TRACK_MENU_OUTPUT = (4, "Output")      # TRACK 홀드 메뉴 항목(실측 Z5). 6(DisplP)·7(Setup)은 뱅크 구성을 바꾸므로 금지
TRACK_MENU_VOLUME = (0, "Volume")
```

`enter()`의 `fam not in _FAMILY_BUTTON` 검사는 그대로 둔다(`"track".split("_")[0] == "track"`). `hold_menu` 아래에 추가:

```python
    def track_param(self, index: int, label: str) -> list[str]:
        """TRACK 버튼을 누른 채 홀드 메뉴(`C_`, 2행 라벨 8개)에서 index 항목을 고른다. 2행 index 열 라벨이 label과
        다르면 누르지 않고 버튼을 놓은 뒤 ModeError(항목 6 DisplP·7 Setup은 뱅크 구성을 바꾼다, 실측 Z5).
        고른 뒤 CS 뷰 2행(스트립별 값 8개, strip)을 돌려준다."""
        self.enter("track")
        self._mark()
        self.surface.send(P.button_down(P.Note.TRACK))
        self._sleep(HOLD_MENU_S)
        shown = self.view.columns[index][1].strip() if self.view.kind == "track_menu" else ""
        if shown != label:
            self.surface.send(P.button_up(P.Note.TRACK))
            self._wait_change()
            raise ModeError("track_menu", f"항목 {index} = {label!r}", f"{self.view.kind} {shown!r}")
        self._press(P.Note.VPOT_PUSH + index)
        self._sleep(0.1)
        self.surface.send(P.button_up(P.Note.TRACK))
        self._wait_change()
        self.settle_overlay()
        return [c[1].strip() for c in self.view.columns]

    def read_strip_outputs(self) -> list[str]:
        """스트립 8개의 Output 텍스트(`St Out` 등). 출력·Master 스트립은 빈칸(실측 Z5). Output을 골랐으면 Volume으로 되돌리고,
        어느 경우든 PAN으로 나간다."""
        changed = False
        try:
            outs = self.track_param(*TRACK_MENU_OUTPUT)
            changed = True
            return outs
        finally:
            try:
                if changed:
                    self.track_param(*TRACK_MENU_VOLUME)
            finally:
                self.leave(keep_select=True)
```

- [ ] **Step 8: fake_assign.py 수정 — 트랙 종류와 TRACK 모드**

`Track`에 필드와 프로퍼티를 더한다(`eq_page: int = 1` 뒤):

```python
    kind: str = "track"                                           # track | output | master (실측 Z4: 출력·Master는 채널 뷰가 안 따라감)

    @property
    def follows(self) -> bool:
        return self.kind == "track"
```

모듈 상수 `ABBREV` 뒤에:

```python
TRACK_MENU = ["Volume", "Pan", "TrkFmt", "Input", "Output", "Auto", "DisplP", "Setup"]   # TRACK 홀드 메뉴(실측 Z5)
```

`FakeLogic.__init__`에 추가:

```python
        self.cs_param = 0                              # TRACK 모드가 보여 주는 채널 스트립 파라미터(TRACK_MENU 인덱스)
        self.menu_labels = list(TRACK_MENU)
        self.track_held = False                        # TRACK 버튼 down 중: 2자리 `C_` + 2행 메뉴(실측 Z5)
```

`_rows()`의 `if self.view == "pan":` 앞에 추가:

```python
        if self.view == "track_menu":
            return " " * 56, "".join(col(x) for x in self.menu_labels).ljust(56), "C_"
        if self.view == "track":
            cells = []
            for tr in self.tracks[:8]:
                if self.cs_param == 0:
                    cells.append(col("+0.0dB"))
                elif self.cs_param == 1:
                    cells.append(col("" if tr.kind == "master" else "0"))
                elif self.cs_param == 4:
                    cells.append(col("St Out" if tr.follows else ""))          # 출력·Master는 빈칸(실측 Z5)
                else:
                    cells.append(col(""))
            return self._names_row(), "".join(cells).ljust(56), "CS"
```

`replies()`의 `elif note == P.Note.EQ:` 분기 앞에 TRACK 분기를 넣는다:

```python
            elif note == P.Note.TRACK:                           # 실측 Z5: down → `C_` 메뉴, up 뒤 CS 뷰
                self.track_held = on
                if on:
                    self.view = "track_menu"
                    self.redraw()
                else:
                    self.deferred.append(lambda: self._button(P.Note.TRACK))
```

`_button()`에 TRACK 처리와 홀드 중 V-Pot 누름을 더한다. `elif note == N.PAN:` 앞에:

```python
        elif note == N.TRACK:
            self._set_mode("track", N.TRACK)
            self.redraw(mode_overlay="Channel Strip parameter:")
```

그리고 `elif N.VPOT_PUSH <= note < N.VPOT_PUSH + 8:` 분기를 다음으로 바꾼다:

```python
        elif N.VPOT_PUSH <= note < N.VPOT_PUSH + 8:
            if self.track_held and self.view == "track_menu":
                self.cs_param = note - N.VPOT_PUSH               # 홀드 메뉴 선택. 6(DisplP)·7(Setup)의 부작용은 흉내 내지 않음
                return
            self._push(note - N.VPOT_PUSH)
```

`_set_mode`는 `self.view`를 바꾸므로 TRACK up의 `_button(TRACK)`이 `track_menu` → `track`으로 간다. `_vpot`·`_push`·`_fader`는 `track`/`track_menu` 뷰에서 아무것도 하지 않는다(`_column_param`이 None을 돌려줌 → 기존 코드가 return).

- [ ] **Step 9: 통과 확인**

Run: `uv run pytest tests/test_modes.py tests/test_state.py -v`
Expected: 전부 PASS(기존 테스트 포함).

- [ ] **Step 10: 커밋**

```bash
git add src/logic_mcp/mcu/state.py src/logic_mcp/logic/modes.py tests/fake_assign.py tests/test_state.py tests/test_modes.py
git commit -m "feat(modes): TRACK 모드(C_/CS)·홀드 메뉴 Output 읽기, 가짜 Logic 트랙 종류 (실측 Z5)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: 수정 8 — 출력·Master 스트립 판별과 가드 (`logic/strips.py`)

**Files:**
- Create: `src/logic_mcp/logic/strips.py`
- Modify: `src/logic_mcp/logic/commands.py` (`Commands.strips`), `src/logic_mcp/logic/assign.py` (`_channel`, 예외 처리, `list`, `EqCommands.get/set`)
- Test: `tests/test_strips.py` (신규), `tests/test_assign_plugin.py`, `tests/test_assign_eq.py`

**Interfaces:**
- Consumes: Task 1 `ModeDriver.read_strip_outputs()`, 가짜 `Track(kind=...)`.
- Produces: `StripKinds.follows(d, state, ch) -> bool`, `StripKinds.ensure(d, state, ch)`(안 따르면 `StripUnsupported` — `.note` 보유), `Commands.strips: StripKinds`; `plugin list` 뱅크 결과 `after={"tracks": {...}, "unsupported": [번호…]}`(미지원 트랙은 `tracks[num] = None`); 미지원 스트립 대상 플러그인 명령·`eq set`은 `skipped`, `eq get`은 `{"has_eq": bool, "bands": {}}` + note.

- [ ] **Step 1: 실패하는 테스트 — StripKinds**

`tests/test_strips.py`:

```python
import pytest

from logic_mcp.logic.modes import ModeDriver
from logic_mcp.logic.strips import StripKinds, StripUnsupported
from tests.fake_assign import Track, make_assign_logic


def test_strip_kinds_fills_cache_for_all_named_strips_once():
    surface, fake, logic = make_assign_logic([Track(1, "1"), Track(3, "StOu", kind="output"), Track(6, "Mast", kind="master")])
    d = ModeDriver(surface, sleep=logic.sleep)
    kinds = StripKinds()
    assert kinds.follows(d, surface.state, 0) is True
    assert kinds.cache == {(1, "1"): True, (3, "StOu"): False, (6, "Mast"): False}
    with pytest.raises(StripUnsupported) as e:
        kinds.ensure(d, surface.state, 1)
    assert "번호 3" in e.value.note and "출력" in e.value.note
    assert kinds.follows(d, surface.state, 5) is True          # 빈 스트립(번호·이름 없음)은 막지 않는다
    assert surface.state.view.kind == "pan" and logic.cs_param == 0
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_strips.py -v`
Expected: FAIL (`logic_mcp.logic.strips` 없음).

- [ ] **Step 3: strips.py 작성**

```python
"""스트립 종류 판별. 출력(Stereo Out)·Master 채널 스트립은 PL·SE·EQ 채널 뷰가 따라가지 않아(실측 Z4) 그 스트립을 대상으로
한 명령이 직전 실제 트랙을 바꾼다. TRACK 모드 홀드 메뉴 Output 열이 빈칸인 스트립을 미지원으로 본다(실측 Z5).
(번호, 이름)별로 캐시해 뱅크당 한 번만 읽는다(번호가 밀리거나 이름이 바뀌면 자연히 다시 읽는다)."""
from __future__ import annotations

from ..mcu import state as S
from .modes import ModeDriver


class StripUnsupported(Exception):
    def __init__(self, ch: int, number: int | None, name: str) -> None:
        self.note = (f"스트립 {ch + 1}(번호 {number}, {name!r})은 출력·Master 채널 스트립이라 채널 뷰(PL·SE·EQ)가 "
                     "따라가지 않음(실측 Z4). 지원하지 않음")
        super().__init__(self.note)


class StripKinds:
    def __init__(self) -> None:
        self.cache: dict[tuple[int | None, str], bool] = {}     # (번호, 이름) → 채널 뷰가 따라가는가

    def follows(self, d: ModeDriver, state: S.SurfaceState, ch: int) -> bool:
        s = state.strips[ch]
        if not s.name and s.number is None:
            return True                                           # 빈 스트립: 판별할 것이 없다
        key = (s.number, s.name)
        if key not in self.cache:
            outs = d.read_strip_outputs()                         # TRACK 모드 Output 열 8개, 끝나면 PAN
            for i, st in enumerate(d.surface.state.strips):
                if st.name or st.number is not None:
                    self.cache[(st.number, st.name)] = bool(outs[i])
        return self.cache.get(key, True)

    def ensure(self, d: ModeDriver, state: S.SurfaceState, ch: int) -> None:
        if not self.follows(d, state, ch):
            s = state.strips[ch]
            raise StripUnsupported(ch, s.number, s.name)
```

`commands.py`의 `Commands.__init__`에서 `self.modes = ModeDriver(surface, sleep)` 다음 줄에:

```python
        from .strips import StripKinds
        self.strips = StripKinds()
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_strips.py -v`
Expected: PASS.

- [ ] **Step 5: 실패하는 테스트 — 명령 가드**

`tests/test_assign_plugin.py`의 `make`를 트랙 목록을 받도록 바꾸고 테스트를 더한다:

```python
from tests.fake_assign import PLUGIN_LIST, Param, Track, make_assign_logic


def make(tmp_path, tracks=None):
    surface, fake, logic = make_assign_logic(tracks)
    cache = PluginCache("fake", list(PLUGIN_LIST), [], {}, {}, None, tmp_path / "plugins-fake.json")
    cmds = Commands(surface, FaderTable.load(), sleep=logic.sleep, logic_running=lambda: True, plugin_cache=cache)
    return cmds, surface, fake, logic, cache


def out_tracks():
    return [Track(1, "1"), Track(2, "DeCl"), Track(3, "StOu", kind="output"), Track(6, "Mast", kind="master")]


def track_presses(msgs: list[bytes]) -> int:
    return sum(1 for m in msgs if m[0] == 0x90 and m[1] == P.Note.TRACK and m[2])


def test_insert_on_output_strip_is_skipped_and_touches_nothing(tmp_path):      # Review Focus 1, 실측 Z4
    cmds, surface, fake, logic, cache = make(tmp_path, out_tracks())
    logic.tracks[1].insert(1, "Channel EQ")
    r = cmds.plugin.insert(strip=3, number=None, slot=1, plugin="Compressor")
    assert r.verified == "skipped" and "출력" in r.note and "번호 3" in r.note
    assert [t.inserts[1] for t in logic.tracks] == [None, "Channel EQ", None, None]
    assert logic.view == "pan" and surface.state.view.kind == "pan" and not logic.pre and logic.cs_param == 0
    for name, fn in (("params", lambda: cmds.plugin.params(None, 6, 1)), ("remove", lambda: cmds.plugin.remove(None, 6, 1)),
                     ("bypass", lambda: cmds.plugin.bypass(None, 6, 1, True)), ("list", lambda: cmds.plugin.list(None, 6))):
        r = fn()
        assert r.verified == "skipped" and "출력" in r.note, name


def test_list_bank_marks_output_and_master_unsupported_and_caches_kinds(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path, out_tracks())
    logic.tracks[1].insert(1, "Channel EQ")
    r = cmds.plugin.list(None, None)
    assert r.verified == "verified"
    t = r.after["tracks"]
    assert t["1"]["1"] is None and t["2"]["1"] == {"text": "Cha EQ", "name": "Channel EQ"}
    assert t["3"] is None and t["6"] is None and r.after["unsupported"] == [3, 6]
    assert cmds.plugin.inventory["3"] is None
    n = track_presses(fake.sent)
    assert n >= 1
    r2 = cmds.plugin.list(None, None)
    assert r2.after["unsupported"] == [3, 6] and track_presses(fake.sent) == n     # (번호, 이름) 캐시: TRACK 모드 재진입 없음
    assert surface.state.view.kind == "pan" and logic.selected == 0


def test_strip_kinds_cache_invalidates_when_name_changes(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path, out_tracks())
    cmds.plugin.list(None, None)
    n = track_presses(fake.sent)
    logic.tracks[2] = Track(3, "Aux1", kind="track")             # 같은 번호에 다른 스트립(버스 센드가 Aux를 만들어 번호가 밀린 경우)
    logic.redraw()
    r = cmds.plugin.list(None, None)
    assert r.after["unsupported"] == [6] and r.after["tracks"]["3"] == {str(i): None for i in range(1, 9)}
    assert track_presses(fake.sent) > n
```

`tests/test_assign_eq.py` 끝에:

```python
def test_eq_get_on_output_strip_reports_has_eq_only_and_set_is_skipped():     # 실측 Z4
    from tests.fake_assign import Track
    surface, fake, logic = make_assign_logic([Track(1, "1"), Track(3, "StOu", kind="output")])
    cmds = Commands(surface, FaderTable.load(), sleep=logic.sleep, logic_running=lambda: True)
    r = cmds.eq.get(strip=2, number=None)
    assert r.verified == "verified" and r.after == {"has_eq": False, "bands": {}} and "출력" in r.note
    r = cmds.eq.set(strip=2, number=None, band=3, param="gain", value=-3.0)
    assert r.verified == "skipped" and "출력" in r.note
    assert logic.tracks[0].eq is None and logic.tracks[1].eq is None and surface.state.view.kind == "pan"
```

- [ ] **Step 6: 실패 확인**

Run: `uv run pytest tests/test_assign_plugin.py tests/test_assign_eq.py -k "output or kinds" -v`
Expected: FAIL (가드 없음 → verified 또는 엉뚱한 트랙 변경).

- [ ] **Step 7: assign.py 수정**

임포트에 `from .strips import StripUnsupported`를 더한다. `PluginCommands._channel` 첫 줄에 가드:

```python
    def _channel(self, ch: int) -> None:
        """대상 트랙을 선택하고 Plug-in Channel 뷰(PL)로 간다. 2행 = 선택 트랙의 슬롯 1~8, V-Pot n = 슬롯 n(실측 C·D).
        PL 안에서 SELECT 만 눌러 트랙을 바꾸면 2행이 그 트랙의 슬롯으로 바뀌지 않는다(실측 Z3) → 이미 PL 이고 다른 스트립이면
        PAN 으로 나가 다시 들어간다. 출력·Master 스트립은 PL이 아예 따라가지 않으므로 먼저 막는다(실측 Z4, 수정 8)."""
        self.b.strips.ensure(self.d, self.b.surface.state, ch)
        if self.d.view.kind != "pan" and not self.b.surface.state.strips[ch].select:
            self.d.leave(keep_select=True)
        self.d.focus(ch)
        self.d.enter("plugin_channel")
```

`params`·`get`·`set`·`insert`·`remove`·`bypass`의 `except SlotEmpty:`(없는 메서드는 `except ModeError` 앞)에 다음 분기를 더한다(여섯 곳 모두 같은 두 줄):

```python
            except StripUnsupported as e:
                return b._result(action, False, "skipped", t0, target=target, note=e.note)
```

`list`는 단일 트랙·뱅크를 나눠 처리한다. `try:` 블록을 다음으로 바꾼다:

```python
            try:
                self._fresh()
                targets = [only] if only is not None else [
                    ch for ch, s in enumerate(b.surface.state.strips) if s.number is not None]
                tracks: dict[str, dict[str, dict | None] | None] = {}
                unsupported: list[int] = []
                learned = False
                for ch in targets:
                    num = b.surface.state.strips[ch].number     # PL은 1행이 채널명이 아니라 PAN에서 읽은 번호를 쓴다
                    try:
                        self._channel(ch)
                    except StripUnsupported as e:
                        if only is not None:
                            return b._result(action, False, "skipped", t0, note=e.note)
                        tracks[str(num)] = None                 # 출력·Master: PL이 따라가지 않아 읽지 않는다(실측 Z4)
                        unsupported.append(num)
                        continue
                    d.settle_overlay()
                    texts = [d.view.columns[i][1].strip() for i in range(MAX_SLOT)]
                    row: dict[str, dict | None] = {}
                    revealed = False
                    for i, text in enumerate(texts):
                        if text in EMPTY_TEXTS:
                            row[str(i + 1)] = None
                            continue
                        name = self.cache.abbrev.get(text.lstrip("*"))
                        if name is None:
                            d.tick(i, -1)                       # ceil 모델: -1 = 현재 항목, +1은 다음 항목(실측 E)
                            shown = strip_suffix(d.read_overlay_text(i))
                            revealed = True
                            if shown and shown != "--":
                                name = self._complete(shown)
                                self.cache.learn_abbrev(text.lstrip("*"), name)
                                learned = True
                        row[str(i + 1)] = {"text": text, "name": name}
                    tracks[str(num)] = row
                    if revealed:
                        d.leave(keep_select=True)               # 드러낸 미리 선택은 누르지 않고 모드 전환으로 취소
                if learned:
                    self.cache.save()
                self.inventory.update(tracks)
                after = {"tracks": tracks} if only is not None else {"tracks": tracks, "unsupported": unsupported}
                return b._result(action, True, "verified", t0, after=after)
```

`self.inventory`의 타입 주석을 `dict[str, dict[str, dict | None] | None]`로 바꾼다.

`EqCommands.get`의 `try:` 첫 부분을 다음으로 바꾼다:

```python
            try:
                if not b.strips.follows(d, b.surface.state, ch):           # 출력·Master: E1 뷰의 유무만(실측 Z4)
                    d.focus(ch)
                    return b._result(action, True, "verified", t0, target=target,
                                     after={"has_eq": self._has_eq(ch), "bands": {}},
                                     note="출력·Master 스트립: EQ 채널 뷰가 따라가지 않아 밴드 값은 읽지 않음(실측 Z4)")
                d.focus(ch)
                if not self._has_eq(ch):
                    …
```

`EqCommands.set`의 `try:` 첫 줄에 `b.strips.ensure(d, b.surface.state, ch)`를 넣고, `except ModeError` 앞에 `except StripUnsupported as e: return b._result(action, False, "skipped", t0, target=target, note=e.note)`를 더한다.

- [ ] **Step 8: 통과 확인**

Run: `uv run pytest -q`
Expected: 전부 PASS(기존 `test_list_inventory_whole_bank`는 `after["unsupported"] == []`가 추가돼도 `after["tracks"]` 단언만 있어 그대로 통과).

- [ ] **Step 9: 커밋**

```bash
git add src/logic_mcp/logic/strips.py src/logic_mcp/logic/commands.py src/logic_mcp/logic/assign.py tests/test_strips.py tests/test_assign_plugin.py tests/test_assign_eq.py
git commit -m "fix(assign): 출력·Master 스트립은 채널 뷰가 따라가지 않아 EQ·플러그인 명령을 막음 (수정 8, 실측 Z4·Z5)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: 가짜 Logic 센드 모델

**Files:**
- Modify: `tests/fake_assign.py` (`Send`, `Track.sends`, SEND 버튼·S1·SE·미리 선택·확정·Flip·틱)
- Test: `tests/test_modes.py`

**Interfaces:**
- Consumes: 실측 S1~S11, 기존 `_pre_cell`·`timers`·`deferred` 구조, `FaderTable`.
- Produces: `Send(dest: str, level: float, pos: int, muted: bool)`(`pos` 0 Pre·1 Post·2 Post Pan, `level` dB, `-inf` 허용), `Track.sends: dict[int, Send | None]`(1~8), `Track.se_page`, `FakeLogic.dest_list`(기본 `DEST_LIST = ["--", "1", "2", "Bus 1", …, "Bus 8"]`), `FakeLogic.se_track`, 뷰 `send_menu`/`send_mixer`/`send_channel`. SE 2행 표기: dest `Bus 2`(뮤트면 `*Bus 2`), level `-oodB`/`+4.5dB`/`-29.2dB`, pos `Pre`/`Post`/`PosPan`, mute `active`/`muted`; 센드 없으면 dest `--`, 나머지 빈칸, 1행 `Sen{n}In - - -`.

- [ ] **Step 1: 실패하는 테스트**

`tests/test_modes.py` 끝에:

```python
def test_enter_send_channel_waits_out_menu_pages_and_remembers_page():      # 실측 S1·S3
    d, surface, fake, logic = make()
    d.focus(1)
    d.enter("send_channel")
    assert surface.state.view.kind == "send_channel" and logic.view == "send_channel"
    assert surface.state.view.columns[0][0] == "Sen1In " and surface.state.view.columns[0][1] == "--     "
    assert surface.state.view.columns[4][0] == "Sen2In " and surface.state.view.columns[1][1] == "       "
    assert d.page_until(lambda v: v.columns[0][0].startswith("Sen3"), forward=True, max_steps=1)
    d.leave(keep_select=True)
    d.enter("send_channel")
    assert surface.state.view.columns[0][0] == "Sen3In "                     # 마지막 페이지를 기억
    assert d.page_until(lambda v: v.columns[0][0].startswith("Sen1"), forward=False, max_steps=1)


def test_send_dest_preselect_is_one_tick_per_item_blinks_and_pan_cancels():  # 실측 S4·S10
    d, surface, fake, logic = make()
    d.focus(0)
    d.enter("send_channel")
    assert d.tick(0, 3)
    assert d.read_overlay_name(0) == "Send 1 Destination" and d.read_overlay_text(0) == "Bus 1"
    d.settle_overlay()
    texts = set()
    for _ in range(4):
        texts.add(surface.state.view.columns[0][1].strip()); logic.sleep(0.4)
    assert texts == {"Bus 1", ""}                                             # 0.8초 주기 깜박임
    d.tick(0, -63)
    assert d.read_overlay_text(0) == "--"
    d.tick(0, 4)
    assert d.read_overlay_text(0) == "Bus 2"
    d.leave()
    assert not logic.pre and logic.tracks[0].sends[1] is None
    d.focus(0); d.enter("send_channel")
    assert surface.state.view.columns[0][1] == "--     "


def test_send_confirm_instantiates_and_flip_fader_sets_level_with_volume_table():   # 실측 S5·S6
    from logic_mcp.logic.faders import FaderTable
    d, surface, fake, logic = make()
    d.focus(0); d.enter("send_channel")
    d.tick(0, 4)
    assert d.press_vpot_until(0, lambda v: v.columns[0][1].strip() == "Bus 2" and v.columns[1][1].strip() == "-oodB", CONFIRM_S)
    d.settle_overlay()
    s = logic.tracks[0].sends[1]
    assert s is not None and s.dest == "Bus 2" and s.level == float("-inf") and s.pos == 2 and not s.muted
    assert [c[1].strip() for c in surface.state.view.columns[:4]] == ["Bus 2", "-oodB", "PosPan", "active"]
    d.flip(True)
    assert d.fader(1, FaderTable.load().db_to_raw(-6.0)) is not None
    assert abs(logic.tracks[0].sends[1].level - -6.0) <= 0.1
    assert d.read_value(1).number == -6.0 and d.read_value(1).unit == "dB"
    d.flip(False)
    d.tick(2, 1); d.settle_overlay()
    assert surface.state.view.columns[2][1].strip() == "PosPan"              # 끝(Post Pan)에서 +1은 무변화
    d.tick(2, -2); d.settle_overlay()
    assert surface.state.view.columns[2][1].strip() == "Pre" and logic.tracks[0].sends[1].pos == 0
    d.tick(3, 1); d.settle_overlay()
    assert surface.state.view.columns[3][1].strip() == "muted" and surface.state.view.columns[0][1].strip() == "*Bus 2"
    d.tick(3, -1); d.settle_overlay()
    assert surface.state.view.columns[3][1].strip() == "active" and surface.state.view.columns[0][1].strip() == "Bus 2"
    d.leave()
    assert surface.state.view.kind == "pan" and not surface.state.assignment.flip
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_modes.py -k "send" -v`
Expected: FAIL (`AssertionError: send_mixer` 등 — 가짜가 센드 뷰를 모른다).

- [ ] **Step 3: fake_assign.py 수정 — 모델과 화면**

모듈 상단(`ABBREV` 뒤)에:

```python
from logic_mcp.logic.faders import FaderTable

DEST_LIST = ["--", "1", "2"] + [f"Bus {i}" for i in range(1, 9)]   # 실측 S4: 앞의 `1`, `2`는 정체 미확인, 1틱 = 1항목
POS_COL = ("Pre", "Post", "PosPan")                                 # 정착 열(실측 S8)
POS_FULL = ("Pre", "Post", "Post Pan")                              # 오버레이
SEND_MENU = "Dest   Level  Pos    Mute   CStrip CStr2  Ds/LvM Ds/LvC "
FADERS = FaderTable.load()
LEVEL_FLOOR = -96.0                                                  # 이 아래는 `-oodB`


@dataclass
class Send:
    dest: str                   # `Bus 2`
    level: float = float("-inf")
    pos: int = 2                # 0 Pre, 1 Post, 2 Post Pan (새 센드 기본 Post Pan, 실측 S5)
    muted: bool = False

    def level_col(self) -> str:
        return col("-oodB" if self.level <= LEVEL_FLOOR else f"{self.level:+.1f}dB")

    def level_full(self) -> str:
        return "-oo dB" if self.level <= LEVEL_FLOOR else f"{self.level:+.1f} dB"
```

`Track`에 필드 추가(`kind` 뒤):

```python
    sends: dict[int, Send | None] = field(default_factory=lambda: {i: None for i in range(1, 9)})
    se_page: int = 1                                              # SE 뷰가 기억하는 마지막 페이지(실측 S3)
```

`FakeLogic.__init__`에:

```python
        self.se_track = 0                              # SE 뷰 2행이 보여 주는 트랙(출력·Master를 고르면 안 바뀜, 실측 S10)
        self.send_held = False
        self.dest_list = list(DEST_LIST)
```

`_rows()`에 센드 뷰 세 가지를 더한다(`if self.view == "pan":` 앞):

```python
        if self.view == "send_menu":
            return " " * 56, SEND_MENU, "S_"
        if self.view == "send_mixer":
            cells = [col(tr.sends[1].dest if tr.sends[1] else "--") for tr in self.tracks[:8]]
            return self._names_row(), "".join(cells).ljust(56), "S1"
        if self.view == "send_channel":
            st = self.tracks[self.se_track]
            r1, r2 = [], []
            for n in (2 * self.page - 1, 2 * self.page):
                s = st.sends.get(n)
                if s is None:
                    r1 += [col(f"Sen{n}In"), col("-"), col("-"), col("-")]
                    r2 += [self._pre_cell_send(n, col("--")), col(""), col(""), col("")]
                else:
                    r1 += [col(f"Sen{n}De"), col(s.dest.replace("Bus ", "")), col(f"Sen{n}Po"), col(f"Sen{n}Mu")]
                    r2 += [self._pre_cell_send(n, col(("*" if s.muted else "") + s.dest)), s.level_col(),
                           col(POS_COL[s.pos]), col("muted" if s.muted else "active")]
            return "".join(r1).ljust(56), "".join(r2).ljust(56), "SE"
```

`_pre_cell` 아래에 센드용 깜박임 셀을 더한다:

```python
    def _pre_cell_send(self, n: int, fallback: str) -> str:
        ch = ((n - 1) % 2) * 4
        if self.view != "send_channel" or ch not in self.pre:
            return fallback
        return col(self.dest_list[self.pre[ch]]) if self.blink_on else col("")
```

`sleep()`의 깜박임 조건을 `self.view in ("plugin_mixer", "plugin_channel", "send_channel")`로 넓힌다.

- [ ] **Step 4: fake_assign.py 수정 — 입력**

`replies()`의 EQ 분기 앞에 SEND 분기(실측 S1: down `S_`, up 뒤 뷰):

```python
            elif note == P.Note.SEND:
                self.send_held = on
                if on:
                    self.view_before_menu = self.view
                    self.view = "send_menu"
                    self.redraw()
                else:
                    self.deferred.append(lambda: self._button(P.Note.SEND))
```

`_button()`에 SEND 처리(`elif note == N.PLUGIN:` 앞):

```python
        elif note == N.SEND:
            prev = getattr(self, "view_before_menu", "pan")
            if prev == "send_mixer":
                self.view, self.page = "send_channel", self.tracks[self.se_track].se_page
                self.pre.clear()
                self.redraw()
            elif prev == "send_channel":
                self.view = "send_mixer"
                self.pre.clear()
                self.redraw()
            else:
                self._set_mode("send_mixer", N.SEND)
                self.se_track = self.selected if self.tracks[self.selected].follows else self.se_track
                self.redraw(mode_overlay="Send 1 Parameter: Send 1 Destination")
```

SELECT 분기(`if N.SELECT <= note < N.SELECT + 8:`)의 `pl_track` 갱신을 다음으로 바꾼다(출력·Master 선택은 PL·SE 2행을 바꾸지 않음, 실측 Z4·S10):

```python
            if self.tracks[self.selected].follows:
                if not (self.pl_select_stale and self.view == "plugin_channel"):
                    self.pl_track = self.selected
                self.se_track = self.selected
```

PLUGIN 분기의 `self.pl_track = self.selected`(plugin_mixer → plugin_channel)도 `if self.tracks[self.selected].follows:` 조건을 붙인다. Task 1에서 `Track.kind`·`follows`가 이미 있다.

`_page()`에 SE 페이지(1~4, 트랙별 기억):

```python
        elif self.view == "send_channel":
            self.page = max(1, min(4, self.page + delta))
            if self.page == old:
                return
            self.tracks[self.se_track].se_page = self.page
```

`_vpot()` 맨 앞에 SE 처리:

```python
        if self.view == "send_channel":
            self._vpot_send(ch, ticks)
            return
```

새 메서드:

```python
    def _send_at(self, ch: int) -> tuple[int, int, Send | None]:
        """SE 열 → (센드 번호, 필드 0 dest·1 level·2 pos·3 mute, 센드)."""
        n = 2 * self.page - 1 + ch // 4
        return n, ch % 4, self.tracks[self.se_track].sends.get(n)

    def _vpot_send(self, ch: int, ticks: int) -> None:
        n, fld, s = self._send_at(ch)
        if fld == 0:                                                 # 목적지 미리 선택: 1틱 = 1항목(실측 S4)
            if ch not in self.pre:
                self.pre = {ch: self.dest_list.index(s.dest) if s else 0}
            self.pre[ch] = max(0, min(len(self.dest_list) - 1, self.pre[ch] + ticks))
            self.redraw(overlay=(ch, f"Send {n} Destination", self.dest_list[self.pre[ch]]))
            return
        if s is None:
            return                                                   # 센드 없으면 level/pos/mute 무반응(실측 S11)
        if fld == 1:
            s.level = max(LEVEL_FLOOR - 1, min(6.0, (LEVEL_FLOOR if s.level < LEVEL_FLOOR else s.level) + 0.5 * ticks))
            self.redraw(overlay=(ch, f"{n}  Aux 1      Sen{n}Mu", s.level_full()))
        elif fld == 2:
            s.pos = max(0, min(2, s.pos + ticks))
            self.redraw(overlay=(ch, f"Send {n} Position", POS_FULL[s.pos]))
        else:
            s.muted = ticks > 0
            self.redraw(overlay=(ch, f"Send {n} Mute   -", "muted" if s.muted else "active"))
```

`_push()` 맨 앞에:

```python
        if self.view == "send_channel":
            self._push_send(ch)
            return
```

```python
    def _push_send(self, ch: int) -> None:
        """dest 열 누름: 미리 선택이 있으면 `Send n Instantiate` 오버레이 → 2초 뒤 센드 생성/제거(실측 S5)."""
        n, fld, _s = self._send_at(ch)
        if fld != 0 or ch not in self.pre:
            return
        name = self.dest_list[self.pre[ch]]
        self.pre.clear()
        track = self.tracks[self.se_track]

        def commit() -> None:
            track.sends[n] = None if name == "--" else Send(name)
            self.redraw()
        self.timers.append((self.clock() + OVERLAY_S, commit))
        self.redraw(overlay=(ch, f"Send {n} Instantiate", name))
```

Flip·페이더: `_button()`의 FLIP 분기에서 `if self.flip:` 에코를 다음으로 바꾼다:

```python
            if self.flip:
                self._emit([fader_echo(ch, self._flip_raw(ch)) for ch in range(8)])
```

```python
    def _flip_raw(self, ch: int) -> int:
        if self.view == "send_channel":
            _n, fld, s = self._send_at(ch)
            if fld == 1 and s is not None:
                return 0 if s.level <= LEVEL_FLOOR else FADERS.db_to_raw(s.level)
            return 0
        p = self._column_param(ch)
        return p.raw() if p else 0
```

`_fader()`의 `p = self._column_param(ch)` 앞에:

```python
        if self.view == "send_channel":                                 # SE Flip: 레벨 열 페이더 = 센드 dB(볼륨 표, 실측 S6)
            n, fld, s = self._send_at(ch)
            if fld != 1 or s is None:
                return
            new = FADERS.raw_to_db(raw)
            if new == s.level:
                return
            s.level = new
            self._emit([fader_echo(ch, FADERS.db_to_raw(new) if new > LEVEL_FLOOR else 1)])
            self.redraw(overlay=(ch, f"{n}  Aux 1      Sen{n}Mu", s.level_full()))
            return
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/test_modes.py tests/test_assign_plugin.py tests/test_assign_eq.py -q`
Expected: 전부 PASS.

- [ ] **Step 6: 커밋**

```bash
git add tests/fake_assign.py tests/test_modes.py
git commit -m "test(fake): 센드 모델 — S_ 메뉴·S1·SE 페이지 기억·1틱 미리 선택·확정·Flip 레벨·pos·mute (실측 S1~S11)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: `SendCommands` — get · set_dest · remove (`logic/sends.py`)

**Files:**
- Create: `src/logic_mcp/logic/sends.py`
- Modify: `src/logic_mcp/logic/commands.py` (`Commands.send`)
- Test: `tests/test_sends.py` (헬퍼), `tests/test_assign_send.py` (명령)

**Interfaces:**
- Consumes: Task 2 `Commands.strips`, Task 3 가짜 센드 모델, `plugins.scan.rewind_to_empty`(오버레이 `--`까지 -63 되감기 — 센드에도 그대로 쓸 수 있다), `ModeDriver.page_until`·`press_vpot_until`·`read_overlay_text`.
- Produces: 헬퍼 `col_of(send, field)`, `page_of(send)`, `se_page_of(view)`, `bus_number(text)`, `pos_of_text(text)`, `parse_send(columns, send) -> dict`, `dest_query(dest) -> int | None`; `SendCommands.get(strip, number)`, `set_dest(strip, number, send, dest)`, `remove(strip, number, send)`; 결과 `action` 이름 `send_get`·`send_set_dest`·`send_remove`; `get`의 `after={"sends": {"1": {...}, …, "8": {...}}}`, 항목 = `{"send", "present", "dest", "bus", "level_db", "pos", "muted", "text"}`.

- [ ] **Step 1: 실패하는 테스트 — 헬퍼**

`tests/test_sends.py`:

```python
import math

from logic_mcp.logic.sends import bus_number, col_of, dest_query, page_of, parse_send, pos_of_text, se_page_of
from logic_mcp.mcu.state import View, lcd_columns


def cols(r1: str, r2: str):
    return lcd_columns((r1.ljust(56), r2.ljust(56)))


def test_column_and_page_math():
    assert [col_of(1, f) for f in ("dest", "level", "pos", "mute")] == [0, 1, 2, 3]
    assert col_of(2, "dest") == 4 and col_of(8, "mute") == 7
    assert [page_of(s) for s in range(1, 9)] == [1, 1, 2, 2, 3, 3, 4, 4]
    assert se_page_of(View(columns=cols("Sen3In -      -      -      Sen4In -      -      -      ", ""))) == 2
    assert se_page_of(View(columns=cols("Sen1De 1      Sen1Po Sen1Mu Sen2De -      -      -      ", ""))) == 1
    assert se_page_of(View(columns=cols("Sen9In -      -      -      Sen10I -      -      -      ", ""))) == 5
    assert se_page_of(View(columns=cols("Send 1 Destination   -      Sen2In -      -      -      ", ""))) is None


def test_bus_number_pos_and_dest_query():
    assert bus_number("Bus 2") == 2 and bus_number("*Bus 12 ") == 12 and bus_number("--") == 0
    assert bus_number("1") is None and bus_number("") is None and bus_number("Aux 1") is None
    assert [pos_of_text(t) for t in ("Pre", "Post", "PosPan", "Post Pa", "Post Pan", "")] == ["pre", "post", "post_pan", "post_pan", "post_pan", None]
    assert dest_query("Bus 3") == 3 and dest_query("3") == 3 and dest_query(3) == 3 and dest_query("bus 12") == 12
    assert dest_query("--") == 0 and dest_query("") == 0 and dest_query(0) == 0
    assert dest_query("Aux 1") is None and dest_query(257) is None and dest_query(True) is None and dest_query(None) is None


def test_parse_send_by_position_only():                                             # 실측 S2·S9
    c = cols("Sen1De 1      Sen1Po Sen1Mu Sen2In -      -      -      ",
             "*Bus 2 -29.2 dPosPan muted  --                          ")
    s1 = parse_send(c, 1)
    assert s1 == {"send": 1, "present": True, "dest": "Bus 2", "bus": 2, "level_db": -29.2, "pos": "post_pan", "muted": True,
                  "text": ["*Bus 2", "-29.2 d", "PosPan", "muted"]}
    assert parse_send(c, 2) == {"send": 2, "present": False, "dest": None, "bus": None, "level_db": None, "pos": None,
                                "muted": None, "text": ["--", "", "", ""]}
    c = cols("Sen3In 1  Aux 1      Sen3Mu Sen4In -      -      -      ", "Bus 2  -oodB  Pre    active --")
    s3 = parse_send(c, 3)
    assert s3["level_db"] == -math.inf and s3["pos"] == "pre" and s3["muted"] is False and s3["bus"] == 2
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_sends.py -v`
Expected: FAIL (`logic_mcp.logic.sends` 없음).

- [ ] **Step 3: sends.py 헬퍼 작성**

```python
"""센드 명령(스펙 2b §4.3, 실측 S1~S11). SE(센드 채널) 뷰 한 곳에서만 다룬다: 2센드/페이지, 열 = (홀수 센드 0, 짝수 4) +
{dest 0, level 1, pos 2, mute 3}. 1행 라벨은 `Sen1In`/`Sen1De`/목적지 번호로 흔들리므로 열 위치로만 해석한다(S2).
목적지는 버스 번호 모델: `--`로 되감은 뒤 `번호+DEST_PREFIX` 틱, 오버레이의 `Bus m`을 읽어 보정, V-Pot 누름으로 확정(S4·S5).
레벨은 Flip 페이더(볼륨 dB 표, S6), pos·mute는 틱(S8·S9)."""
from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING

from .modes import CONFIRM_S, ModeError
from .plugins.scan import rewind_to_empty
from .setter import set_numeric
from .strips import StripUnsupported
from .values import Mapping, parse_value

if TYPE_CHECKING:
    from .commands import Commands, ToolResult

MAX_SEND = 8
MAX_BUS = 256
FIELDS = ("dest", "level", "pos", "mute")
POS_ORDER = ("pre", "post", "post_pan")                  # 틱 +1 방향(실측 S8)
DEST_PREFIX = 2                                           # `--` 뒤 `1`, `2` 다음이 `Bus 1`(실측 S4). 다르면 보정 루프가 맞춘다
EMPTY = ("", "--")
_POS_TEXT = {"pre": "pre", "post": "post", "pospan": "post_pan", "postpa": "post_pan", "postpan": "post_pan"}
_SEN_RE = re.compile(r"Sen(\d+)")
_BUS_RE = re.compile(r"Bus\s*(\d+)")
_QUERY_RE = re.compile(r"(?:[Bb]us\s*)?(\d+)")


def col_of(send: int, field: str) -> int:
    return (0 if send % 2 == 1 else 4) + FIELDS.index(field)


def page_of(send: int) -> int:
    return (send + 1) // 2


def se_page_of(view) -> int | None:
    """1행 첫 열 `Sen<n>…`으로 현재 페이지. 오버레이가 덮었으면 None."""
    m = _SEN_RE.match(view.columns[0][0].strip())
    return page_of(int(m.group(1))) if m else None


def bus_number(text: str) -> int | None:
    """`Bus 2`·`*Bus 2` → 2, `--` → 0, 그 밖(`1`, `2`, 빈칸, `Aux 1`) → None."""
    t = text.strip().lstrip("*")
    if t == "--":
        return 0
    m = _BUS_RE.fullmatch(t)
    return int(m.group(1)) if m else None


def pos_of_text(text: str) -> str | None:
    return _POS_TEXT.get(text.strip().replace(" ", "").lower())


def parse_send(columns, send: int) -> dict:
    off = col_of(send, "dest")
    texts = [columns[off + i][1].strip() for i in range(4)]
    dest = texts[0].lstrip("*")
    present = dest not in EMPTY
    if not present:
        return {"send": send, "present": False, "dest": None, "bus": None, "level_db": None, "pos": None, "muted": None,
                "text": texts}
    level = parse_value(texts[1])
    return {"send": send, "present": True, "dest": dest, "bus": bus_number(texts[0]),
            "level_db": level.number if level.kind == "number" else None, "pos": pos_of_text(texts[2]),
            "muted": texts[0].startswith("*") or texts[3] == "muted", "text": texts}


def dest_query(dest) -> int | None:
    """`"Bus 3"`·`"3"`·`3` → 3, `"--"`·`""`·`0` → 0(제거), 그 밖 → None."""
    if dest is None or isinstance(dest, bool):
        return None
    if isinstance(dest, int):
        return dest if 0 <= dest <= MAX_BUS else None
    t = str(dest).strip()
    if t in EMPTY or t == "0":
        return 0
    m = _QUERY_RE.fullmatch(t)
    n = int(m.group(1)) if m else None
    return n if n is not None and 1 <= n <= MAX_BUS else None
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_sends.py -v`
Expected: PASS.

- [ ] **Step 5: 실패하는 테스트 — 명령**

`tests/test_assign_send.py`:

```python
import math

import pytest

from logic_mcp.logic.commands import Commands
from logic_mcp.logic.faders import FaderTable
from logic_mcp.mcu import protocol as P
from tests.fake_assign import Send, Track, make_assign_logic


def make(tracks=None):
    surface, fake, logic = make_assign_logic(tracks)
    cmds = Commands(surface, FaderTable.load(), sleep=logic.sleep, logic_running=lambda: True)
    return cmds, surface, fake, logic


def pushes(msgs: list[bytes]) -> list[int]:
    return [m[1] - P.Note.VPOT_PUSH for m in msgs if m[0] == 0x90 and P.Note.VPOT_PUSH <= m[1] < P.Note.VPOT_PUSH + 8 and m[2]]


def test_get_reads_all_eight_sends_by_column_position():
    cmds, surface, fake, logic = make()
    logic.tracks[0].sends[1] = Send("Bus 2", -6.0, 0, False)
    logic.tracks[0].sends[4] = Send("Bus 5", float("-inf"), 2, True)
    r = cmds.send.get(strip=1, number=None)
    assert r.verified == "verified" and r.action == "send_get" and r.target == {"strip": 1, "number": 15, "name": "DCl"}
    s = r.after["sends"]
    assert len(s) == 8
    assert s["1"] == {"send": 1, "present": True, "dest": "Bus 2", "bus": 2, "level_db": -6.0, "pos": "pre", "muted": False,
                      "text": ["Bus 2", "-6.0dB", "Pre", "active"]}
    assert s["4"]["bus"] == 5 and s["4"]["level_db"] == -math.inf and s["4"]["pos"] == "post_pan" and s["4"]["muted"] is True
    assert s["2"]["present"] is False and s["8"]["present"] is False
    assert surface.state.view.kind == "pan" and logic.selected == 0


def test_get_reads_from_remembered_page():                                          # Review Focus 4, 실측 S3
    cmds, surface, fake, logic = make()
    logic.tracks[0].se_page = 3
    logic.tracks[0].sends[1] = Send("Bus 1")
    r = cmds.send.get(strip=1, number=None)
    assert r.after["sends"]["1"]["bus"] == 1 and r.after["sends"]["5"]["present"] is False


def test_set_dest_bus_3_confirms_and_notes_aux_creation():                          # 실측 S4·S5
    cmds, surface, fake, logic = make()
    n0 = len(fake.sent)
    r = cmds.send.set_dest(strip=1, number=None, send=1, dest="Bus 3")
    assert r.ok and r.verified == "verified" and r.action == "send_set_dest" and "Aux" in r.note
    s = logic.tracks[0].sends[1]
    assert s is not None and s.dest == "Bus 3" and s.level == -math.inf and s.pos == 2 and not s.muted
    assert r.before["present"] is False and r.after["bus"] == 3 and r.after["present"] is True
    assert pushes(fake.sent[n0:]) == [0] and surface.state.view.kind == "pan" and not logic.pre


@pytest.mark.parametrize("prefix", [[], ["1", "2", "3", "4"]])
def test_set_dest_adjusts_when_prefix_count_differs(prefix):                        # Review Focus 2
    cmds, surface, fake, logic = make()
    logic.dest_list = ["--"] + prefix + [f"Bus {i}" for i in range(1, 9)]
    r = cmds.send.set_dest(strip=1, number=None, send=2, dest=2)
    assert r.verified == "verified" and logic.tracks[0].sends[2].dest == "Bus 2"


def test_set_dest_does_not_press_when_overlay_mismatches():                         # Review Focus 2
    cmds, surface, fake, logic = make()
    logic.dest_list = ["--", "1", "2"] + [f"Bus {i}" for i in (1, 2, 3, 5, 6, 7, 8, 9)]   # Bus 4 없음
    n0 = len(fake.sent)
    r = cmds.send.set_dest(strip=1, number=None, send=1, dest="Bus 4")
    assert r.verified == "unverified" and "확정하지 않음" in r.note
    assert pushes(fake.sent[n0:]) == [] and logic.tracks[0].sends[1] is None and not logic.pre
    assert surface.state.view.kind == "pan"


def test_set_dest_already_and_remove():
    cmds, surface, fake, logic = make()
    logic.tracks[0].sends[3] = Send("Bus 2")
    r = cmds.send.set_dest(strip=1, number=None, send=3, dest="2")
    assert r.verified == "skipped" and r.note == "already"
    r = cmds.send.remove(strip=1, number=None, send=3)
    assert r.verified == "verified" and r.action == "send_remove" and logic.tracks[0].sends[3] is None
    assert r.after["present"] is False and r.before["bus"] == 2
    r = cmds.send.remove(strip=1, number=None, send=3)
    assert r.verified == "skipped" and r.note == "already"


def test_set_dest_rejects_bad_dest_and_send():
    cmds, surface, fake, logic = make()
    r = cmds.send.set_dest(strip=1, number=None, send=1, dest="Aux 1")
    assert r.verified == "skipped" and "버스 번호" in r.note
    assert cmds.send.set_dest(strip=1, number=None, send=9, dest=1).verified == "skipped"
    assert cmds.send.set_dest(strip=1, number=None, send=1, dest=1).ok   # 정상 경로는 그대로
    assert surface.state.view.kind == "pan"


def test_set_dest_on_output_strip_is_skipped():                                     # Review Focus 1, 실측 Z4·S10
    cmds, surface, fake, logic = make([Track(1, "1"), Track(3, "StOu", kind="output")])
    r = cmds.send.set_dest(strip=2, number=None, send=1, dest=1)
    assert r.verified == "skipped" and "출력" in r.note
    assert all(s is None for t in logic.tracks for s in t.sends.values()) and surface.state.view.kind == "pan"
    assert cmds.send.get(strip=2, number=None).verified == "skipped"
```

- [ ] **Step 6: 실패 확인**

Run: `uv run pytest tests/test_assign_send.py -v`
Expected: FAIL (`Commands`에 `send` 없음).

- [ ] **Step 7: SendCommands 작성(sends.py 아래쪽)과 Commands 연결**

```python
class SendCommands:
    def __init__(self, base: "Commands") -> None:
        self.b = base
        self.d = base.modes

    # ---------- 공통 ----------
    def _fresh(self) -> None:
        if self.d.view.kind != "pan" or self.b.surface.state.assignment.flip:
            self.d.leave(keep_select=True)

    def _channel(self, ch: int) -> None:
        """대상 트랙을 선택하고 SE 뷰로 간다. 출력·Master는 SE가 따라가지 않으므로 먼저 막는다(실측 Z4·S10).
        이미 SE고 다른 스트립이면 PAN으로 나가 다시 들어간다(PL의 Z3와 같은 규칙)."""
        self.b.strips.ensure(self.d, self.b.surface.state, ch)
        if self.d.view.kind != "pan" and not self.b.surface.state.strips[ch].select:
            self.d.leave(keep_select=True)
        self.d.focus(ch)
        self.d.enter("send_channel")

    def _goto_page(self, send: int) -> None:
        """SE는 마지막 페이지를 기억하므로(실측 S3) 1행 `Sen<n>`으로 현재 페이지를 읽어 커서로 간다."""
        page = page_of(send)
        cur = se_page_of(self.d.view)
        if cur is None:
            raise ModeError("page", "1행 `Sen<n>` 라벨", self.d.view.columns[0][0].strip() or "빈 열")
        if cur == page:
            return
        if not self.d.page_until(lambda v: se_page_of(v) == page, forward=page > cur, max_steps=abs(page - cur)):
            raise ModeError("page", f"센드 {send}의 페이지 {page}", f"페이지 {se_page_of(self.d.view)}")

    def _row(self, send: int) -> dict:
        return parse_send(self.d.view.columns, send)

    def _begin(self, action: str, strip, number, send, t0):
        if not 1 <= send <= MAX_SEND:
            return self.b._result(action, False, "skipped", t0, note=f"send는 1-{MAX_SEND}")
        return self.b._resolve(strip, number, action, t0)

    def _fail(self, action: str, t0: int, target: dict, e: Exception) -> "ToolResult":
        if isinstance(e, StripUnsupported):
            return self.b._result(action, False, "skipped", t0, target=target, note=e.note)
        if isinstance(e, ModeError):
            return self.b._result(action, False, "unverified", t0, target=target, note=str(e))
        return self.b._result(action, False, "skipped", t0, target=target, note=f"값 오류: {e}")

    # ---------- 명령 ----------
    def get(self, strip: int | None, number: int | None) -> "ToolResult":
        b, d, action = self.b, self.d, "send_get"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = b._resolve(strip, number, action, t0)
            if not isinstance(ch, int):
                return ch
            target = b._target(ch)
            try:
                self._fresh()
                self._channel(ch)
                sends: dict[str, dict] = {}
                for page in range(1, MAX_SEND // 2 + 1):
                    self._goto_page(2 * page - 1)
                    for send in (2 * page - 1, 2 * page):
                        sends[str(send)] = self._row(send)
                return b._result(action, True, "verified", t0, target=target, after={"sends": sends})
            except (StripUnsupported, ModeError, ValueError) as e:
                return self._fail(action, t0, target, e)
            finally:
                d.leave_safely()

    def set_dest(self, strip: int | None, number: int | None, send: int, dest) -> "ToolResult":
        b, d = self.b, self.d
        want = dest_query(dest)
        action = "send_remove" if want == 0 else "send_set_dest"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            if want is None:
                return b._result(action, False, "skipped", t0,
                                 note=f"dest는 버스 번호(1-{MAX_BUS}, 예: \"Bus 3\"·3) 또는 \"--\"(제거). 받은 값: {dest!r}")
            ch = self._begin(action, strip, number, send, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "send": send}
            col = col_of(send, "dest")
            try:
                self._fresh()
                self._channel(ch)
                self._goto_page(send)
                before = self._row(send)
                if (before["bus"] or 0) == want:
                    return b._result(action, True, "skipped", t0, target=target, before=before, after=before, note="already")
                rewind_to_empty(d, col)                                  # 오버레이 `--`까지(1틱 = 1항목이라 -63이면 넉넉, 실측 S4)
                if want > 0:
                    d.tick(col, want + DEST_PREFIX)
                    shown = bus_number(d.read_overlay_text(col))
                    for _ in range(4):                                   # 목록 앞 항목 수가 다르면 보이는 번호로 보정(실측 S4)
                        if shown == want:
                            break
                        d.tick(col, 1 if not shown else want - shown)    # `--`·`1`·`2`처럼 버스가 아니면 한 칸 앞으로
                        shown = bus_number(d.read_overlay_text(col))
                    if shown != want:                                    # 누르지 않는다: finally의 leave가 미리 선택을 취소(S4)
                        return b._result(action, False, "unverified", t0, target=target, before=before,
                                         note=f"목적지 오버레이가 {d.read_overlay_text(col)!r}(기대 Bus {want}). 확정하지 않음")
                ok = d.press_vpot_until(col, lambda v: (parse_send(v.columns, send)["bus"] or 0) == want
                                        and (want == 0 or parse_send(v.columns, send)["present"]), CONFIRM_S)
                d.settle_overlay()                                       # `Send n Instantiate` 오버레이가 지나간 뒤 읽는다(S5)
                after = self._row(send)
                ok = ok and (after["bus"] or 0) == want
                if ok:
                    note = "버스 센드를 새로 만들면 Logic이 Aux 트랙을 자동 생성해 뒤 스트립 번호가 바뀔 수 있음(실측 S5)" if want else ""
                else:
                    note = f"확정 뒤 {CONFIRM_S:.0f}초 안에 목적지가 {after['text'][0]!r}(기대 {'--' if want == 0 else f'Bus {want}'})"
                return b._result(action, ok, "verified" if ok else "unverified", t0, target=target, before=before,
                                 after=after, note=note)
            except (StripUnsupported, ModeError, ValueError) as e:
                return self._fail(action, t0, target, e)
            finally:
                d.leave_safely()

    def remove(self, strip: int | None, number: int | None, send: int) -> "ToolResult":
        return self.set_dest(strip, number, send, "--")
```

`commands.py`의 `Commands.__init__` 끝(`self.plugin = …` 다음)에:

```python
        from .sends import SendCommands
        self.send = SendCommands(self)
```

- [ ] **Step 8: 통과 확인**

Run: `uv run pytest tests/test_assign_send.py tests/test_sends.py -v && uv run pytest -q`
Expected: 전부 PASS.

- [ ] **Step 9: 커밋**

```bash
git add src/logic_mcp/logic/sends.py src/logic_mcp/logic/commands.py tests/test_sends.py tests/test_assign_send.py
git commit -m "feat(send): SE 뷰 센드 get·set_dest·remove — 열 위치 해석, 버스 번호 모델, 미리 선택 확정 (실측 S2~S5)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: `SendCommands` — set_level · set_pos · mute

**Files:**
- Modify: `src/logic_mcp/logic/sends.py`, `tests/fake_assign.py` (`drop_all_vpots` 옵션)
- Test: `tests/test_assign_send.py`

**Interfaces:**
- Consumes: `setter.set_numeric(d, ch, target, Mapping("db_table"), 0.1, faders)`(Flip 페이더 → dB 표, 실측 S6), `ModeDriver.flip/fader/tick`.
- Produces: `set_level(strip, number, send, db: float)`(`-inf` 허용, +6 초과는 clamp + note), `set_pos(strip, number, send, pos: "pre"|"post"|"post_pan")`, `mute(strip, number, send, on: bool)`; action 이름 `send_set_level`·`send_set_pos`·`send_mute`; 가짜 `FakeLogic.drop_all_vpots`(V-Pot 틱을 항상 무시).

- [ ] **Step 1: 실패하는 테스트**

`tests/test_assign_send.py` 끝에:

```python
def test_set_level_uses_flip_fader_with_volume_table_and_leaves_flip_off():       # 실측 S6
    cmds, surface, fake, logic = make()
    logic.tracks[0].sends[1] = Send("Bus 1")
    r = cmds.send.set_level(strip=1, number=None, send=1, db=-6.0)
    assert r.verified == "verified" and r.action == "send_set_level" and "fader" in r.note
    assert abs(logic.tracks[0].sends[1].level - -6.0) <= 0.1 and r.after["level_db"] == -6.0 and r.before["level_db"] == -math.inf
    assert surface.state.view.kind == "pan" and not surface.state.assignment.flip and not logic.flip
    assert cmds.send.set_level(strip=1, number=None, send=1, db=-6.0).note == "already"


def test_set_level_minus_inf_and_clamp():
    cmds, surface, fake, logic = make()
    logic.tracks[0].sends[2] = Send("Bus 1", -3.0)
    r = cmds.send.set_level(strip=1, number=None, send=2, db=float("-inf"))
    assert r.verified == "verified" and r.after["level_db"] == -math.inf and logic.tracks[0].sends[2].level <= -96
    r = cmds.send.set_level(strip=1, number=None, send=2, db=9.0)
    assert r.verified == "verified" and r.after["level_db"] == 6.0 and "clamped" in r.note
    assert cmds.send.set_level(strip=1, number=None, send=2, db=float("nan")).verified == "skipped"


def test_set_level_without_send_is_skipped():
    cmds, surface, fake, logic = make()
    r = cmds.send.set_level(strip=1, number=None, send=1, db=-6.0)
    assert r.verified == "skipped" and "set_dest" in r.note and surface.state.view.kind == "pan"


def test_set_level_mode_error_still_leaves_flip_off():                              # Review Focus 3
    cmds, surface, fake, logic = make()
    logic.tracks[0].sends[1] = Send("Bus 1")
    logic.drop_all_faders = True
    logic.drop_all_vpots = True
    r = cmds.send.set_level(strip=1, number=None, send=1, db=-6.0)
    assert r.verified == "unverified"
    assert not surface.state.assignment.flip and not logic.flip and surface.state.view.kind == "pan"


def test_set_pos_and_mute():                                                         # 실측 S8·S9
    cmds, surface, fake, logic = make()
    logic.tracks[0].sends[1] = Send("Bus 1")                                          # Post Pan, active
    r = cmds.send.set_pos(strip=1, number=None, send=1, pos="pre")
    assert r.verified == "verified" and r.action == "send_set_pos" and logic.tracks[0].sends[1].pos == 0 and r.after["pos"] == "pre"
    r = cmds.send.set_pos(strip=1, number=None, send=1, pos="post")
    assert r.verified == "verified" and logic.tracks[0].sends[1].pos == 1
    assert cmds.send.set_pos(strip=1, number=None, send=1, pos="post").note == "already"
    assert cmds.send.set_pos(strip=1, number=None, send=1, pos="sideways").verified == "skipped"
    r = cmds.send.mute(strip=1, number=None, send=1, on=True)
    assert r.verified == "verified" and r.action == "send_mute" and logic.tracks[0].sends[1].muted
    assert r.after["muted"] is True and r.after["dest"] == "Bus 1" and r.after["text"][0] == "*Bus 1"
    assert cmds.send.mute(strip=1, number=None, send=1, on=True).note == "already"
    r = cmds.send.mute(strip=1, number=None, send=1, on=False)
    assert r.verified == "verified" and not logic.tracks[0].sends[1].muted
    assert cmds.send.set_pos(strip=1, number=None, send=2, pos="pre").verified == "skipped"
    assert cmds.send.mute(strip=1, number=None, send=2, on=True).verified == "skipped"
    assert surface.state.view.kind == "pan"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_assign_send.py -k "level or pos" -v`
Expected: FAIL (`set_level` 없음).

- [ ] **Step 3: 가짜 옵션**

`FakeLogic.__init__`에 `self.drop_all_vpots = False  # True면 V-Pot 틱을 항상 무시(반응 없는 Logic)`. `replies()`의 V-Pot 분기 첫 줄에 `if self.drop_all_vpots: return []`.

- [ ] **Step 4: 구현(sends.py `remove` 아래)**

```python
    def set_level(self, strip: int | None, number: int | None, send: int, db: float) -> "ToolResult":
        b, d, action = self.b, self.d, "send_set_level"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            if db != db:
                return b._result(action, False, "skipped", t0, note="db가 NaN. 예: -6.0, 0, \"-inf\"")
            ch = self._begin(action, strip, number, send, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "send": send}
            col = col_of(send, "level")
            try:
                self._fresh()
                self._channel(ch)
                self._goto_page(send)
                before = self._row(send)
                if not before["present"]:
                    return b._result(action, False, "skipped", t0, target=target,
                                     note=f"센드 {send} 없음. set_dest로 먼저 목적지를 정할 것")
                clamp = "clamped to +6.0 dB" if db > 6.0 else ""
                goal = min(db, 6.0)
                if goal == -math.inf:
                    d.flip(True)
                    d.fader(col, 1)                                        # raw 1 → `-oo dB`(실측 S6)
                    d.settle_overlay()
                    after = self._row(send)
                    ok, detail = after["level_db"] == -math.inf, ""
                else:
                    out = set_numeric(d, col, goal, Mapping("db_table"), 0.1, b.faders)   # 센드 dB 표 = 볼륨 표(실측 S6)
                    d.settle_overlay()
                    after = self._row(send)
                    ok, detail = out.ok and after["level_db"] is not None and abs(after["level_db"] - goal) <= 0.1, out.note
                    if ok and out.note == "already":
                        return b._result(action, True, "skipped", t0, target=target, before=before, after=after, note="already")
                return b._result(action, ok, "verified" if ok else "unverified", t0, target=target, before=before,
                                 after=after, note=" ".join(x for x in (clamp, detail) if x))
            except (StripUnsupported, ModeError, ValueError) as e:
                return self._fail(action, t0, target, e)
            finally:
                d.leave_safely()

    def set_pos(self, strip: int | None, number: int | None, send: int, pos: str) -> "ToolResult":
        b, d, action = self.b, self.d, "send_set_pos"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            if pos not in POS_ORDER:
                return b._result(action, False, "skipped", t0, note=f"pos는 {'|'.join(POS_ORDER)} 중 하나")
            ch = self._begin(action, strip, number, send, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "send": send}
            col = col_of(send, "pos")
            try:
                self._fresh()
                self._channel(ch)
                self._goto_page(send)
                before = self._row(send)
                if not before["present"]:
                    return b._result(action, False, "skipped", t0, target=target,
                                     note=f"센드 {send} 없음. set_dest로 먼저 목적지를 정할 것")
                cur = before["pos"]
                if cur == pos:
                    return b._result(action, True, "skipped", t0, target=target, before=before, after=before, note="already")
                if cur is None:
                    raise ModeError("pos", "Pre/Post/PosPan", before["text"][2] or "빈 열")
                after = before
                for _ in range(2):                                         # 순서 고정 Pre→Post→Post Pan(실측 S8): 차이만큼 한 번에
                    d.tick(col, POS_ORDER.index(pos) - POS_ORDER.index(cur))
                    d.settle_overlay()
                    after = self._row(send)
                    if after["pos"] == pos:
                        break
                    cur = after["pos"] or cur
                ok = after["pos"] == pos
                return b._result(action, ok, "verified" if ok else "unverified", t0, target=target, before=before,
                                 after=after, note="" if ok else f"위치가 {after['text'][2]!r}(기대 {pos})")
            except (StripUnsupported, ModeError, ValueError) as e:
                return self._fail(action, t0, target, e)
            finally:
                d.leave_safely()

    def mute(self, strip: int | None, number: int | None, send: int, on: bool) -> "ToolResult":
        b, d, action = self.b, self.d, "send_mute"
        t0 = b._now_ms()
        with b._lock:
            if (r := b._require_ready(action, t0)) is not None:
                return r
            ch = self._begin(action, strip, number, send, t0)
            if not isinstance(ch, int):
                return ch
            target = {**b._target(ch), "send": send}
            col = col_of(send, "mute")
            try:
                self._fresh()
                self._channel(ch)
                self._goto_page(send)
                before = self._row(send)
                if not before["present"]:
                    return b._result(action, False, "skipped", t0, target=target,
                                     note=f"센드 {send} 없음. set_dest로 먼저 목적지를 정할 것")
                if before["muted"] == on:
                    return b._result(action, True, "skipped", t0, target=target, before=before, after=before, note="already")
                d.tick(col, 1 if on else -1)                                # +1 = muted, -1 = active(실측 S9)
                d.settle_overlay()
                after = self._row(send)
                ok = after["muted"] == on
                return b._result(action, ok, "verified" if ok else "unverified", t0, target=target, before=before,
                                 after=after, note="" if ok else f"뮤트 열이 {after['text'][3]!r}")
            except (StripUnsupported, ModeError, ValueError) as e:
                return self._fail(action, t0, target, e)
            finally:
                d.leave_safely()
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/test_assign_send.py -v && uv run pytest -q`
Expected: 전부 PASS.

- [ ] **Step 6: 커밋**

```bash
git add src/logic_mcp/logic/sends.py tests/fake_assign.py tests/test_assign_send.py
git commit -m "feat(send): set_level(Flip 페이더, 볼륨 dB 표)·set_pos·mute (실측 S6~S9)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: MCP 도구 `logic_send`

**Files:**
- Modify: `src/logic_mcp/server/tools.py`, `README.md`(툴 표 한 줄)
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: Task 4·5 `Commands.send.*`.
- Produces: 툴 `logic_send(action: get|set_dest|set_level|set_pos|mute|remove, strip, number, send, dest, db, pos, on)`.

- [ ] **Step 1: 실패하는 테스트**

`tests/test_server.py`의 `test_tool_list_and_names`에서 기대 집합을 `{"logic_transport", "logic_track", "logic_mixer", "logic_bank", "logic_session", "logic_eq", "logic_plugin", "logic_send"}`로 바꾸고 끝에 추가:

```python
@pytest.mark.anyio
async def test_send_tool_via_client(assign_setup):
    mcp, logic = assign_setup
    async with Client(mcp) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        assert set(tools["logic_send"].input_schema["properties"]) >= {"action", "strip", "number", "send", "dest", "db", "pos", "on"}
        r = await client.call_tool("logic_send", {"action": "set_dest", "strip": 2, "send": 1, "dest": "Bus 1"})
        assert r.structured_content["verified"] == "verified" and logic.tracks[1].sends[1].dest == "Bus 1"
        r = await client.call_tool("logic_send", {"action": "set_level", "strip": 2, "send": 1, "db": "-inf"})
        assert r.structured_content["verified"] == "verified"
        r = await client.call_tool("logic_send", {"action": "set_level", "strip": 2, "send": 1, "db": -6})
        assert r.structured_content["verified"] == "verified"
        r = await client.call_tool("logic_send", {"action": "get", "strip": 2})
        assert r.structured_content["after"]["sends"]["1"]["bus"] == 1 and r.structured_content["after"]["sends"]["1"]["level_db"] == -6.0
        r = await client.call_tool("logic_send", {"action": "mute", "strip": 2})
        assert r.structured_content["verified"] == "skipped" and "send" in r.structured_content["note"]
        r = await client.call_tool("logic_send", {"action": "set_pos", "strip": 2, "send": 1})
        assert r.structured_content["verified"] == "skipped" and "pos" in r.structured_content["note"]
        r = await client.call_tool("logic_send", {"action": "remove", "strip": 2, "send": 1})
        assert r.structured_content["verified"] == "verified" and logic.tracks[1].sends[1] is None
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_server.py -v`
Expected: FAIL (`logic_send` 없음).

- [ ] **Step 3: tools.py에 추가(`logic_plugin` 아래)**

```python
    @mcp.tool(name="logic_send", annotations=ToolAnnotations(idempotent_hint=True),
              description="센드 1-8. get: 8개 전체(목적지 버스·레벨 dB·위치·뮤트). set_dest: dest는 버스 번호(\"Bus 3\"·\"3\"·3) 또는 "
                          "\"--\"(제거). set_level: db(-inf..+6.0). set_pos: pre|post|post_pan. mute: on. remove. 버스 센드를 새로 만들면 "
                          "Logic이 Aux 트랙을 자동 생성해 뒤 트랙 번호가 바뀔 수 있다. 출력·Master 스트립은 지원하지 않는다(skipped). "
                          "끝나면 PAN 모드로 돌아간다.")
    def logic_send(
        action: Literal["get", "set_dest", "set_level", "set_pos", "mute", "remove"],
        strip: Strip = None,
        number: Number = None,
        send: Annotated[int | None, Field(ge=1, le=8, description="센드 1-8")] = None,
        dest: Annotated[str | int | None, Field(description="set_dest: \"Bus 3\", \"3\", 3 또는 \"--\"")] = None,
        db: Annotated[float | Literal["-inf"] | None, Field(description="set_level: dB. 문자열 \"-inf\" 허용")] = None,
        pos: Literal["pre", "post", "post_pan"] | None = None,
        on: Annotated[bool | None, Field(description="mute: true=뮤트")] = None,
    ) -> ToolResult:
        name = f"send_{action}"
        if action == "get":
            return commands.send.get(strip, number)
        if send is None:
            return ToolResult(ok=False, verified="skipped", action=name, note="send(1-8)가 필요")
        if action == "set_dest":
            if dest is None:
                return ToolResult(ok=False, verified="skipped", action=name, note="set_dest에는 dest가 필요(버스 번호 또는 \"--\")")
            return commands.send.set_dest(strip, number, send, dest)
        if action == "remove":
            return commands.send.remove(strip, number, send)
        if action == "set_level":
            if db is None:
                return ToolResult(ok=False, verified="skipped", action=name, note="set_level에는 db가 필요. 예: -6.0, 0, \"-inf\"")
            return commands.send.set_level(strip, number, send, -math.inf if db == "-inf" else float(db))
        if action == "set_pos":
            if pos is None:
                return ToolResult(ok=False, verified="skipped", action=name, note="set_pos에는 pos(pre|post|post_pan)가 필요")
            return commands.send.set_pos(strip, number, send, pos)
        if on is None:
            return ToolResult(ok=False, verified="skipped", action=name, note="mute에는 on(true/false)이 필요")
        return commands.send.mute(strip, number, send, on)
```

README 툴 표에 `| `logic_send` | 센드 1~8의 목적지(버스)·레벨·위치·뮤트 읽기·쓰기 |` 한 줄.

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest -q`
Expected: 전부 PASS.

- [ ] **Step 5: 커밋**

```bash
git add src/logic_mcp/server/tools.py tests/test_server.py README.md
git commit -m "feat(server): logic_send 도구

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: 캐시 저장 규칙(리뷰 m4)과 번들 병합 헬퍼

**Files:**
- Modify: `src/logic_mcp/logic/plugins/cache.py`
- Test: `tests/test_plugins.py`

**Interfaces:**
- Consumes: 기존 `PluginCache` 필드(위치 인자 7개는 그대로 — 테스트가 `PluginCache("fake", list, [], {}, {}, None, path)`로 만든다).
- Produces: 필드 `bundled_abbrev`, `bundled_params`, `bundled_generated`(기본값 있음); `save()`는 번들과 **다른** 항목만 사용자 파일에 쓴다(`abbrev`·`params`), `bundled_generated` 기록; `merge_bundled(bundled: Path, name: str, table: dict, generated: str) -> dict`.

- [ ] **Step 1: 실패하는 테스트**

`tests/test_plugins.py` 끝에:

```python
def test_save_writes_only_entries_that_differ_from_bundle(tmp_path):          # 리뷰 m4
    bundled = tmp_path / "known.json"
    bundled.write_text(json.dumps({"logic_version": "12.0.1", "generated": "2026-10-15", "list": ["--", "Compressor", "Channel EQ"],
                                   "abbrev": {"Cha EQ": "Channel EQ"}, "params": {"Channel EQ": {"pages": 6, "items": []}}}))
    c = PluginCache.load(version="12.0.1", user_dir=tmp_path, bundled=bundled)
    c.learn_abbrev("Comprs", "Compressor")
    c.params["Compressor"] = {"pages": 3, "items": [{"index": 2, "short": "Thrs", "name": None, "map": None}]}
    c.save()
    saved = json.loads(c.path.read_text())
    assert saved["abbrev"] == {"Comprs": "Compressor"} and list(saved["params"]) == ["Compressor"]
    assert saved["bundled_generated"] == "2026-10-15"
    bundled.write_text(bundled.read_text().replace('"pages": 6', '"pages": 7'))        # 번들이 갱신돼도
    c2 = PluginCache.load(version="12.0.1", user_dir=tmp_path, bundled=bundled)
    assert c2.param_table("Channel EQ")["pages"] == 7                                    # 사용자 파일이 가리지 않는다
    assert c2.param_table("Compressor")["pages"] == 3 and c2.abbrev["Cha EQ"] == "Channel EQ"
    c2.params["Channel EQ"]["pages"] = 9                                                 # 번들 항목을 고치면 그 항목만 사용자 파일에
    c2.save()
    assert set(json.loads(c2.path.read_text())["params"]) == {"Compressor", "Channel EQ"}
    c3 = PluginCache.load(version="12.0.1", user_dir=tmp_path, bundled=bundled)
    assert c3.bundled_params["Channel EQ"]["pages"] == 7 and c3.param_table("Channel EQ")["pages"] == 9


def test_merge_bundled_replaces_table_and_generated(tmp_path):
    from logic_mcp.logic.plugins.cache import merge_bundled
    bundled = tmp_path / "known.json"
    bundled.write_text(json.dumps({"logic_version": "12.0.1", "generated": "2026-10-15", "list": ["--"], "abbrev": {},
                                   "params": {"A": {"pages": 1, "items": []}}}))
    table = {"pages": 2, "items": [{"index": 1, "short": "X", "name": "X", "map": None}]}
    data = merge_bundled(bundled, "B", table, "2026-10-17")
    assert data["params"]["B"] == table and data["params"]["A"]["pages"] == 1 and data["generated"] == "2026-10-17"
    assert json.loads(bundled.read_text()) == data and not list(tmp_path.glob("*.tmp"))
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_plugins.py -v`
Expected: FAIL (`bundled_generated` 없음 / `merge_bundled` 없음).

- [ ] **Step 3: cache.py 수정**

임포트에 `import copy`와 `from dataclasses import dataclass, field`. 데이터클래스 필드 끝에:

```python
    bundled_abbrev: dict[str, str] = field(default_factory=dict)     # 저장 때 번들과 같은 항목을 빼기 위한 기준(리뷰 m4)
    bundled_params: dict[str, dict] = field(default_factory=dict)
    bundled_generated: str | None = None
```

`load`를 다음으로 바꾼다:

```python
    @classmethod
    def load(cls, version: str | None = None, user_dir: Path = USER_DIR, bundled: Path = BUNDLED) -> "PluginCache":
        version = version or logic_version()
        b = json.loads(bundled.read_text())
        path = user_dir / f"plugins-{version}.json"
        u = cls._read_user(path)
        b_abbrev, b_params = dict(b.get("abbrev", {})), copy.deepcopy(b.get("params", {}))
        return cls(version=version, bundled_list=list(b.get("list", [])), user_list=list(u.get("list", [])),
                   abbrev={**b_abbrev, **u.get("abbrev", {})},
                   params={**copy.deepcopy(b_params), **u.get("params", {})},
                   scanned_at=u.get("scanned_at"), path=path,
                   bundled_abbrev=b_abbrev, bundled_params=b_params, bundled_generated=b.get("generated"))
```

`save`의 `json.dumps(...)` 인자를 다음으로 바꾼다(번들과 같은 항목은 쓰지 않는다 — 번들을 고쳐도 사용자에게 반영되도록, 리뷰 m4):

```python
        abbrev = {k: v for k, v in self.abbrev.items() if self.bundled_abbrev.get(k) != v}
        params = {k: v for k, v in self.params.items() if self.bundled_params.get(k) != v}
        tmp.write_text(json.dumps({"logic_version": self.version, "bundled_generated": self.bundled_generated,
                                   "scanned_at": self.scanned_at, "list": self.user_list, "abbrev": abbrev, "params": params},
                                  ensure_ascii=False, indent=1))
```

모듈 끝에:

```python
def merge_bundled(bundled: Path, name: str, table: dict, generated: str) -> dict:
    """calibrate 결과 표를 번들 known.json에 넣고(같은 이름은 교체) generated를 갱신해 저장한다. 저장한 전체 dict를 돌려준다."""
    data = json.loads(bundled.read_text())
    data.setdefault("params", {})[name] = table
    data["generated"] = generated
    tmp = bundled.with_name(bundled.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    os.replace(tmp, bundled)
    return data
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_plugins.py tests/test_assign_plugin.py -q`
Expected: 전부 PASS(기존 `test_cache_merges_bundled_and_user`는 사용자 파일에 번들 축약이 안 들어가도 `c2.abbrev["Cha EQ"]`가 번들에서 오므로 그대로 통과).

- [ ] **Step 5: 커밋**

```bash
git add src/logic_mcp/logic/plugins/cache.py tests/test_plugins.py
git commit -m "fix(cache): 사용자 파일에는 번들과 다른 항목만 저장, merge_bundled 헬퍼 (리뷰 m4)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: 플러그인 캘리브레이션 — `PluginCommands.calibrate`와 `scripts/calibrate_plugin.py`

**Files:**
- Modify: `src/logic_mcp/logic/assign.py` (`calibrate`, `MAX_OPTIONS`), `src/logic_mcp/logic/values.py` (`:1` 단위)
- Create: `scripts/calibrate_plugin.py`
- Test: `tests/test_values.py`, `tests/test_calibrate.py` (신규)

**Interfaces:**
- Consumes: `_open_edit`·`_read_pages`·`_merge_items`·`_goto_param`·`probe_mapping`·`_map_to`, Task 7 `merge_bundled`.
- Produces: `PluginCommands.calibrate(strip, number, slot) -> ToolResult`(`after={"plugin", "pages", "items", "probed", "enums"}`; 캐시에 저장). 값을 움직이고 되돌리지 않으므로(끝 값에서 ±1 틱은 비대칭) **스크립트가 삽입한 임시 인스턴스에만** 쓴다. `parse_value("2.1:1")` → number 2.1, unit `:1`.

- [ ] **Step 1: 실패하는 테스트**

`tests/test_values.py` 끝에:

```python
def test_parse_value_ratio_unit():                                    # Compressor Ratio `2.1:1`(실측 M)
    v = parse_value("2.1:1")
    assert v.kind == "number" and v.number == 2.1 and v.unit == ":1"
```

`tests/test_calibrate.py`:

```python
from logic_mcp.logic.commands import Commands
from logic_mcp.logic.faders import FaderTable
from logic_mcp.logic.plugins.cache import PluginCache
from tests.fake_assign import PLUGIN_LIST, make_assign_logic


def make(tmp_path):
    surface, fake, logic = make_assign_logic()
    cache = PluginCache("fake", list(PLUGIN_LIST), [], {}, {}, None, tmp_path / "plugins-fake.json")
    cmds = Commands(surface, FaderTable.load(), sleep=logic.sleep, logic_running=lambda: True, plugin_cache=cache)
    return cmds, surface, fake, logic, cache


def test_calibrate_collects_names_maps_and_options(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    logic.tracks[0].insert(2, "Compressor")
    r = cmds.plugin.calibrate(strip=1, number=None, slot=2)
    assert r.verified == "verified" and r.after["plugin"] == "Compressor" and r.after["pages"] == 3
    items = {it["index"]: it for it in r.after["items"]}
    assert len(items) == 20 and all(it["name"] for it in items.values())
    assert items[2]["name"] == "Threshold" and items[2]["map"]["type"] == "linear"
    assert abs(items[2]["map"]["lo"] - -60.0) < 0.5 and abs(items[2]["map"]["hi"] - 0.0) < 0.5
    assert items[3]["map"]["type"] == "linear" and abs(items[3]["map"]["lo"] - 1.0) < 0.1          # Ratio `2.1:1`
    assert items[1] == {"index": 1, "short": "CirTyp", "name": "Circuit Type",
                        "map": {"type": "enum", "options": ["PltDig", "StdVCA", "StdFET", "ClsVCA"]}}
    assert items[6]["map"] == {"type": "enum", "options": ["Off", "On"]}                           # 시작값 On이어도 처음부터
    assert items[8]["map"] is None                                                                 # AutGai: `Off`/`-12dB`/`0dB` 혼합은 매핑 못 함
    assert r.after["enums"] == 8 and r.after["probed"] >= 10
    assert cache.param_table("Compressor")["items"][1]["name"] == "Threshold" and cache.path.exists()
    assert surface.state.view.kind == "pan" and not surface.state.assignment.flip and logic.name_mode is False


def test_calibrate_on_empty_slot_is_skipped(tmp_path):
    cmds, surface, fake, logic, cache = make(tmp_path)
    r = cmds.plugin.calibrate(strip=1, number=None, slot=3)
    assert r.verified == "skipped" and "비어" in r.note and surface.state.view.kind == "pan"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_values.py tests/test_calibrate.py -v`
Expected: FAIL.

- [ ] **Step 3: values.py — `:1` 단위**

`_NUM_RE`를 `re.compile(r"^\s*([+-]?\d+(?:\.\d+)?|-oo)\s*([A-Za-z/%:0-9]*)\s*$")`로, `_UNITS`에 `":1": ":1"`을 더한다(앞 토큰이 숫자이므로 `2.1:1`은 숫자 2.1 + 단위 `:1`). `tests/test_values.py`의 기존 테스트가 모두 통과하는지 확인한다(단위 문자 집합이 넓어져도 `20.0Hz`·`-oo dB`·`36 dB/Oct`는 그대로).

- [ ] **Step 4: assign.py — calibrate**

`MAX_SLOT` 옆에 `MAX_OPTIONS = 16   # 열거형 선택지 수집 상한(캘리브레이션)`. `PluginCommands.scan` 앞에:

```python
    def calibrate(self, strip: int | None, number: int | None, slot: int) -> "ToolResult":
        """편집 뷰에서 파라미터마다 전체 이름(틱 오버레이 1행), 숫자 매핑(Flip 페이더 프로빙), 열거형 선택지(-1로 처음까지 간 뒤
        +1로 끝까지, 정착 열 텍스트)를 모아 캐시에 저장한다. 값을 바꾸고 되돌리지 않는다 → scripts/calibrate_plugin.py가
        삽입한 임시 인스턴스에만 쓴다."""
        b, d, action = self.b, self.d, "plugin_calibrate"
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
                full, _abbrev, pages = self._open_edit(ch, slot)
                self._merge_items(full, pages, self._read_pages(pages))
                table = self._table(full, pages)
                probed = enums = 0
                for item in table["items"]:
                    col = self._goto_param(item)                                   # VALUE 모드
                    v = d.read_column(col)[1]
                    if v.kind == "enum":
                        last = v.text
                        for _ in range(MAX_OPTIONS):                               # 처음(가장 앞 선택지)까지 -1
                            d.tick(col, -1)
                            name = d.read_overlay_name(col)
                            d.settle_overlay()
                            t = d.read_column(col)[1].text
                            if t == last:
                                break
                            last = t
                        options = [last]
                        for _ in range(MAX_OPTIONS - 1):                           # +1로 끝까지 모은다
                            d.tick(col, 1)
                            d.settle_overlay()
                            t = d.read_column(col)[1].text
                            if t == options[-1]:
                                break
                            options.append(t)
                        item["map"] = {"type": "enum", "options": options}
                        enums += 1
                    else:
                        d.tick(col, 1)
                        name = d.read_overlay_name(col)
                        d.tick(col, -1)
                        d.settle_overlay()
                        if v.kind == "number" and not item.get("map"):
                            d.flip(True)
                            mapping, _lo, _hi = probe_mapping(d, col)              # 페이더 1·16383 → 범위(실측 X: 에코 뒤 LCD까지 대기)
                            if mapping is not None:
                                item["map"] = _map_to(mapping)
                                probed += 1
                    if name and "Page" not in name:
                        item["name"] = name
                    d.toggle_name_value()                                           # NAME 모드로 복귀(다음 page_to가 헤더를 읽는다)
                self.cache.save()
                return b._result(action, True, "verified", t0, target=target,
                                 after={"plugin": full, "pages": pages, "items": table["items"], "probed": probed, "enums": enums})
            except SlotEmpty:
                return b._result(action, False, "skipped", t0, target=target, note=f"슬롯 {slot}이 비어 있음")
            except StripUnsupported as e:
                return b._result(action, False, "skipped", t0, target=target, note=e.note)
            except ModeError as e:
                return b._result(action, False, "unverified", t0, target=target, note=str(e))
            except ValueError as e:
                return b._result(action, False, "skipped", t0, target=target, note=f"값 오류: {e}")
            finally:
                d.leave_safely()
```

- [ ] **Step 5: 스크립트 `scripts/calibrate_plugin.py`**

```python
"""번들 파라미터 표 만들기(스펙 §6.1). 테스트 프로젝트(저장 안 함)의 strip 빈 슬롯에 플러그인을 넣고 calibrate → 제거.
--write면 src/logic_mcp/logic/plugins/known.json에 합친다.
사용: uv run python scripts/calibrate_plugin.py "Channel EQ" [strip=1] [--write]"""
import sys
from datetime import date

from logic_mcp.logic.plugins.cache import BUNDLED, merge_bundled
from logic_mcp.server.main import build

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if not args:
    sys.exit(__doc__)
name = args[0]
strip = int(args[1]) if len(args) > 1 else 1
commands, surface = build()
surface.start()
try:
    print("ready:", commands.wait_ready(60).after["state"], "configure:", commands.configure().note)
    inv = commands.plugin.list(strip, None)
    row = next(iter(inv.after["tracks"].values())) if inv.ok and inv.after else None
    slot = next((int(s) for s, v in (row or {}).items() if v is None), None)
    if slot is None:
        sys.exit(f"스트립 {strip}에 빈 슬롯 없음: {inv.note}")
    r = commands.plugin.insert(strip, None, slot, name)
    print(f"insert {name} → 슬롯 {slot}:", r.verified, r.note)
    if not r.ok:
        sys.exit(1)
    full = r.after["plugin"]
    r = commands.plugin.calibrate(strip, None, slot)
    print("calibrate:", r.verified, r.note)
    for it in (r.after or {}).get("items", []):
        print(f"  {it['index']:3} {it['short']:7} {str(it.get('name')):28} {it.get('map')}")
    print("remove:", commands.plugin.remove(strip, None, slot).verified)
    if r.ok and "--write" in sys.argv:
        merge_bundled(BUNDLED, full, commands.plugin.cache.param_table(full), date.today().isoformat())
        print("known.json 갱신:", full)
finally:
    surface.stop()
```

- [ ] **Step 6: 통과 확인**

Run: `uv run pytest -q`
Expected: 전부 PASS.

- [ ] **Step 7: 커밋**

```bash
git add src/logic_mcp/logic/assign.py src/logic_mcp/logic/values.py scripts/calibrate_plugin.py tests/test_values.py tests/test_calibrate.py
git commit -m "feat(plugin): calibrate — 편집 뷰에서 이름·매핑·선택지 수집, calibrate_plugin.py가 known.json에 병합

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: 스킬·README·실기 스크립트·스펙 보정·진행 기록

**Files:**
- Create: `skills/logic-plugins/SKILL.md`
- Modify: `README.md`, `scripts/live_check2.py`, `docs/superpowers/specs/2026-10-15-logic-mcp-assign-design.md`, `docs/progress.md`

**Interfaces:**
- Consumes: Task 1~8 전부.
- Produces: 문서만. 테스트 없음(`uv run pytest -q` 녹색 유지).

- [ ] **Step 1: 스킬 파일**

`skills/logic-plugins/SKILL.md`:

```markdown
---
name: logic-plugins
description: Logic Pro MCP(logic-mcp)로 Channel EQ·인서트 플러그인·센드를 다룰 때의 순서와 함정. logic_eq·logic_plugin·logic_send를 쓰기 전에 읽는다.
---

# Logic Pro 플러그인·EQ·센드 조작 (logic-mcp)

## 시작할 때
1. `logic_session wait_ready` → `logic_session configure`(처음 한 번. Logic이 서피스를 다시 설치한 뒤에도 한 번 더).
2. `logic://plugins` 리소스를 읽는다. `scanned_at`이 없거나 `logic_version`이 다르면 `logic_plugin scan`을 권한다(30~90초, 빈 슬롯 1개 필요, 화면의 슬롯이 깜박이지만 삽입은 없음).

## 플러그인
- `insert`가 "목록에 없음"이면 `scan` 뒤 다시. 차 있는 슬롯은 `replace=true`가 있어야 바꾼다.
- `params`를 먼저 읽고 `short`(축약명)나 `index`로 `get`/`set`. 마지막 페이지는 index가 건너뛸 수 있으니 params가 준 index를 그대로 쓴다.
- 서드파티가 이름 없이 `Control #N`(0~1000)만 주면 index로 다루고 값은 0~1000 정수.
- 인서트 슬롯은 1~8만.

## EQ
- `logic_eq get`은 삽입하지 않는다. `set`은 EQ가 없으면 `allow_insert`(기본 true)에 따라 Channel EQ를 넣는다. 밴드 1·8은 gain 대신 slope(6/12/18/24/36/48).

## 센드
- `logic_send set_dest`의 dest는 버스 번호("Bus 3", "3", 3) 또는 "--"(제거). 버스 센드를 새로 만들면 Logic이 Aux 트랙을 자동 생성해 **뒤 트랙 번호가 바뀐다** → 이어서 number로 부르기 전에 `logic://strips`를 다시 읽는다.
- 레벨은 dB(-inf..+6.0), 위치 pre|post|post_pan, 뮤트는 on. 센드가 없는 번호에 레벨·위치·뮤트는 skipped.

## 지원하지 않는 것
- 출력(Stereo Out)·Master 스트립: EQ 채널·플러그인·센드 명령은 `skipped`(Logic의 채널 뷰가 그 스트립을 따라가지 않아 엉뚱한 트랙을 바꾸게 된다). `eq get`은 EQ 유무만 알려 준다.
- 인서트 슬롯 9~15, 악기·MIDI FX 슬롯, 서라운드, 버스가 아닌 센드 목적지.

## 안전
- 모든 명령은 끝나면 PAN 모드·Flip 꺼짐으로 돌아온다. `verified`가 아니면 결과를 믿지 말고 `note`를 읽는다.
- 스펙 1 도구(`logic_track` mute/solo/select, `logic_transport`, `logic_bank`)는 어사인먼트 뷰 중에도 안전하다. `logic_mixer`의 set_volume·set_pan은 스스로 PAN으로 돌아간 뒤 실행한다.
- Logic을 다시 켠 뒤 EQ·플러그인·센드 명령이 전부 `unverified`("버튼 반응 없음")이면 Logic Pro → 설정 → 컨트롤 서피스 → 설정…에서 **Mackie Control 장치를 지우고** 다시 연결하도록 사용자에게 안내한다(MPK 등 다른 장치는 건드리지 않음, "기본값 재형성"은 누르지 않음).
```

- [ ] **Step 2: README**

설치 절에 5번: `5. 스킬을 복사한다: \`cp -R skills/logic-plugins ~/.claude/skills/\``. 툴 표 아래 제약 문단을 다음으로 바꾼다:

```markdown
인서트 슬롯은 1~8, 센드는 1~8만 지원한다. 출력(Stereo Out)·Master 스트립은 EQ 채널·플러그인·센드 명령을 받지 않는다(Logic의 채널 뷰가 그 스트립을 따라가지 않음, `docs/mcu-protocol.md` Z4).

플러그인 목록은 번들(Logic 12.0.1 내장) + `logic_plugin scan`(사용자 캐시 `~/.logic-mcp/plugins-<버전>.json`)으로 이뤄진다. 번들 파라미터 표는 `uv run python scripts/calibrate_plugin.py "<플러그인>" [strip] --write`로 만든다(테스트 프로젝트에서).

부작용: EQ·플러그인·센드 명령은 Logic의 트랙 선택을 바꾸고, 트랙에 Channel EQ가 없으면 EQ 명령이 자동으로 삽입하며, 플러그인 창이 열릴 수 있다. 버스 센드를 새로 만들면 Logic이 Aux 트랙을 자동 생성해 뒤 트랙 번호가 바뀐다.
```

- [ ] **Step 3: live_check2.py 센드 단계**

`plugin remove s1 (Channel EQ)` 줄 뒤, `if "--scan"` 앞에:

```python
    r = run("send get (before)", lambda: commands.send.get(strip, None))
    run("send set_dest Bus 1 s1", lambda: commands.send.set_dest(strip, None, 1, "Bus 1"))      # Aux 자동 생성 → 뒤 번호 밀림(S5)
    run("send set_level -6 s1", lambda: commands.send.set_level(strip, None, 1, -6.0))
    run("send set_level -inf s1", lambda: commands.send.set_level(strip, None, 1, float("-inf")))
    run("send set_pos pre s1", lambda: commands.send.set_pos(strip, None, 1, "pre"))
    run("send mute on s1", lambda: commands.send.mute(strip, None, 1, True))
    run("send mute off s1", lambda: commands.send.mute(strip, None, 1, False))
    r = run("send get (after)", lambda: commands.send.get(strip, None))
    print("  send 1:", r.after and r.after["sends"]["1"])
    run("send remove s1", lambda: commands.send.remove(strip, None, 1))
    outs = [s.number for s in commands.surface.state.strips if s.number is not None and s.name.startswith(("St", "Mas"))]
    if outs:                                                                                   # 출력 스트립 가드(Z4): skipped 기대
        run(f"plugin list #{outs[0]} (출력, skipped 기대)", lambda: commands.plugin.list(None, outs[0]))
        run(f"send get #{outs[0]} (출력, skipped 기대)", lambda: commands.send.get(None, outs[0]))
```

- [ ] **Step 4: 스펙 보정 반영**

`docs/superpowers/specs/2026-10-15-logic-mcp-assign-design.md`:
- §4.3 표 바로 아래에 `**보정(2026-10-16 실측 S1~S11, 계획 2b):** SE 뷰 Flip 페이더로 레벨 확정(D1 경로 없음, dB 표 = 볼륨 표). 목적지는 버스 번호 모델(\`--\`로 되감고 \`번호+2\` 틱 → 오버레이 \`Bus m\` 보정 → 누름). pos는 Pre→Post→Post Pan 순서 고정, mute는 +1/-1. 버스 센드 확정 시 Aux 트랙 자동 생성.` 문단 추가.
- §6.3 제목 뒤에 `(2b 보정: 삭제 — 목적지는 버스 번호로 지정, 스캔 없음)` 추가.
- §7 목록 끝에 `- **출력·Master 스트립 미지원**: PL·SE·EQ 채널 뷰가 따라가지 않아(실측 Z4) 그 스트립 대상 명령은 skipped. 판별은 TRACK 모드 홀드 메뉴 Output 열(실측 Z5).` 추가.
- §8의 `센드 dB 표는 \`scripts/calibrate_send.py\`로 …` 문장을 `센드 dB 표는 볼륨 표와 같다(실측 S6, calibrate_send 불필요). 번들 파라미터 표는 \`scripts/calibrate_plugin.py\`.`로 바꾼다.

- [ ] **Step 5: progress.md**

`- 다음: 2b (수정 8 · 센드 · 번들 생성 · 스킬)` 줄을 지우고 끝에 절을 더한다:

```markdown
## 스펙 2b
- Task 1~9 완료 표시 자리(컨트롤러가 채움).
- 실기 결과 자리: `scripts/live_check2.py <strip>`(센드 단계 포함), 출력 스트립 skipped 확인, `scripts/calibrate_plugin.py` 10종(Channel EQ, Compressor, Limiter, Noise Gate, Tape Delay, Stereo Delay, Space Designer, ChromaVerb, Overdrive, Distortion) 수집 결과.
- 미검증 경로 자리.
- 다음: 스펙 3(공개 준비: GitHub 원격, 설치 문서, 악기 슬롯 검토).
```

- [ ] **Step 6: 확인과 커밋**

Run: `uv run pytest -q && test -f skills/logic-plugins/SKILL.md && uv run python -c "import ast; ast.parse(open('scripts/live_check2.py').read())"`
Expected: 테스트 전부 PASS, 파일 존재, 구문 OK.

```bash
git add skills/logic-plugins/SKILL.md README.md scripts/live_check2.py docs/superpowers/specs/2026-10-15-logic-mcp-assign-design.md docs/progress.md
git commit -m "docs: logic-plugins 스킬, README 2b, live_check2 센드 단계, 스펙 보정(2026-10-16 실측), progress 2b

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## 계획 밖(실기 세션, 컨트롤러 담당)

1. `uv run python scripts/live_check2.py <strip>` — 센드 7단계·출력 스트립 skipped 확인. 결과를 `docs/progress.md` "스펙 2b"에 기록(실기 10차).
2. `uv run python scripts/calibrate_plugin.py "<이름>" <strip> --write` ×10종 → `known.json` 커밋. 각 ~2~4분.
3. 실측 추가분(Z8~, S12~)은 `docs/mcu-protocol.md`에.
