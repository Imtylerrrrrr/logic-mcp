# Field Fixes (Spec 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `logic_plugin` insert by name when the cached list disagrees with Logic, refuse Aux strips before pressing (Z19) while still allowing slot-1 insert/remove on them via the Plug-in Mixer view, loosen numeric set tolerances, and add `plugin move` (remove + reinsert).

**Architecture:** All MCU interaction stays in `ModeDriver`/`plugins/scan.py` helpers; `PluginCommands` composes them inside `_guarded`. Strip classification moves from a bool (`follows`) to a three-way kind read from the TRACK hold menu (Output + Input columns). Tests run against the fake Logic in `tests/fake_assign.py`.

**Tech Stack:** Python ≥3.12, `mcp` 2.3.0, python-rtmidi, pytest (`uv run pytest -q`).

**Spec:** `docs/superpowers/specs/2026-10-27-field-fixes-design.md` (Korean). Field evidence: `docs/progress.md` "실전 사용 교훈 (2026-10-24)".

## Global Constraints
- MIDI only; never press a V-Pot to confirm a pre-selection unless the overlay name was read and matched first (spec 반목표).
- Code `ToolResult.note` strings stay Korean (tests assert them); tool `description=` text and CHANGELOG are English (repo rule).
- Never weaken an existing test; when a default changes, update the expected number only.
- Commit per task on branch `feat/field-fixes`; message ends with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Run `uv run pytest -q` before each commit; all tests green (295 at start).

## Review Focus
1. Name scan that never finds the name must stop (stale limit or wrap to `--`) and must not press — Task 1 test `test_insert_name_scan_gives_up_without_pressing`.
2. Aux strip with slot 1 already occupied: `insert` must be skipped, not overwrite — Task 3 test `test_aux_insert_slot1_occupied_is_skipped`.
3. `move` when the reinsert fails after a successful remove must report unverified with the plug-in name so the user can reinsert — Task 5 test `test_move_reports_when_reinsert_fails`.
4. Strip whose Input column is blank but Output is present (software instrument) must stay `track` — Task 2 test `test_read_strip_kinds_three_kinds`.
5. Tolerance override by the caller must still win over the new defaults — Task 4 test `test_tolerance_argument_overrides_default`.

---

### Task 1: `seek_by_name` and insert name-scan fallback

**Files:**
- Modify: `src/logic_mcp/logic/plugins/scan.py`
- Modify: `src/logic_mcp/logic/plugin.py:396-453` (`PluginCommands.insert`)
- Test: `tests/test_assign_plugin.py`

**Interfaces:**
- Produces: `seek_by_name(d: ModeDriver, ch: int, want: str, prefix: bool = False) -> tuple[bool, int, str]` — `(found, ticks, last_text)`. Starts with `rewind_to_empty(d, ch)`, advances `SCAN_STEP` ticks at a time reading `strip_suffix(d.read_overlay_text(ch))`; match = `normalize(text) == normalize(want)` (or `normalize(text).startswith(normalize(want))` when `prefix`), re-read after `d.pause(0.4)` must still match; stops on `STALE_LIMIT` unchanged reads, `MAX_ITEMS * ITEM_TICKS` ticks, or `text == "--"` after the first 4 ticks. Leaves the matched item pre-selected (caller presses or leaves).
- `insert` result `note`: `""` on cache-position hit, `"name_scan:<ticks>"` on fallback hit; `after.plugin` is the full name found.

- [ ] **Step 1: Write failing tests** in `tests/test_assign_plugin.py`:
  - `test_insert_falls_back_to_name_scan_when_cache_order_differs`: build cache list = fake `PLUGIN_LIST` with two items swapped so cached index of `"Channel EQ"` points at another name; `commands.plugin.insert(1, None, 4, "Channel EQ")` → `r.ok and r.verified == "verified"`, `r.note.startswith("name_scan:")`, fake track inserts[4] == "Channel EQ".
  - `test_insert_name_scan_gives_up_without_pressing`: name present in cache but absent from fake `plugin_list`; result `verified == "unverified"`, note contains `"이름 탐색"` and `"scan"`, no `VPOT_PUSH` sent after the rewind (inspect `fake.sent`), track slot still empty.
  - `test_insert_unknown_name_uses_prefix_scan`: cache list lacks `"Tape Delay"`; `insert(1, None, 4, "Tape De")` → verified, `after["plugin"] == "Tape Delay"`.
  - keep `test_insert_unknown_or_ambiguous_name_sends_nothing` passing: ambiguous (2+ cache candidates) is still skipped; the "unknown" half of that test moves to the prefix-scan test above.
