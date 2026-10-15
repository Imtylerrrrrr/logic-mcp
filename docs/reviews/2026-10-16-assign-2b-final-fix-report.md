# 최종 리뷰 수정 웨이브 보고 — 계획 2b (`feat/assign-2b`, d8206d1 → e5f2706)

전체 스위트: `uv run pytest -q` → **263 passed**(50 s, 2026-10-16, rc=0). 시작 시 251개였고 12개를 더했다. 기존 테스트 하나의 기대값을 바꿨다(아래 M8).
Logic Pro는 실행하지 않았다. 라이브 스크립트도 돌리지 않았다. CoreMIDI·`~/.logic-mcp`·번들 `known.json`에는 쓰지 않았다.

## 커밋
| SHA | 내용 |
|---|---|
| d71f864 | C1 + M4 + M7: 스트립 판별 fail-closed, PAN에서 TRACK 홀드 |
| 86da14f | I1 + I2 + M8: 센드 제거는 present로 판정, 확정은 3회 읽기, -inf already |
| 76db898 | I3: calibrate 이름은 LCD가 바뀐 틱에서만 받음 |
| e5f2706 | M1 · M3 · M9 |

## C1(+M7, M4) — 스트립 판별 fail-closed
- `src/logic_mcp/logic/modes.py:312` `track_param`
  - `enter("track")`를 없앴다. 뷰가 PAN이 아니면 `leave(keep_select=True)`로 PAN에 간 뒤 TRACK을 홀드한다(Z5 경로, M7).
  - 누르기 전 라벨 확인은 그대로 둔다. 항목 6·7을 누르는 경로는 없다.
  - 손을 뗀 뒤 다음 경우에 ModeError를 던진다.
    - `view.kind != "track"`
    - label이 Output인데 2행에 `parse_value(t).unit == "dB"`인 열이 있음. note: "Output 누름이 무시된 듯(스트립 종류 판별 실패)"
    - label이 Volume인데 dB 열이 하나도 없음(Volume 복원을 확인하지 못함)
  - Volume이 아닌 항목을 누르기 직전에 `_cs_dirty = True`를 세운다(`modes.py:54`, `:328`). Volume 복원이 확인되면 False로 돌린다.
- `modes.py:347` `read_strip_outputs` 순서
  1. PAN에서 홀드 → Output
  2. 읽기
  3. `leave(keep_select=True)`
  4. finally: `_cs_dirty`이면 PAN에서 다시 홀드 → Volume(dB 확인)
  5. `leave(keep_select=True)`
  - 복원이 실패해도 ModeError가 전파되므로 호출자는 unverified가 된다.
  - 라벨 거부(누름 없음)일 때는 복원 누름을 하지 않는다.
- `src/logic_mcp/logic/strips.py:21` `follows`
  - 캐시 조회는 `number is not None`일 때만 한다.
  - 읽기에서 예외가 나면 아무것도 캐시하지 않는다(예외가 그대로 전파됨).
  - 캐시에는 `number is not None`인 스트립만 넣는다(M4).
  - 대상 결과는 이번 읽기의 `outs[ch]`에서 바로 가져온다. 그래서 번호 없는 스트립도 가드가 꺼지지 않는다.
- 가짜 Logic은 바꾸지 않았다. 이미 PAN에서 TRACK을 누르면 `C_` 메뉴가 나오고, `refuse`에 든 누름은 `cs_param`을 바꾸지 않는다(Volume 유지).
- 테스트
  - `tests/test_modes.py:309` `test_read_strip_outputs_raises_when_output_push_is_dropped`
  - `:321` `test_read_strip_outputs_holds_track_from_pan_each_time`: TRACK down 시점의 가짜 뷰가 두 번 모두 `pan`인지 확인한다.
  - `tests/test_assign_plugin.py:377` `test_insert_on_output_strip_fails_closed_when_output_push_is_dropped`: not ok, note에 `Output` 포함, 인서트 불변, `cmds.strips.cache == {}`, pan, `cs_param == 0`.
  - `tests/test_strips.py:38` `test_strip_kinds_caches_nothing_when_read_fails`
  - `tests/test_strips.py:21` `test_strip_kinds_does_not_cache_strips_without_number`(M4)
