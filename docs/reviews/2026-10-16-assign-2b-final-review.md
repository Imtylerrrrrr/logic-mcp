# 최종 리뷰 — 계획 2b (5065811..d8206d1, `feat/assign-2b`, 9커밋)

리뷰 범위: 패키지 diff 전체(2726줄)를 한 번에 읽고, `modes.py`·`setter.py`·`sends.py`·`strips.py`·`fake_assign.py`는 원본을 따로 열어 확인했다. `uv run pytest -q` 251 passed(39 s, 2026-10-16) 재확인. 아래 두 결함(C1, I1)은 스크래치패드 스크립트로 가짜 Logic에 재현했다(작업 트리 변경 없음).

### Strengths

- **가드 위치가 맞다.** `StripKinds.ensure`가 EQ set·PL `_channel`·SE `_channel` 모두에서 `focus`/`enter` 이전에 호출된다(`assign.py` `_channel`, `sends.py:100`). `plugin list` 뱅크 경로는 출력·Master를 `None` + `unsupported`로 표시하고 나머지는 계속 읽는다. `eq get`은 E1 `has_eq`만 돌려주는 계획의 보정표를 그대로 따랐다.
- **TRACK 홀드 메뉴 안전장치(Z5).** `track_param`은 누르기 전에 2행 라벨을 확인하고, 다르면 버튼을 놓고 ModeError를 던진다. `read_strip_outputs`는 `changed`일 때만 Volume으로 되돌리고, 중첩 finally로 `leave(keep_select=True)`까지 반드시 간다. 항목 6·7을 누르는 경로는 코드에 없다.
- **set_dest의 "확정하지 않음" 규칙.** 오버레이가 `Bus want`가 아니면 누르지 않고 unverified로 끝낸다. finally의 leave가 미리 선택을 취소하는 S4 사실에 맞게 기댄다. 보정 루프는 비버스 항목(`1`, `2`)에서 한 칸씩만 나아가므로 과회전하지 않는다.
- **열 위치 해석(S2).** `col_of`/`parse_send`가 1행 라벨을 쓰지 않고, `*` 뮤트 접두·`PosPan`/`Post Pa` 조각·잘린 `-29.2 d`를 모두 처리한다. 단위 테스트(`test_sends.py`)가 실측 문자열을 그대로 쓴다.
- **set_level.** -inf는 Flip + raw 1(raw 0 금지 준수), 일반 값은 `set_numeric`(db_table, 볼륨 표 재사용, S6). +6 클램프 note, NaN skipped. 모든 경로가 `leave_safely`로 Flip을 끈다.
- **가짜 Logic 확장.** S1~S11을 충실히 옮겼다: SE 페이지 기억(트랙별), 1틱 = 1항목 미리 선택과 0.8초 깜박임, `Instantiate` 2초 지연 커밋, S10(출력 선택 시 `se_track` 유지), S11(센드 없는 열 무반응). 테스트는 목(mock)이 아니라 이 모델을 거쳐 실제 메시지 흐름을 검증한다.
- **캐시 m4.** `load`가 번들 params를 deepcopy해 두 사본을 분리했으므로, 사용자가 번들 항목을 고쳐도 `bundled_params` 기준이 오염되지 않는다(`test_save_writes_only_entries_that_differ_from_bundle` 마지막 단계가 확인). `merge_bundled`는 `setdefault("params")[name]`과 `generated`만 바꾸므로 `list`·`abbrev`·`complete`·다른 params 키를 보존하고, tmp + `os.replace`로 원자적으로 쓴다.
- **`logic_send` 입력 검증**은 `logic_plugin`/`logic_eq`와 같은 방식이다. 범위는 스키마(`ge/le`)로 막고, 빠진 인자는 도움말이 담긴 note와 함께 skipped로 돌려준다. `"-inf"` 문자열은 `Literal`에 정확히 맞으므로 float 변환 전에 잡힌다.
- 문서: README·스킬·스펙 보정은 실측과 일치한다. 스킬은 Aux 자동 생성 뒤 `logic://strips`를 다시 읽으라고 안내하고, Mackie Control 재설치 절차도 담았다.

### Issues

#### Critical (Must Fix)