- [ ] **Step 2: Run** `uv run pytest tests/test_assign_plugin.py -q -k "name_scan or prefix_scan"` → FAIL (ImportError / wrong verified).
- [ ] **Step 3: Implement `seek_by_name` in `scan.py`** (reuse `rewind_to_empty`, `SCAN_STEP`, `STALE_LIMIT`, `MAX_ITEMS`, `ITEM_TICKS`; export it from the module).
- [ ] **Step 4: Wire into `insert`**: after the existing 3-round nudge still mismatches, call `seek_by_name(d, v, want)`; on `found` continue to the existing `press_vpot_until` + header check with `note=f"name_scan:{ticks}"`; else `unverified` with note `f"이름 탐색 {ticks}틱 뒤에도 {want!r} 못 찾음(마지막 {last!r}). 설치 목록이 다른 듯. `logic_plugin scan` 권장"`. When `find()` returns `(None, [])`, skip the cache path and call `seek_by_name(d, v, plugin, prefix=True)`; the full name is `strip_suffix(d.read_overlay_text(v))` at the match. The `_result(...)` note for success must be the string above (tests check prefix).
- [ ] **Step 5: Run** `uv run pytest -q` → all green.
- [ ] **Step 6: Commit** `feat: insert falls back to scanning the plug-in list by name`.

### Task 2: Strip kinds via Input column (Z19)

**Files:**
- Modify: `src/logic_mcp/logic/modes.py:36-37,370-385` (add `TRACK_MENU_INPUT = (3, "Input")`, `read_strip_kinds()`)
- Modify: `src/logic_mcp/logic/strips.py`
- Modify: `tests/fake_assign.py` (Track gets `kind="aux"` support: Input column `"Bus N"` for aux, `"1"` for track, `""` for output/master/instrument; `cs_param == 3` renders it)
- Modify: `docs/mcu-protocol.md` (append `Z19`)
- Test: `tests/test_strips.py`, `tests/test_modes.py`

**Interfaces:**
- Produces: `StripKind = Literal["track", "aux", "output"]` in `strips.py`; `ModeDriver.read_strip_kinds() -> list[StripKind]` (one Input read + one Output read, Volume restored, same `_cs_dirty` discipline and ModeError rules as `read_strip_outputs`); `StripKinds.kind(d, state, ch) -> StripKind`; `StripKinds.follows(...)` keeps returning `kind != "output"`; `StripKinds.cache: dict[tuple[int | None, str], StripKind]`; new exception `StripAux(ch, number, name)` with `.note` = `f"스트립 {ch + 1}(번호 {number}, {name!r})은 Aux 채널 스트립이라 채널 뷰(PL·SE·EQ)가 따라가지 않음(실측 Z19). 플러그인은 슬롯 1 삽입·제거만 Plug-in Mixer 뷰로 지원"`.
- Consumed by Task 3.