- RED: `uv run pytest -q tests/test_modes.py tests/test_assign_plugin.py -k "dropped or from_pan"` → 3 failed.
  - 수정 전 insert는 `ok=True, verified`였다.
  - M4 테스트는 수정 뒤에 작성했다. HEAD의 strips.py로 되돌려 돌리면 1 failed임을 확인했다.
- GREEN: 같은 파일들 66 passed, 전체 256 passed.
- 기존 Task 1 테스트(`test_enter_track_reads_outputs_and_restores_volume`의 누름 `[4, 0]`, 라벨 거부 테스트의 `pushes == []`)는 바꾸지 않고 통과한다. TRACK 누름 수만 줄었다(enter 누름 1 + 홀드 → 홀드만). 개수를 고정한 테스트는 없다(`>= 1`과 캐시 재사용 동일성만 확인).

## I1 — present 기준 제거
- `src/logic_mcp/logic/sends.py:188`: `already`는 `want == 0`이면 `not before["present"]`, 그 밖은 `before["present"] and before["bus"] == want`.
- 확정 술어와 after 판정은 `dest_done`(`sends.py:75`)이 맡는다.
  - 제거: `not present`이고 level·pos 열이 빈칸
  - 버스: `present and bus == want and pos is not None`
- 테스트: `tests/test_assign_send.py:87` `test_remove_non_bus_destination_is_verified_by_presence`(`Send("1")` 제거 → verified, `sends[1] is None`). RED였다(수정 전에는 already/skipped).

## I2 — 확정 누름 드롭
- (a) `dest_done`이 pos(제거라면 level·pos 열까지)를 확인한다.
- (b) `sends.py:26`, `:205`: `settle_overlay` 뒤 `d.pause(0.45)`를 두 번 하며 행을 세 번 읽는다(0·0.45·0.9초). 세 텍스트가 모두 같고 `dest_done`일 때만 verified로 판정한다. 그 밖은 unverified이고 note에 "확정 누름이 무시된 듯(미리 선택 깜박임, 실측 S4)"와 읽은 행들을 담는다.
  - 판결은 "≥0.9초 떨어진 두 번 읽기"였다. 처음과 끝 읽기가 0.9초 떨어져 있으니 이를 지킨다. 가운데 0.45초 읽기 하나를 더한 이유는 0.9초 간격 두 번만으로는 연속한 두 켜짐 위상에 걸릴 수 있기 때문이다(약 6%, 기존 센드의 목적지를 바꿀 때). 간격이 반주기 0.8초보다 짧으므로 0.8/0.8 깜박임에서는 꺼진 위상을 반드시 한 번 본다. 판결보다 엄격해질 뿐 느슨해지지는 않는다.
  - 비용: set_dest/remove마다 약 0.9초가 늘어난다.
- 가짜 Logic: `refuse`에 든 누름은 `replies` 첫머리에서 버려진다. 그래서 `pre`가 그대로 남고 깜박임이 계속된다(원래 동작이라 코드는 바꾸지 않았고 docstring에 적었다).
- 테스트: `tests/test_assign_send.py:96` `test_set_dest_unverified_when_confirm_push_is_dropped`. 세 경우를 parametrize했다: 새 센드, Bus 1 → Bus 2, Bus 2 제거. 모두 not ok, unverified, note에 `깜박임`, 센드 불변, 타이머 없음, pan.
  - RED: 3 failed. 그중 실제 거짓 verified는 제거 경우였다. 나머지 둘은 가짜의 결정적 깜박임 위상 덕분에 이미 unverified였고, note 단언만 실패했다.

## I3 — calibrate 이름
- `src/logic_mcp/logic/assign.py:739-778`
  - 정착 1행 조각 `settled`를 먼저 읽는다.
  - 열거형: -1 루프와 +1 루프에서 `tick()`이 처음 True를 돌려준 틱의 오버레이 이름을 받는다. 첫 선택지에 있으면 +1 방향에서 받게 된다.
  - 숫자: +1 틱이 반응하면 읽고 -1로 되돌린다. 반응이 없으면 -1 틱으로 읽고 +1로 되돌린다. 둘 다 반응이 없으면 None이다.
  - `name == settled`이면 버린다.