**C1. 스트립 종류 판별이 실패해도 막지 않고 통과시키며(fail-open), 잘못 읽은 결과가 세션 내내 캐시에 남는다** — `src/logic_mcp/logic/modes.py:311-329`(`track_param`), `src/logic_mcp/logic/strips.py:26-31`
- 무엇이 문제인가: `track_param`은 Output 항목 V-Pot을 누른 뒤 CS 뷰 2행을 그대로 돌려준다. 누름이 실제로 먹혔는지, 즉 2행이 Output 값인지 확인하지 않고, `view.kind == "track"`도 확인하지 않는다. Z5에 따르면 Volume은 출력·Master를 포함한 **모든** 스트립에 `+0.0dB`를 보인다. 그래서 누름이 하나라도 무시되면(Z1·Z2처럼 드롭은 실측된 현상이다) 8개 열이 모두 비어 있지 않게 읽히고, `StripKinds`는 Stereo Out·Master를 "따라감(True)"으로 캐시한다. 이 캐시는 번호·이름이 바뀌기 전까지 남으므로, 그 세션에서는 수정 8 가드가 조용히 꺼진다.
- 재현(가짜 Logic): `logic.refuse = {VPOT_PUSH+4}` 상태에서 `plugin.insert(strip=3 /*StOu*/, slot=1, "Compressor")`를 실행하면 결과가 **`verified`**이고, 캐시는 `{(3,'StOu'): True, (6,'Mast'): True}`가 된다. 실제 Logic이었다면 Z4대로 직전 실제 트랙에 Compressor가 들어가고, 결과는 verified로 보고된다. Review Focus 1이 막으려던 결함이 그대로 다시 열린다.
- 왜 중요한가: 이 분기의 핵심 산출물(목표 1)이 안전 가드인데, 확률적으로 꺼지고 꺼진 사실이 드러나지 않는다. 잘못된 트랙을 바꾼 결과도 `verified`로 보고된다.
- 고치는 법:
  1. 누른 뒤 Output 값이 정말 보이는지 확인한다. 2행에 dB 숫자(`parse_value(...).unit == "dB"`)가 하나라도 있으면 Volume이 남아 있는 것으로 보고 ModeError를 던진다. 또는 오버레이 `Channel Strip parameter: Output`을 확인한다. `view.kind == "track"`도 함께 확인한다.
  2. `StripKinds.follows`는 판별이 ModeError로 끝나면 아무것도 캐시하지 않는다(지금도 예외가 전파되므로 캐시하지 않는 점은 맞다. 1번이 들어가면 자연히 성립한다).
  3. 회귀 테스트: `logic.refuse = {P.Note.VPOT_PUSH + 4}`이면 `read_strip_outputs`가 ModeError를 던지고, `insert`는 unverified/skipped가 되며 어떤 트랙도 바뀌지 않고 캐시가 비어 있어야 한다.

#### Important (Should Fix)

**I1. 버스가 아닌 목적지의 센드를 `remove`하면 "already"(ok=True)로 보고하고 아무것도 하지 않는다** — `src/logic_mcp/logic/sends.py:178`(그리고 192-196)
- `(before["bus"] or 0) == want`에서 `bus_number`는 "센드 없음"과 "있지만 버스가 아님"(`1`, `2`, 또는 Logic이 Aux 이름으로 보이는 경우) 모두 `None`을 돌려준다. want == 0이면 둘 다 `already`가 된다. 재현: `sends[1] = Send("1")` → `send.remove(...)` → `ok=True, skipped, "already"`이고 센드는 그대로 남는다. 확정 뒤 판정(192·196행)도 같은 식이라, 제거가 안 됐는데 열이 비버스 텍스트를 보이면 verified가 된다.
- 왜 중요한가: Claude가 "센드 제거됨"으로 믿는다. 비버스 목적지는 범위 밖이지만, 그런 센드를 지우는 일은 사용자가 충분히 시도할 만하다.
- 고치는 법: 제거 판정을 `present`로 한다. `already`는 `want == 0 and not before["present"]`, 확정 술어와 `after` 판정은 `want == 0 → not present`, `want > 0 → bus == want and present`. 테스트는 `Send("1")` 제거에 대해 verified와 함께 `sends[1] is None`을 확인한다.

