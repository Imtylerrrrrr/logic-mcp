# 최종 리뷰: feat/assign-2a (fb76640..7cc4d34, 커밋 19개)

리뷰어: Opus, 2026-10-15. 읽기 전용으로 진행했다. 실행한 것은 `uv run pytest -q`(192 passed, 29.4 s)와 가짜 Logic을 대상으로 한 엣지 케이스 탐침 스크립트 하나(scratchpad, MIDI 포트 없음)뿐이다.
diff는 소스 단위로 여러 번에 나눠 읽었다: modes → setter/values → assign → plugins/* → state/protocol/commands/server → fake_assign → 테스트 → 문서. `cap_assign*.log`는 형식과 사용처만 확인했다.

## Strengths

- **실측을 근거로 한 판단이 추적된다.** 계획과 다르게 간 부분(슬롯 접근 경로, ceil 미리 선택 모델, EQ 페이지 기억, 마지막 페이지 오른쪽 정렬, 페이더/LCD 경합)마다 `docs/mcu-protocol.md`의 사실 A~Z2와 ledger의 Ruling이 붙어 있다. 각 Ruling은 타당하고, 해당 사실을 코드로 옮긴 부분도 정확하다(`classify_view`의 `PL` 코드 판정, `_eq_page_of`의 첫 열 판정, `_read_pages`의 겹침 제거).
- **잘못된 플러그인이 삽입되지 않도록 구조로 막았다.** `insert`는 오버레이 이름이 목록 이름과 정규화 일치할 때만 누른다(`assign.py:530-546`). `_open_edit`는 틱 없이 누른다. 모든 명령은 `_fresh()`로 PAN을 거쳐 남은 미리 선택을 취소한다. 툴 스키마의 `Slot le=8`로 미지원 슬롯은 아예 표현할 수 없다. V-Pot은 `vpot_turn_messages`(63 분할)만 쓴다.
- **finally 규율.** 공개 명령 9개 모두 `with lock / try / finally: leave_safely()` 형태다. 탐침에서 예외가 나는 경로도 끝난 뒤 `pan`, Flip off로 돌아왔다.
- **가짜 Logic이 실측을 실제로 모델링한다.** 지연 응답(`E_` → E1), ceil 모델, 확정 2 s 타이머, 깜박임, 오른쪽 정렬 Compressor 20항목, `lcd_lag`, `drop_first_fader/flip`이 들어 있다. 테스트는 코드 자체를 목으로 바꾸지 않고 이 가짜를 상대로 돈다. Review Focus 1~5에 각각 고정 테스트가 있다.
- **수정 물결의 원인 분석이 좋다.** 특히 Z1이 그렇다. 실패 시간이 정확히 +1.4 s(FADER_TIMEOUT 0.8 + FEEDBACK_TIMEOUT 0.6)라는 점에서 "이동 한 번이 통째로 무시됐다"를 추론하고, 시컨트가 폭주하지 않게 막았다(`reacted` 가드). 수정 뒤 효과가 실기에서 확인되지 않았다는 점도 숨기지 않고 ledger에 "증거 부족"으로 기록했다.

## Issues

### Critical (Must Fix)

**C1. `flip()` 재누름이 Flip을 반대로 돌려놓을 수 있고, 그러면 다음 페이더 이동이 엉뚱한 트랙의 볼륨을 바꾼다.**
`src/logic_mcp/logic/modes.py:277-287` (`flip`), `:260-275` (`fader`), `setter.py:44-46`, `assign.py:476-478`.
- 무엇이 문제인가: FLIP은 토글 버튼이다. 0.5 s 안에 LED가 안 오면 "무시됐다"고 보고 다시 누르는데, Z2의 근거는 "0.5 s 안에 LED 변화 없음" 한 번뿐이다. 누름이 **무시**된 것인지 LED가 **늦게** 온 것인지 구별되지 않았다. Z1(Flip 직후 첫 페이더 이동 무시)을 보면 Logic의 Flip 처리에 지연이 있다는 쪽에 무게가 실린다. LED가 0.5 s 넘어 늦게 오는 경우의 흐름은 이렇다.
  1. 첫 누름으로 Flip on(LED 지연), 0.53 s에 두 번째 누름.
  2. 0.6 s에 첫 누름의 LED on이 도착해 두 번째 `wait_for(flip == on)`이 바로 참이 되고 break.
  3. 그 뒤 두 번째 누름의 LED off가 온다. 실제 Flip은 **off**다.
  4. `set_numeric`의 `d.fader(col, raw)`가 Flip off 상태에서 페이더 `col`을 움직인다. 결과적으로 **뱅크 스트립 col번 트랙의 볼륨**이 EQ 주파수나 Q에 해당하는 raw로 바뀐다(col은 대상 트랙이 아니라 EQ 열 번호다).
  5. 틱 단계가 EQ 값을 맞추므로 명령은 `verified`를 돌려준다. 사용자는 다른 트랙 볼륨이 바뀐 것을 모른다.
  `leave()`의 `flip(False)`도 같은 경합으로 Flip을 **on**으로 남길 수 있다. 그러면 I1과 겹쳐 다음 `set_volume`이 팬을 움직인다.
- 왜 중요한가: 리뷰 지시가 가장 경계하라고 한 "Flip이 꺼진 채 페이더가 트랙 볼륨을 움직이는" 경로 그 자체다. 프로젝트 데이터가 조용히 바뀌고, 결과 보고는 성공이다. 가짜 Logic은 Flip off일 때 페이더를 무시하고(`fake_assign.py:589`) LED 지연 모드도 없어서, 지금 테스트로는 이 경로를 잡을 수 없다.
- 고치는 방법(구조로 막기):
  (a) `fader()` 첫 줄에서 `self.surface.state.assignment.flip`이 아니면 `ModeError("fader", "flip on", "off")`를 던진다. Flip off에서 페이더를 보내는 일 자체를 불가능하게 만든다.
  (b) `flip()`은 재누름 전에 추가 관찰 창(예: LED_TIMEOUT 1회 더)을 두고, 그 사이 LED가 오면 누르지 않는다. 재누름 뒤에는 FLIP LED가 일정 시간(예: 0.3~0.5 s) 더 바뀌지 않는 것을 확인한 다음 최종 상태를 다시 검사해, 원하는 상태가 아니면 ModeError로 끝낸다.
  (c) 가짜에 `late_flip_led`(LED를 0.6 s 늦게 보냄)와 "Flip off일 때 페이더는 트랙 볼륨을 바꾸고 에코함"을 넣고, 테스트 두 개를 추가한다. 하나는 EQ set 뒤 다른 스트립 볼륨이 그대로인지, 다른 하나는 leave 뒤 Flip이 off인지 확인한다.

### Important (Should Fix)

**I1. 스펙 1 `mixer_volume`이 Flip이 남아 있는지 확인하지 않는다.** `src/logic_mcp/logic/commands.py:231-257`.
`mixer_pan`에는 Flip/PAN 가드를 넣었는데(`:267-273`) `set_volume`에는 없다. `leave_safely()`는 ModeError를 삼키므로, 복귀에 실패하거나 C1 경합이 생기면 Flip on 상태가 실제로 남는다. 그때 `set_volume`은 페이더로 V-Pot 파라미터(PAN 뷰라면 팬, EQ 뷰라면 EQ 값)를 움직인다. 게다가 에코 raw가 보낸 값과 ±32로 맞으면 `verified`가 된다. 스펙 §2의 원칙 1("스펙 1 도구는 PAN 모드와 Flip 해제를 전제")을 보면 사용자는 볼륨 명령이 볼륨만 바꾸리라 기대한다.
고치는 방법: `mixer_pan`과 같은 가드를 넣는다. `assignment.flip`이면 `leave_safely()`를 부르고, 그래도 Flip이 on이면 skipped와 `last_leave_error`를 돌려준다. Flip이 on일 때 `set_volume`이 페이더를 보내지 않는다는 테스트를 하나 추가한다.

**I2. `leave()`는 한 단계라도 실패하면 나머지 복귀 단계를 건너뛴다.** `modes.py:307-330`.
NAME 토글 → Flip off → PAN → SELECT 복원이 순서대로 이어지는데, `toggle_name_value()`가 ModeError를 던지면 Flip off와 PAN을 시도조차 하지 않는다. `flip(False)`가 실패해도 PAN을 누르지 않는다. 어느 쪽이든 Flip이나 비PAN 상태가 남고, 그 위로 I1이 겹친다. `_name_mode`/`_focused`도 갱신되지 않아 다음 명령까지 어긋남이 이어진다.
고치는 방법: `leave()` 안에서 단계마다 try로 감싸 오류를 모은다. Flip off와 PAN은 무조건 시도하고, 마지막에 모은 오류를 하나의 ModeError로 던진다. `_focused`·`_restore_select`는 finally에서 정리한다. NAME 토글이 실패하는 가짜로 "그래도 PAN·Flip off" 테스트를 하나 추가한다.

**I3. 입력 검증이 비어 있어 예외가 툴 밖으로 나가고(Global Constraint "예외를 밖으로 던지지 않는다" 위반), 한 경우는 반대 값을 `verified`로 설정한다.** 가짜를 대상으로 재현했다.
- `logic_plugin set` Channel EQ `LoCutS` 24(번들 known.json의 enum 매핑): `raw_for`가 `"24.0"`이 선택지에 없다며 `ValueError`를 던진다. 문자열 `"24"`도 `float`로 바뀌어 같은 결과다. **번들에 들어 있는 파라미터를 logic_plugin으로 설정할 수 없다.** (`assign.py:467-483`, `values.py:60-62`) 고치는 방법: `item.map.type == "enum"`이면 숫자 값을 텍스트로 바꿔(정수면 `str(int(v))`) `set_enum`으로 보낸다.
- `logic_eq set` freq 0, q ≤ 0, gain NaN: `math.log`나 `round(nan)`에서 `ValueError`가 난다(`values.py:57`). gain ±24 바깥은 6회 틱을 헛돌고 실패한다. 고치는 방법: freq 20~20000, gain −24~24, q 0.1~100을 스키마(`Field(ge, le)`)나 `set()` 입구에서 skipped로 막는다. 그 밖의 예외는 공개 메서드에서 잡아 `unverified`로 돌려준다.
- `logic_eq set` param `on`, value `1`/`1.0`: `str(1.0) == "1.0"`은 `("on","true","1")`에 없어서 **Off로 설정하고 verified**를 돌려준다(`assign.py:135-136`). 고치는 방법: 숫자는 `bool(value)`로 판정한다.

**I4. 프로빙으로 파라미터를 움직인 뒤 매핑을 못 얻으면 끝값에 그대로 남는다.** `assign.py:476-483`, `setter.py:27-33`.
숫자 값이 들어오고 캐시에 매핑이 없으면 페이더를 1 → 16383으로 보낸다. 이때 파라미터가 비숫자 표시(`On`, `PltDig`)이거나 lo == hi여서 `mapping is None`이 되면, `set_numeric`은 `n is None → ticks = 1`을 6회 반복하고 실패한다. 파라미터는 최대값 + 6틱에 머문다. 실패한 설정이 원래 값을 망가뜨리는 것이고, 출력 게인이나 드라이브류라면 재생 중 소리가 크게 튈 수 있다.
고치는 방법: `flip(True)` 직후의 `strips[col].fader_raw`(현재 위치)를 저장해 두고, 매핑이 None이거나 최종 실패하면 그 raw로 되돌린다. 숫자 값인데 매핑이 None이면 틱으로 가지 말고 skipped("숫자로 설정할 수 없는 파라미터")를 돌려준다.

**I5. 사용자 캐시 파일이 깨지면 서버가 뜨지 않는다. 저장도 원자적이지 않다.** `plugins/cache.py:44-56`.
`PluginCommands.__init__`(서버 build 시점)에서 `json.loads(path.read_text())`를 예외 처리 없이 부른다. `save()`는 `write_text`로 덮어쓰기 때문에, 명령 중간에 클라이언트가 서버 프로세스를 죽이면 반쯤 쓰인 파일이 남는다. 그다음부터 서버는 기동할 때마다 JSONDecodeError로 죽고, 사용자는 원인을 알 길이 없다.
고치는 방법: 임시 파일에 쓰고 `os.replace`로 바꾼다. load에서 JSONDecodeError가 나면 `.bad`로 옮기고 빈 사용자 캐시로 시작한다. 파일에 `"format": 1`도 넣는다. W 수정으로 index 의미가 이미 한 번 바뀌었다(페이지 기준 번호, 아래 m3).

### Minor (Nice to Have)

- **m1.** `tests/test_server.py:83-84` 임포트가 파일 끝에 있다(보류 1). 상단으로 옮긴다.
- **m2.** `modes.py:260-275` fader 재전송이 정상 경우에도 +1.4 s를 쓴다(보류 3). `raw == before`(에코가 올 이유가 없는 경우)면 재전송을 건너뛴다. `probe_mapping`에서 파라미터가 이미 최솟값이나 최댓값일 때 이 경우가 실제로 생긴다.
- **m3.** 파라미터 index가 페이지 기준이라 Compressor는 1..16, 21..24로 빈칸이 생긴다(`assign.py:264-266`). 17을 요청하면 "자리가 비어 있음"이 나온다. 결정 자체(W Ruling)는 일관되지만 툴 설명에 "index는 params 결과의 값을 그대로 쓸 것, 마지막 페이지에서 번호가 건너뛸 수 있음"을 적는다.
- **m4.** `PluginCache.load`는 `{**bundled.params, **user.params}`로 합치고 `save()`가 합친 전체를 사용자 파일에 쓴다. 그래서 이후 번들 known.json을 고쳐도, 한 번이라도 저장한 사용자에게는 반영되지 않는다(`cache.py:49,55`). 사용자 파일에는 사용자가 배운 항목만 쓰거나 번들 버전을 기록한다.
- **m5.** 학습된 매핑(`item["map"]`)과 축약(`abbrev`)을 무효화하는 장치가 없다. X처럼 잘못 학습된 값이 영구히 남는다(이번에는 컨트롤러가 손으로 지웠다). 설정이 6회 안에 실패하면 그 항목의 map을 지우는 정도면 충분하다.
- **m6.** `list`는 뱅크 전체를 돌 때 PL 뷰에서 SELECT만 눌러 트랙을 바꾼다(`assign.py:357-360`). 이때 PL 2행이 새 트랙으로 갱신된다는 것은 가짜의 가정이다. progress.md에 "실기 2차 확인 대상"으로 적혔지만 live_check2는 한 트랙 list만 돈다. 잘못된 컨트롤을 움직이지는 않지만(누르지 않음), 갱신되지 않으면 인벤토리가 틀린다. 실기에서 확인하거나 트랙마다 2행 변화를 기다리는 대기를 넣는다.
- **m7.** `leave()`가 실패하면 `_focused=True`가 남아, 다음 명령의 `focus()`가 새 `_restore_select`를 기록하지 않는다(I2와 함께 고치면 해결된다).
- **m8.** `docs/progress.md` 스펙 2a 절에 "(컨트롤러가 체크)", "(컨트롤러가 채움)" 자리표시가 그대로 있다. 실기 4~7차 결과(17/17 등)도 progress.md에는 없고 ledger에만 있다.
- **m9.** `slope` 검증의 `str(int(value))`는 12.7을 12로 받아들인다(`assign.py:117`). 정수가 아니면 skipped로 돌려준다.
- **m10.** 실기에서 한 번도 밟지 않은 경로: `insert replace=true`(차 있는 슬롯을 되감기 → 교체), 슬롯 3~8, enum 플러그인 파라미터 set, index로 get, `list` 뱅크 전체. 이름 확인 게이트가 있어 잘못 삽입될 위험은 낮지만, "검증됨"이 아니라 "미검증"으로 기록해 둔다.

## Verdict on the five deferred items

1. **test_server.py 끝 임포트**: 고친다(m1). 이동만 하면 되고 위험은 없다.
2. **N % 8 == 0 겹침 오탐**: **수용한다.** 문서에 남기면 된다. 오탐이 나려면 직전 페이지 마지막 k열과 마지막 페이지 앞 k열이 축약명과 값 텍스트까지 모두 같아야 해서 드물다. 오탐이 나도 결과는 항목 하나가 params에서 빠지는 정도이고 컨트롤이 움직이지는 않는다. 다만 빠진 항목과 축약명이 같은 다른 항목이 있으면, 이름 조회가 "여럿에 맞음" 대신 남은 하나를 고른다. 캐시에 그 플러그인의 전체 표(N을 아는 번들 표)가 있으면 그것으로 겹침을 판정하도록 2b 번들 생성 때 보강하기를 권한다.
3. **fader 재전송 +1.4 s**: **수용하되 1줄 개선을 권한다**(m2: `raw == before`면 재전송하지 않음). 같은 절대 위치를 다시 보내는 것은 멱등이라 안전하다. 단 C1의 Flip 가드가 이 경로보다 먼저 있어야 한다.
4. **Q 허용 오차 2 %(틱 격자 ≈6 %)**: **수용한다.** 정확 매핑(T)으로 페이더 한 번에 안착하는 것이 주 경로이고, 실기 4·6·7차와 반복 프로브 12/12가 이를 뒷받침한다. 틱 폴백에서는 격자 때문에 허용 오차 안에 들어가지 못해 실패가 정상 결과다. 실패 메시지에 "가장 가까운 값 X(틱 격자 ≈6 %)"를 넣으면 사용자가 판단하기 쉽다. `set_numeric`이 per_tick으로 격자 > 2·tol을 감지하면 가장 가까운 값을 note로 남기는 정도면 된다.
5. **슬롯 9~15 미지원**: **수용한다.** 스키마(`le=8`)와 `_begin`이 막고, README와 문서에도 적혀 있다. 다만 `list` 결과에 "슬롯 1~8만 보임" 같은 note나 필드를 넣어, 9번 이후 인서트가 없다고 오해하지 않게 한다.

## Declined to judge

- 프로빙이 파라미터를 1·16383(최소·최대)으로 잠깐 보내는 것 자체: 스펙 §5.2(179행)가 정한 방식이라 판정하지 않았다. 실패했을 때 원래 값으로 돌려놓는 문제만 I4로 올렸다.
- EQ 명령이 Channel EQ를 기본으로 자동 삽입하는 것(`allow_insert=True` 기본값)과 트랙 선택이 바뀌는 부작용: 스펙과 README에 명시돼 있다.
- 센드(`logic_send`), 번들 파라미터 표 10종, 스킬 문서: 계획 Goal이 2b로 미룬 범위다.
- 타이밍 상수의 구체 값(ENTER_TIMEOUT 3.0, TICK_QUIET_S 0.4, CONFIRM_S 3.0 등): 실측에서 나온 값이고, 실기 없이 검증할 수 없다. 대기 방식(조건 대기 + 조용 대기)의 구조만 봤고 타당하다.
- `cap_assign*.log` 픽스처 내용: 형식(RX 타임스탬프 + 바이트)과 사용처(test_protocol·test_state)만 확인했다.
- 실기 7차 결과: 리뷰 시점에 진행 중이었다.
- 스캔 소요 시간(실측 75 s, 스펙 30~90 s): 범위 안이라 판정하지 않았다.
- 커밋 트레일러와 커밋 메시지 형식: 코드 품질 대상이 아니다.
- 비ASCII 트랙명 뱅크에서 `plugin_mixer`와 `plugin_edit` 판정(`classify_view`가 `NN:` 열에 의존): 스펙 1 configure의 이름 형식 전제(`name_format_ok`)에 속하는 문제라 2a 범위 밖으로 봤다.

## Recommendations

1. C1을 먼저 고친다. fader의 Flip 가드, flip의 관찰 창과 최종 확인, 가짜의 LED 지연 및 Flip off 볼륨 모델을 함께 넣는다. 이어서 I1과 I2를 고친다. 이 셋은 같은 "Flip 잔류" 축에 있다.
2. I3, I4, I5는 각각 작은 수정이고 테스트 1~2개씩이면 된다.
3. 고친 뒤 live_check2를 최소 2회 돌린다. 가능하면 `insert replace=true`와 `list`(뱅크 전체) 항목을 추가한다. Z2 재누름 경로는 여전히 실기에서 확인되지 않았으니 progress.md에 "미검증"으로 남긴다.
4. 2b 전에 `set_volume`/`set_pan` 이외의 스펙 1 도구(트랙 mute 등)가 어사인먼트 뷰에서도 안전한지 표로 정리해 두면 센드 작업 때 같은 종류의 실수를 막을 수 있다.

## Assessment

**Ready to merge?** With fixes

**Reasoning:** 실측에 맞춘 구조와 테스트는 견고하다. 그러나 Flip 토글 재누름(C1)이 Flip off 상태에서 다른 트랙 볼륨을 조용히 바꾸고 성공을 보고하는 경로를 열어 두었고, 스펙 1 `set_volume`의 Flip 가드 누락(I1)과 `leave()`의 단계 중단(I2)이 그 위험을 키운다. 이 셋과 입력 검증(I3)은 머지 전에 고쳐야 한다.