- 가짜 Logic: `tests/fake_assign.py`에 `no_overlay_on_nochange` 옵션을 더했다. 값이 안 바뀐 파라미터 틱은 그리지 않는다.
- 테스트: `tests/test_calibrate.py:39` `test_calibrate_names_come_only_from_ticks_that_changed_the_lcd`. CirTyp(첫 선택지)는 `"Circuit Type"`, Mix(최댓값)는 `"Mix"`인지 확인한다. 모든 항목의 이름이 실제 이름이거나 None인지 축약명 기준으로 확인한다. 3페이지가 오른쪽 정렬이라 index로는 맞출 수 없다.
- RED: `'CirTyp Thrs   Ratio' in ('Circuit Type', None)` 실패. GREEN: 3 passed.

## Minor
- **M1** `tests/test_assign_send.py:170` `test_set_level_mode_error_raised_inside_try_still_leaves_flip_off_and_pan`: `drop_all_flips` → `flip(True)` ModeError → unverified, note에 `flip`, Flip off, pan, 센드 레벨·트랙 볼륨 불변. 기존 테스트는 유지했다.
  - 참고: drop_all_flips이면 Flip이 처음부터 켜지지 않으므로 "Flip off" 단언은 사소하게 참이다. 이 테스트가 실제로 고정하는 것은 "try 안 예외 → `_fail` → finally leave → pan"이다.
- **M3** `src/logic_mcp/logic/plugins/cache.py:107`을 `indent=2`로 바꿨다. `tests/test_plugins.py`의 merge 테스트에 2칸 들여쓰기 단언을 추가했다.
- **M8** `sends.py:250`: 이미 -∞이면 Flip 없이 skipped/already를 돌려준다. 테스트는 `tests/test_assign_send.py:145`(FLIP 누름 없음 확인).
  - **기대값을 바꾼 기존 테스트**: `tests/test_server.py:143` `test_send_tool_via_client`. 방금 만든 새 센드(기본 -∞, S5)에 `"-inf"`를 보내던 단언을 `verified`에서 `skipped` + `note == "already"`로 바꿨다. M8이 의도한 동작 변화이고, `"-inf"` 문자열이 도구 계층에서 -∞로 해석되는 경로는 여전히 지난다. 실제 -∞ 페이더 경로는 `test_set_level_minus_inf_and_clamp`(-3 dB → -inf)가 계속 고정한다.
  - 처음에는 이 실패를 못 본 채 86da14f를 커밋했다(파이프 때문에 종료 코드를 놓쳤다). 고친 뒤 같은 커밋에 amend했다.
- **M9** `scripts/calibrate_plugin.py`: 시작할 때 한 줄 경고를 출력한다(현재 프로젝트 스트립에 삽입, 값을 되돌리지 않음, 저장 금지). `--yes`가 없으면 Enter를 기다린다. `--write`의 의미는 그대로다. 구문만 확인했고 실행하지는 않았다.

## 확인 범위·우려
- 모든 검증은 가짜 Logic 위에서만 했다. 실기 미확인 항목:
  - PAN에서 바로 TRACK을 홀드하는 경로(Z5에 기록된 것과 같은 경로이긴 하다)
  - Volume 텍스트가 모든 스트립에서 dB로 파싱되는지(`-oodB` 포함)
  - 확정 뒤 깜박임이 멈추는지
  - 끝값 틱이 오버레이를 그리는지
  - 이 넷은 실기 10차 확인 목록에 둔다.
- `read_strip_outputs`는 Volume 복원에도 dB 열이 적어도 하나 있어야 한다. 뱅크 8칸이 모두 빈 경우는 `follows`가 읽기 전에 True를 돌려주므로 생기지 않는다.
- `track_param`이 PAN이 아닐 때 부르는 `leave(keep_select=True)`는 NAME 모드와 Flip도 정리한다. 지금 호출 경로(`ensure`가 focus/enter 전에 호출됨)에서는 항상 PAN이라 실행되지 않는다.
- M2, M5, M6은 지시대로 손대지 않았다.