**I2. 확정 누름이 무시되면 미리 선택 깜박임 때문에 set_dest/remove가 거짓 verified가 될 수 있다(실기 위험, 가짜 Logic은 보여 주지 못함)** — `src/logic_mcp/logic/sends.py:192-196`
- S4에 따르면 미리 선택은 dest 열에서 0.8초 켜짐/0.8초 꺼짐으로 **시간 제한 없이** 깜박인다. 누름이 드롭되면 `press_vpot_until`의 술어가 깜박임의 켜진 위상(`Bus want` 또는 `--`)에서 바로 참이 되고, `settle_overlay` 뒤 `_row`를 한 번 읽어 판정하므로 약 50% 확률로 verified가 된다. 가짜 Logic은 누르는 즉시 `pre.clear()`를 해서 이 경로를 만들지 않는다.
- 고치는 법(값싼 순서):
  - (a) 새 센드라면 확정 뒤 level/pos 열이 채워졌는지(`after["pos"] is not None`) 확인하고, 제거라면 그 열들이 비었는지 확인한다.
  - (b) 깜박임 반주기보다 길게 떨어진 두 번(≥0.9 s 간격)의 읽기가 같을 때만 판정한다.
  - (c) 누른 직후 `Send n Instantiate` 오버레이가 보였는지 확인한다.
  - 가짜 Logic에는 "누름 드롭" 옵션(`refuse`에 V-Pot push 추가)으로 회귀 테스트를 더한다.

**I3. `calibrate`가 값이 끝에 닿아 틱에 반응이 없을 때 정착 1행 조각을 파라미터 "전체 이름"으로 저장할 수 있다** — `src/logic_mcp/logic/assign.py:743, 761, 771`
- 열거형 -1 루프는 마지막 반복, 즉 **값이 바뀌지 않은 틱**의 `read_overlay_name`을 `name`으로 남긴다. 직전 반복이 `settle_overlay()`로 오버레이를 지웠으므로, Logic이 무변화 틱에 오버레이를 다시 그리지 않으면 21칸 정착 1행(예: `CirTyp Thrs   Ratio`)이 읽힌다. 이 문자열에는 `"Page"`가 없으므로 `item["name"]`에 저장된다. 숫자 분기도 값이 최대일 때 +1 틱이 같은 위험을 가진다. 가짜 Logic은 끝에서도 항상 오버레이를 그리므로(`fake_assign.py:717`) 테스트가 이 상황을 보지 못한다. 실기에서는 미측정이다(S7은 무변화만 기록했고 오버레이 여부는 없다).
- 왜 중요한가: `--write`는 같은 실행 안에서 사람의 확인 없이 `known.json`에 영구 반영된다. 기본값이 첫 선택지(Off 등)인 열거형이 흔하므로 잘못된 이름이 번들에 섞이고, 이름 부분 일치 `get/set`이 엉뚱한 파라미터를 고를 수 있다.
- 고치는 법: `tick()`이 True를 돌려준(LCD가 바뀐) 틱에서만 이름을 받는다. 예: 첫 반응 틱의 이름만 저장하고, 반응이 없었으면 반대 방향으로 한 틱 더 가서 읽는다. 추가로 이름이 1행 정착 조각과 같으면 버린다.

#### Minor (Nice to Have)