- [ ] **Step 1: Write failing tests**:
  - `tests/test_modes.py::test_read_strip_kinds_three_kinds`: tracks `[Track(1,"1"), Track(2,"Inst", input_blank=True), Track(5,"Aux1", kind="aux"), Track(3,"StOu", kind="output")]` → `["track","track","aux","output", ...]`, and afterwards `logic.cs_param == 0`, view `pan`.
  - `tests/test_strips.py`: update `test_strip_kinds_fills_cache_for_all_named_strips_once` expected cache to kinds (`"track"`, `"output"`, `"output"`), add `test_strip_kinds_aux_is_cached_and_follows_is_true` (aux → `follows` True, `kind == "aux"`), keep the no-number and read-fails tests (adapt the SimpleNamespace fake to provide `read_strip_kinds`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `TRACK_MENU_INPUT`, `read_strip_kinds` (Input first, then Output, both via `track_param`; classify per spec: Output blank → `output`; Input starts with `"Bus"` → `aux`; else `track`), `StripKind`, `StripAux`, `StripKinds.kind`, and the fake's Input column.
- [ ] **Step 4: Append Z19 to `docs/mcu-protocol.md`** with the 2026-10-27 measurement: Input row `['1', '1', 'Bus 1', 'Bus 2', '', '', '', '']`, Volume restore, Output `St Out` for both tracks and Aux.
- [ ] **Step 5: Run** `uv run pytest -q` → green. **Commit** `feat: classify strips as track/aux/output from the TRACK Input column (Z19)`.

### Task 3: Aux handling in plugin commands (Mixer-view slot 1)

**Files:**
- Modify: `src/logic_mcp/logic/commands.py:129-137` (`_channel`), `:147-163` (`_guarded`)
- Modify: `src/logic_mcp/logic/plugin.py` (`list`, `insert`, `remove`)
- Modify: `src/logic_mcp/server/tools.py:92-97` (description)
- Modify: `tests/fake_assign.py` (aux track: PL/SE/EQ keep showing the previously followed track; `plugin_mixer` row shows slot 1 of every strip; a V-Pot push in `plugin_mixer` confirms the pre-selection for that strip and opens the *selected* track's edit view)
- Test: `tests/test_assign_plugin.py`

**Interfaces:**
- Consumes: `StripKinds.kind`, `StripAux` (Task 2); `seek_by_name` (Task 1).
- Produces: `Commands._channel` raises `StripAux` when `kind == "aux"` and the requested view is `plugin_channel`/`send`/`eq`; `_guarded` maps `StripAux` → skipped with `e.note`. `PluginCommands._mixer_slot1(ch) -> list[str]` (enter `plugin_mixer`, require `d.view.index in (None, 1)`, return the 8 slot-1 texts). `insert`/`remove` on aux + slot 1 use the Mixer path and return `after["path"] == "mixer"`; aux + slot ≥2 → skipped with `StripAux.note`. `list` returns aux rows as `{"1": {...} | None, "2": None, …}` and `after["aux"] = [numbers]` beside `unsupported`.

- [ ] **Step 1: Write failing tests** (`tests/test_assign_plugin.py`, aux fixture = `[Track(1,"1"), Track(5,"Aux1", kind="aux"), Track(3,"StOu", kind="output")]`):
  - `test_aux_insert_slot1_uses_mixer_view`: `insert(2, None, 1, "Tape Delay")` → verified, `after["path"] == "mixer"`, fake aux inserts[1] == "Tape Delay", track 1 inserts unchanged.
  - `test_aux_insert_slot1_occupied_is_skipped`: aux slot 1 filled → skipped, note contains `"슬롯 1에"`, nothing inserted anywhere.
  - `test_aux_insert_slot2_is_skipped_with_z19_note`: `insert(2, None, 2, "Chorus")` → skipped, note contains `"Z19"`.
  - `test_aux_remove_slot1_uses_mixer_view`: remove → verified, `after["path"] == "mixer"`, slot empty.
  - `test_list_reports_aux_slot1_only`: whole-bank list → aux row `{"1": {"text": …, "name": …}, "2": None, …, "8": None}`, `after["aux"] == [5]`, and the aux row never equals track 1's row.
  - `test_params_on_aux_is_skipped`: `params(2, None, 1)` → skipped with Z19 note.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `_channel`/`_guarded` changes, `_mixer_slot1`, Mixer-path `insert` (rewind → `seek_by_name` → press → `settle_smart` → re-enter `plugin_mixer` → verify column `ch` changed and the other 7 unchanged) and `remove` (rewind → press → verify `--`), `list` aux rows (read via `_mixer_slot1`, abbrev lookup only — no overlay reveal on aux), tool description sentence: "Aux strips (no track): only slot 1 insert/remove, via the Plug-in Mixer view."
- [ ] **Step 4: Run** `uv run pytest -q` → green. **Commit** `feat: refuse channel views on Aux strips; slot-1 insert/remove via Plug-in Mixer view`.

### Task 4: Tolerance and correction rounds

**Files:**
- Modify: `src/logic_mcp/logic/values.py:84-89`, `src/logic_mcp/logic/setter.py:12`
- Test: `tests/test_values.py`, `tests/test_setter.py`, any test asserting `"6회"`

**Interfaces:**
- Produces: `tolerance_for(target, unit)`: dB → `0.2`; unit present (Hz, ms, %) → `max(|target|, 1.0) * 0.02`; unit None → unchanged 2 %. `MAX_ROUNDS = 10`. Failure note text keeps the pattern `f"{MAX_ROUNDS}회 안에 허용 오차 {tolerance} 안으로 못 맞춤 (마지막 {cur.text!r})"`.

- [ ] **Step 1: Update/add tests**: `test_values.py::test_tolerance_defaults` asserts `tolerance_for(3.0,"dB") == 0.2`, `tolerance_for(3500,"Hz") == 70.0`, `tolerance_for(0.5,None) == 0.01`; `test_setter.py::test_tolerance_argument_overrides_default` (explicit `tolerance=0.05` is used verbatim); replace any `"6회"` expectation with `"10회"`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** `uv run pytest -q` → green. **Commit** `fix: widen default set tolerances (dB 0.2, 2 %) and allow 10 correction rounds`.

### Task 5: `plugin move`

**Files:**
- Modify: `src/logic_mcp/logic/plugin.py` (new `move`), `src/logic_mcp/server/tools.py:92-141` (action `"move"`, param `to_slot: Slot = None`)
- Modify: `CHANGELOG.md`, `CHANGELOG.ko.md` (Unreleased: Added `move`, name-scan fallback, Aux handling; Changed tolerances)
- Test: `tests/test_assign_plugin.py`, `tests/test_server.py`

**Interfaces:**
- Produces: `PluginCommands.move(strip, number, slot, to_slot) -> ToolResult`; tool `logic_plugin(action="move", slot=from, to_slot=to)`; `after = {"from": a, "to": b, "plugin": full_name, "note_path": "remove+insert"}`; success note `"설정값은 초기화됨(MCU에 이동 명령이 없어 제거+재삽입)"`.

- [ ] **Step 1: Write failing tests**:
  - `test_move_removes_and_reinserts_into_empty_slot`: track slot 2 = "Compressor", `move(1, None, 2, 6)` → verified, inserts[2] None, inserts[6] "Compressor", `after == {"from": 2, "to": 6, "plugin": "Compressor", "note_path": "remove+insert"}`.
  - `test_move_target_occupied_is_skipped`: note contains `"슬롯 6에"`, nothing changed.
  - `test_move_source_empty_is_skipped`: note contains `"슬롯 2이 비어 있음"`.
  - `test_move_reports_when_reinsert_fails`: make the fake drop the overlay for the name (reuse the mechanism from `test_insert_name_scan_gives_up_without_pressing`) → `verified == "unverified"`, note contains `"제거는 됐으나 재삽입 실패"` and `"Compressor"`.
  - `test_move_on_aux_is_skipped`: Z19 note.
  - `tests/test_server.py`: `move` without `to_slot` → skipped note `"move에는 to_slot(1-8)이 필요"`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** `move` per spec §F5 (header name via `_open_edit`, then `d.enter("plugin_channel")`, target empty check, then the existing remove body and insert body as inner calls — refactor `insert`/`remove` bodies into `_insert_body(ch, slot, want, replace)` / `_remove_body(ch, slot)` returning `ToolResult` so `move` can compose them inside one `_guarded`). Tool description: append "move: remove + reinsert into an empty slot (to_slot); plug-in settings are reset."
- [ ] **Step 4: Update CHANGELOGs.** **Step 5: Run** `uv run pytest -q` → green. **Commit** `feat: plugin move (remove + reinsert) and changelog`.

### Task 6: Live check script

**Files:**
- Create: `scripts/live_check4.py` (pattern of `scripts/live_check2.py`): given a strip number, runs ① insert "Channel EQ" into the first empty slot and remove it (prints note), ② `plugin list` for the whole bank (prints aux rows), ③ set Channel EQ `Low Shelf Gain` 3 on an existing Channel EQ slot if present, ④ `move` of the last occupied slot into the first empty slot and back. Prints one line per step: `verified/unverified/skipped | note`. No project save.

- [ ] **Step 1: Write the script** (no tests; it is an operator tool). **Step 2:** `uv run python -c "import ast,sys;ast.parse(open('scripts/live_check4.py').read())"` → ok. **Step 3: Commit** `chore: live check script for spec 4`.