- **M1. Review Focus 3 테스트는 이름과 달리 예외 경로를 지나지 않는다** — `tests/test_assign_send.py:130`. `drop_all_faders` + `drop_all_vpots`이면 `set_numeric`이 `SetOutcome(False, "V-Pot 틱에 LCD 반응 없음")`을 정상 반환하고, ModeError는 나지 않는다. Flip off는 finally 구조 덕분에 맞지만, 테스트는 "실패 반환 경로"만 고정한다. `refuse={P.Note.FLIP}`처럼 Flip을 켠 뒤 ModeError를 내는 경우나 `fader()`가 "flip on" ModeError를 내는 경우를 하나 더하면 Focus 3을 실제로 고정할 수 있다.
- **M2. `bundled_generated`를 쓰기만 하고 읽지 않으며, 사용자 항목이 번들 갱신을 가린다** — `src/logic_mcp/logic/plugins/cache.py:58, 82`. 2b 이전 형식의 사용자 파일(이 맥의 `~/.logic-mcp/plugins-12.0.1.json`에 `Compressor`·`Channel EQ` 전체 사본이 있다)이나 `plugin params`로 쌓인 부분 표는, 번들이 캘리브레이션으로 갱신되면 "번들과 다름"으로 남아 새 번들 표를 통째로 가린다(항목 단위 병합이 아니다). 이 맥에서는 `calibrate_plugin.py`가 같은 프로세스에서 사용자 캐시도 갱신하므로 실제 피해는 작다. 그래도 계획이 말한 "번들을 고쳐도 사용자에게 반영"은 부분적으로만 성립한다. 계획 수준의 빈틈이다. 고치는 법: `load`에서 사용자 파일의 `bundled_generated`가 현재 번들의 `generated`와 다르면(없음 포함) 번들에 있는 키는 번들을 우선하거나, items 단위로 `name`/`map`이 None인 칸만 사용자 값으로 채운다.
- **M3. `merge_bundled`가 `indent=1`로 `known.json` 전체 형식을 바꾼다** — `cache.py:107`. 현재 파일은 손으로 맞춘 2칸 들여쓰기에 `list`가 줄바꿈 정렬돼 있다. 첫 `--write`에서 목록 수백 줄이 한 줄씩 펼쳐져 diff 리뷰가 어려워진다. 한 번 정규화 커밋을 따로 하거나 `indent=2`로 맞춘다.
- **M4. `StripKinds` 캐시 키 `(number, name)`의 경계** — `strips.py:25`. 번호 표시가 꺼진 상태(Z6 직후 `configure` 전)에서는 키가 `(None, name)`이라 같은 이름의 트랙끼리 충돌한다. 또 "Master"라는 이름의 실제 트랙이 지워지고 진짜 Master가 같은 번호로 밀려오면 True가 남는다. 드문 경우다. `follows`가 `number is None`이면 캐시하지 않게 하는 정도면 충분하다.
- **M5. 가짜 Logic의 PL 쓰기 경로는 Z4를 흉내 내지 않는다** — `tests/fake_assign.py:707`. PL 미리 선택·삽입이 `pl_track`이 아니라 `self.selected`를 쓴다. 그래서 가드가 빠지면 "출력 스트립에 삽입됨"으로 나타나지 Z4의 "직전 트랙이 바뀜"으로 나타나지 않는다. Focus 1 테스트는 note의 `출력` 검사로 고정되므로 지금은 문제가 없지만, 가짜 Logic의 충실도가 떨어지는 지점이다.
- **M6. Aux 자동 생성(S5) 뒤 `leave()`의 선택 복원이 밀린 인덱스를 고를 수 있다** — `modes.py:358`. `_restore_select`가 스트립 인덱스라, 확정으로 Aux가 앞에 끼면 다른 트랙을 다시 선택한다. 선택만 바뀌므로 피해는 작다. 가짜 Logic에 Aux 삽입 모델이 없어 테스트도 없다. note와 스킬의 경고로 일단 충분하고, 실기 10차에서 관찰할 항목으로 남긴다.
- **M7. TRACK 버튼 이중 누름은 실기 미측정 경로다** — `modes.py:315-318`. `read_strip_outputs`는 `enter("track")`(누름 1)으로 CS에 들어간 뒤 다시 TRACK을 홀드한다. Z5는 PAN에서 홀드한 결과만 기록했다. SEND처럼 두 번째 누름이 다른 하위 뷰로 바꾸면 C1의 확인(뷰 종류·dB 검사)이 유일한 방어선이 된다. PAN에서 바로 홀드하는 쪽이 누름 하나를 줄이면서 실측과도 같다. 실기 10차에 확인 항목으로 넣는다.
- **M8. `set_level -inf`에는 "already" 단축이 없다** — `sends.py:234`. 이미 -∞여도 Flip을 켜고 raw 1을 보낸 뒤 verified를 돌려준다. 다른 명령과 일관되게 `before["level_db"] == -inf`면 skipped/already로 한다.
- **M9. `calibrate_plugin.py`는 테스트 프로젝트에서만 쓰라는 경고가 docstring에만 있다.** 스크립트는 실행 중인 프로젝트의 strip 1 빈 슬롯에 바로 삽입한다. 기존 인서트를 건드리지 않고 제거까지 하므로 위험은 낮다. 다만 `calibrate`가 값을 되돌리지 않는다는 점은 메서드 docstring에만 있다. 스크립트 시작 시 "현재 프로젝트: 저장하지 말 것" 한 줄을 출력하고 `--yes` 없이는 Enter 확인을 받으면 충분하다. MCP 도구로 노출되지 않은 점은 확인했다.

### Declined to judge

- 인서트 슬롯 9~15, 악기·MIDI FX 슬롯, 버스가 아닌 센드 목적지 *설정*: 계획 보정표(§6.3)와 SKILL에서 범위 밖으로 정했다. 단, 비버스 센드의 *제거*가 거짓 성공하는 것은 I1로 따로 다뤘다.
- `calibrate_plugin.py` 10종 실기 수집과 `known.json` 실제 내용: 계획이 "계획 밖(컨트롤러 실기 세션)"으로 정했다.
- 판별 때문에 뱅크마다 첫 명령에 붙는 TRACK 모드 지연(약 5초): 계획이 정한 설계 비용이고 스펙에 시간 요구가 없다.
- `merge_bundled`가 번들 `abbrev`는 갱신하지 않는 것: 계획 인터페이스가 params만 정의한다.
- `logic_send`의 `idempotent_hint=True`: MCP 힌트일 뿐이고 행동에 영향이 없다.
- pydantic이 `dest=True`를 int 1로 바꿀 가능성: 실사용에서 생기지 않는 입력이고 스펙도 언급하지 않는다.
- 커밋 메시지의 Co-Authored-By 표기: 코드 리뷰 범위 밖이라 확인하지 않았다.
- 실제 Logic 타이밍 상수(`CONFIRM_S` 3.0, `EDIT_OPEN_S` 1.5, 오버레이 2.0초)의 적정성: 2a 실측값을 그대로 썼고 2b에서 바꾸지 않았다. 센드 확정 지연(약 2초) 대비 `CONFIRM_S` 3.0 + `settle_overlay`도 여유가 있어 보인다. 다만 실기로 검증된 것은 아니며 I2와 함께 실기 10차에서 볼 항목이다.

### Recommendations

1. C1을 먼저 고친다. Output 선택 확인(dB 값 없음, `view.kind == "track"`)과 V-Pot push 드롭 회귀 테스트를 더한다. 수정은 20줄 안팎이다.
2. I1은 `present` 기준으로 판정을 바꾸고 테스트 하나를 더한다. I2는 (a) level/pos 열 확인으로 새 센드·제거를 판정하고, 가짜 Logic에 push 드롭 옵션을 써서 회귀 테스트를 더한다.
3. I3은 이름을 반응한 틱에서만 받도록 바꾼다. 실기 10차 첫 캘리브레이션은 `--write` 없이 돌려 출력된 이름을 눈으로 확인한 뒤 쓴다.
4. 실기 10차 확인 목록에 넣을 것:
   - CS에서 TRACK을 다시 홀드할 때의 동작(M7)
   - 끝값에서의 무변화 틱이 오버레이를 그리는지(I3)
   - 확정 뒤 미리 선택 깜박임이 멈추는지(I2)
   - Aux 생성 뒤 선택 복원(M6)
   - Aux 이름을 바꾼 뒤 dest 목록이 `Bus n`인지 이름인지(I1·보정 루프)

### Assessment

**Ready to merge?** With fixes

수정 8 가드는 위치와 구조가 옳고 센드 기능은 실측을 충실히 따른다. 다만 판별 단계가 V-Pot 누름 하나만 드롭돼도 가드를 끈 채 캐시하고, 잘못된 트랙 변경을 `verified`로 보고한다(C1). 센드 제거·확정 판정에도 거짓 성공 경로가 있다(I1·I2). C1과 I1은 작은 수정과 테스트로 닫을 수 있으니 고친 뒤 병합하고, I2·I3은 병합 전 수정이 바람직하지만 실기 10차 확인과 묶어도 된다.
