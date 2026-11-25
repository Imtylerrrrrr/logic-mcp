# 진행 (스펙 1)

스펙: docs/superpowers/specs/2026-10-14-logic-mcp-core-design.md
계획: docs/superpowers/plans/2026-10-14-logic-mcp-core.md

## 완료 (2026-10-14)
- Task 1 뼈대·픽스처 (cap_raw6.log 4628줄, cap_raw2.log 2453줄)
- Task 2 protocol 디코드·픽스처 파서 (픽스처 미해독 13개는 전부 MCU 외 범용 sysex)
- Task 3 인코더·핸드셰이크 응답 (픽스처 TX 바이트와 일치)
- Task 4 state 리듀서 (스트립·LED·페이더·링·미터)
- Task 5 타임 디스플레이·연결 상태 머신
- Task 6 rtmidi 트랜스포트 + Surface
- Task 7 페이더 dB 표·값 텍스트 파서
- Task 8–10 Commands (주소 해석, 트랙 LED, 트랜스포트, 볼륨, 팬, 뱅크, configure, wait_ready)
- Task 11 MCP 서버 (툴 5, 리소스 4, stdio)
- Task 12 스크립트·문서, 실제 Logic 12.0.1 검증, 페이더 캘리브레이션 233점
- 단위 테스트 62개 통과 (`uv run pytest -q`, 약 11초)

## 실기 검증 (2026-10-14 16:15, scripts/live_check.py, 트랙 3개 프로젝트)
```
wait_ready   ok=True verified   (재바인딩, 1초 조용 규칙)
configure    ok=True skipped     206ms already
mute 1       ok=True verified    183ms
unmute 1     ok=True verified    216ms
play         ok=True verified     36ms
stop         ok=True verified    244ms
cycle_on     ok=True verified    214ms
cycle_off    ok=True verified     33ms
volume -6    ok=True verified    176ms
volume 0     ok=True verified    213ms
pan +10      ok=True verified    427ms LCD에 팬 값을 드러내려고 +1 돌린 뒤 보정.
pan 0        ok=True verified    209ms
bank right   ok=False unverified 1039ms LCD 변화 없음(끝에 닿았거나 트랙이 8개 이하)
bank first   ok=True skipped    1049ms already
```

## 실기에서 고친 것
- ready 판정: 핸드셰이크 뒤엔 10초 조용(설치 애니메이션 677~736초, 안에 3초 공백, 시작 전 7.6초 공백). 재바인딩은 1초.
- set_pan: 페이더를 움직인 직후 LCD 2행은 dB 텍스트라 팬을 못 읽음 → V-Pot +1로 값을 드러낸 뒤 보정.
- dB 파서: 7칸 열에 `-55.0 d`로 잘림, 최저 `-120 dB`(정수). 1차 캘리브레이션은 115점만 잡혔고 수정 후 233점.

## 다음
- ~~Task 12 Step 6~~ 완료(2026-10-15): 트랙 22채널 프로젝트에서 bank left/right = 8칸 페이지(끝 클램프, 15→9→15), channel_left/right = 1칸 모두 verified. 코드 변경 없음.
- 스펙 2: Send/EQ/Plug-in 모드 + Flip (`logic_assign`)

## 메모
- 스파이크 자료: ~/logic-mcp-spike (진행상황.md, 리서치.md)
- 실행 전 같은 이름("LogicMCP")의 가상 포트가 다른 프로세스에 있으면 안 된다(스파이크 capture2.py 종료).

## 스펙 2a
- Task 1~11 완료.
- 실기 결과 (scripts/live_check2.py, 트랙 22채널 테스트 프로젝트): 4차 17/17(1332fad), 5차 15/17·6차 17/17(2115946), 7차 17/17(7cc4d34). EQ 반복 프로브 11/12 → 12/12. 플러그인 스캔 153개 75 s.
  - 미검증 경로(실기에서 밟은 적 없음): `insert replace=true`, 슬롯 3~8, enum 플러그인 파라미터 set, index 로 get, `list` 뱅크 전체(8차: 인벤토리 오류 → 수정 7, 9차 재확인 필요), Flip·페이더 재시도 경로의 실기 발동.
  - 확인 대상: EQ 밴드 7·8 축약명, bypass의 `*` 표시, 스트립 7·8 오버레이 시작 열, plugin params 페이지 헤더, `--scan` 소요 시간·항목 수
- 실기 1차(2026-10-15, Logic 12.0.1, 트랙 15~24 뱅크): EQ·플러그인 명령 전부 실패.
  - EQ: `enter`가 버튼 down의 `E_` 메뉴에서 대기를 끝내 "기대 eq_mixer, 관측 eq_menu".
  - 플러그인: `slot_to`(P<n> 믹서 뷰 커서 ▼)가 실기에서 무반응 → "슬롯 1에서 커서 반응 없음".
  - 컨트롤러 탐침으로 실측 A~O 확보(`docs/mcu-protocol.md` 스펙 2a 실기 1차 실측).
- 수정 1(fix-1): 모드 대기가 `_menu`·과도기를 지나침, `slot_to` 삭제 → 슬롯은 PL 뷰 V-Pot(슬롯 1~8만),
  미리 선택 ceil 모델(현재 이름은 -1 틱, 편집 뷰는 틱 없이 누름), 확정 뒤 편집 뷰 ≈2초 대기(3초),
  NAME 헤더 1페이지에서 이름·2페이지에서 페이지 수, `plugin_channel`은 코드 `PL`만으로 판정, 가짜 Logic·테스트 갱신.
  - 실기 2차 확인 대상: 전체 흐름 재실행, PL에서 SELECT로 트랙을 바꿀 때 2행 갱신, Compressor 3페이지 params, `--scan`.
- 실기 2차(2026-10-15): `eq get`·`eq set gain`·`eq set on(already)`·`plugin list`·`plugin remove` verified. 잔여 4건(P~S)은 수정 2(fix-2)로 반영: 모드 단계 대기 3초, EQ 페이지를 1행 첫 열로 판정, 단위 없는 숫자 파싱(`24 dB/O`), 틱 뒤 0.4초 조용 대기. 실기 3차 확인 대상: `eq set freq/slope/q`, `plugin insert`.
- 실기 3차(2026-10-15): 17건 중 16건 verified, 실패는 `eq set q`(2.8에서 수렴 못 함) 1건. 수정 3(fix-3): Q = 고정 log 0.10~100 매핑(프로빙 안 함, 실측 T~V), 틱 보정 로그 영역을 log 매핑까지 일반화, 단위 없는 숫자 허용 오차 2 %.
- 수정 4(fix-4): 실기 4차 결함 2건. 편집 뷰 마지막 페이지 오른쪽 정렬 겹침 제거(W, `params` 20항목·index 1..16,21..24, 캐시의 겹침 항목은 전체 읽기 때 삭제), `ModeDriver.fader`가 에코 뒤 LCD 변화도 기다림(X, Thrs 매핑 오학습 방지). 가짜 Compressor를 실측 20개 모델로, `live_check2`의 Thrs 목표를 -24로.
- 수정 5(fix-5): 실기 5차 간헐 실패 2건(Z1·Z2). `fader()`는 에코·LCD 모두 없으면 이동 재전송, `flip()`은 LED 무변화면 재누름, `set_numeric`은 이동 전과 같은 값이면 시컨트 건너뜀. 가짜에 `drop_first_fader`·`drop_all_faders`·`drop_first_flip`.
- 수정 6(fix-6, 최종 리뷰 반영): C1 `flip()` 재누름 제거(LED 대기 1.0 s, 늦은 LED와 겹치면 Flip이 꺼진 채 페이더가 트랙 볼륨을 움직임)와 `fader()` 송신 직전 Flip 확인·같은 위치 재전송 안 함, I1 `mixer_volume` Flip 가드, I2 `leave()` 전 단계 시도, I3 EQ 입력 검증·enum 파라미터 숫자 입력·`ValueError` → skipped, I4 프로빙 실패 시 원위치 복원, m5 실패한 map 무효화, I5 캐시 손상 파일 격리(`.bad-*`)·원자적 저장. `live_check2`에 미검증 경로 추가. m4(번들 갱신이 저장된 사용자 캐시에 반영 안 됨)는 2b로 이월.
- 수정 7(fix-7, 리뷰 m6): 뱅크 전체 `plugin list` 가 첫 트랙 외에는 슬롯 대신 트랙 이름 조각을 읽던 문제(실기 8차, Z3). `_channel()` 이 이미 PL 이고 다른 스트립이면 PAN 으로 나가 다시 들어가도록 수정, 가짜 Logic 에 `pl_select_stale` 옵션과 회귀 테스트 추가, `live_check2` 에 식별 안 된 슬롯 검사 추가. 9차 실기 확인 필요.
- 실기 9차(2026-10-16, 사용자가 새로 만든 테스트 프로젝트, 스트립 2): **17/17 verified**, 뱅크 `plugin list` 식별 안 된 슬롯 없음(수정 7 확인). 단, 뱅크 결과에서 Stereo Out·Master 가 직전 트랙의 `Cha EQ` 로 읽힘 → 실측 Z4(출력·마스터 스트립은 PL·SE 가 따라가지 않음). 출력 스트립 대상 insert/eq set 은 엉뚱한 트랙을 바꿀 수 있어 **수정 8 필요**(계획 2b 에 포함: TRACK 모드 Output 열로 스트립 판별, 미지원 스트립은 skipped).
  - 9차 전에 Logic 재시작 뒤 장치 상태가 꼬여 첫 실행은 0/17(실측 Z6). 설정 창에서 Mackie Control 삭제 → 재연결로 복구.
  - 계획 2b 준비 실측(센드 S1~S11, TRACK 모드 Z5) 완료 → `docs/mcu-protocol.md`.

## 스펙 2b
- Task 1~9 완료(2026-10-16, SDD, 263 테스트, Opus 최종 리뷰 C1·I1~I3 수정·재리뷰 통과, main 87aff9b 머지·push; docs/reviews/2026-10-16-assign-2b-*).
- 실기 10차(2026-10-19): `scripts/live_check2.py 1` 29/29 ok(verified 28, 기대된 skipped 1). 출력 스트립 가드: Stereo Out(LCD `SOu`, 번호 15)에 `plugin list`·`send get` skipped, `eq get`은 has_eq만. Aux 자동 생성은 마지막 트랙 뒤에 놓여 대상 스트립이 밀리지 않음(M6 미발현). 다섯 확인 항목 모두 1회 통과. 상세 `docs/mcu-protocol.md` 실기 10차.
- 캘리브레이션(2026-10-19, 3회 수집): 1차 8종에서 결함 셋(이름에 이웃 축약명, `-` 빈 칸, NAME/VALUE 뒤 축약명을 값으로 읽어 enum 오판) → `fix/calibrate-quality` 1차 수정(3커밋) → 2차 8종은 이름·`-` 해결, 숫자 10개 enum 잔존 → 2차 수정(값 열 대기·상한 숫자 선택지 프로빙·스캔 재읽기·insert 근처 탐색, 3커밋) → 스캔 진단(Z8: 항목당 2위치, 오버레이 쓰기 가끔 누락) → 3차 수정(1틱 스캔, 1커밋). 273 테스트. 번들 known.json: 2차 표 7종(Compressor·Adaptive Limiter·Noise Gate·Tape Delay·Stereo Delay·Overdrive·Distortion) + Channel EQ(2a 표), 오판 enum map 10개는 None(쓸 때 프로빙). 메뉴에 `Limiter` 없음(Adaptive Limiter로 대체). Space Designer·ChromaVerb는 목록 위치 오류로 미수집. 2·3차 수정은 실기 전에 Logic 수신이 끊김(no_logic, 원인은 이어폰 분리로 뜬 오디오 인터페이스 모달 = Z10, 닫으면 즉시 복구) → 4차: 1틱 스캔 163개(진단 1~31번 일치), 8종 재수집 → 번들 9종 179 파라미터, enum 오판 0건(2차 A 실기 확인), 1틱 스캔 실기 확인. Space Designer는 `page_to` 실패(16회 안에 1페이지 못 감)로 미수집, Adaptive Limiter 재수집은 V-Pot 63틱 메시지 유실(Z9)로 착지 실패 → 2차 표 유지. insert 근처 탐색은 실기 미확인.
- 리뷰 M2·M5·M6 처리(2026-10-19): M2 수정 — `PluginCache.load`에서 사용자 파일의 `bundled_generated`가 번들 `generated`와 다르면(키 없는 옛 형식 포함) 번들에 있는 이름의 표는 번들 우선, 사용자만 가진 표는 유지(테스트 3건, 276 테스트). M5(가짜 Logic PL 쓰기 경로가 Z4를 흉내 내지 않음) 폐기 — Z4 가드는 실기 10차에서 `SOu`로 확인했고 가짜 모델 확장은 비용 대비 이득 없음. M6(Aux 자동 생성 뒤 선택 복원 인덱스 밀림) 종결 — 실기에서 Aux는 마지막 트랙 뒤에 놓여 발현하지 않음(S5 재확인). Z10 기록: Logic 모달(오디오 인터페이스 변경 알림)이 MIDI 수신을 멈춤 → `wait_ready` 실패 노트에 모달 확인 힌트.
- page_to 한도 수정(2026-10-19, Sonnet 구현): Space Designer 진단으로 편집 뷰가 23페이지이고 임의 위치(15번 파라미터)에서 열림을 확인 → `page_to` 한도를 고정 16회에서 총 페이지+1회로, 실패 메시지에 출발·횟수·현재·총 페이지(가짜 Logic `edit_open_page` 스위치, 277 테스트). Adaptive Limiter 재수집 성공(Gain·Remove DC map 채움, 번들 갱신).
- Space Designer 수집 1차 시도(2026-10-19 21:12): 삽입까지 정상, 수집 도중 프로젝트가 닫혀(Z11) `name_value` 실패 → 미수집. page_to 수정은 이 시도에서 검증되지 않음.
- Space Designer 수집 2차 시도(2026-10-20 00:04): `plugin list`가 Volume 복원 단계에서 실패 → 당시엔 프로젝트 닫힘으로 봤으나 16:00 프로젝트를 연 뒤에도 같아 원인은 Z12(NAME 표시 상태 잔존)로 정정. Z11의 "Quartz 창 0개"는 측정 오류(소유자 이름 NBSP)로 정정.
- 서피스 견고성 수정(2026-10-20 16:10~16:25, Sonnet 구현, 282 테스트, main c14dce1): `configure` 값 표시 판정을 2행 값 유무로 교체(Z12), `page_to` 커서 무응답 1회 재시도(Z13), `probe_pages` 마지막 페이지 ◀ 확인. 16:03 3차 시도는 Z13으로 중단(31초), 재현 실행 2회는 통과.
- Space Designer 수집 3~6차(2026-10-20 16:03~16:38): Z13(16:03 커서 무응답), Z14(16:20 7페이지 동작 파라미터 → '열기' 대화상자 → NAME/VALUE 사망; Logic 재실행으로 안 풀림). 19:45 사용자가 설정 창에서 Mackie Control 2대를 삭제 → 포트 재연결·재설치로 복구.
- Space Designer 수집 7차(2026-10-20 19:49~20:12, 23분): 성공(178개·23페이지, 동작 파라미터 8개 틱 차단, map None 비움) — 그러나 map None 77개. 원인은 Z15(Flip 페이더 값 오버레이 14칸이 옆 열을 2초 덮음) + `_NUM_RE` 공백·`infer_mapping` 단위 불일치. `fix/fader-overlay`(Sonnet 구현) 뒤 재수집 예정.
- 페이더 오버레이 수정(2026-10-20 20:25~20:34, Sonnet 구현, 285 테스트, main 9fad1a4): calibrate 프로빙 뒤 `settle_overlay`, `_NUM_RE` 공백 1칸, `infer_mapping` 단위 불일치 → None. 8차 수집(20:35)은 25번째 항목에서 Z16(커서 무응답)으로 중단 → `page_to` 지연 허용(Sonnet 구현, 287 테스트, main 81c65bc) 뒤 9차(20:5x).
- 9차(20:50)도 7→8페이지에서 Z16으로 중단. 그 뒤 PAN 뷰 `-`·TRACK `Ch Out`(Z17: 서라운드 파라미터 `중앙`+표시 모드 `이름`, 설정 창 캡처로 확인) → PAN 홀드 항목 0 + NAME/VALUE로 복구. 10차(21:0x)는 실패해도 같은 프로세스에서 최대 3회 재시도(캐시 진행분 유지).
- **Space Designer 수집 10차 성공(2026-10-20 21:02~21:19, 17분)**: 178개·23페이지, 1회 시도에 완료(page_to 202회 재시도 0, NAME/VALUE 404회 최대 380 ms, 동작 파라미터 틱 차단 16회 = 7·18페이지 각 4개×2). map: linear 96·log 17·enum 43·None 22(동작 8 + 최소가 `Mute`인 Output Dry/Wet·Center Level, 단위가 바뀌는 Length·Volume Decay Time·Low Mid Freq·X-Over Freq·Low Cut Order — 설계상 None, 틱으로 설정). 이름 165/178(없음: 동작 8·EQ·Size·Filter). 번들 표 10종 357 파라미터, known.json 갱신. 7차 대비 map None 77 → 22.
- **명령 계층 리팩토링(2026-10-20 22:00~22:40, Sonnet 구현·Opus 리뷰 1회, main으로 ff)**: 동작 보존 4커밋 + 리뷰 반영 1커밋. ① `Commands.__init__`의 지연 import를 상단으로(실제 순환 없었음) ② 플러그인·센드가 복사해 쓰던 `_fresh`·`_channel`·`_begin`을 `Commands` 공통 헬퍼로 ③ 서브커맨드 16개 메서드의 try/except/finally를 `Commands._guarded` 한 곳으로(예외→결과 정책 단일화; eq.get·plugin.list·plugin.scan은 전에 그대로 올라가던 StripUnsupported가 skipped로 바뀜, 테스트 1개 추가) ④ `assign.py`(872줄)를 `eq.py`·`plugin.py`로 순수 분할. 순증감 +327/−376줄, 288 테스트. 리뷰어가 가짜 Logic 위에서 main과 HEAD의 호출 157건·MIDI 4418개를 바이트 비교해 동일함을 확인(실기 미검증).
- **configure 값 표시·팬 파라미터 판정 수정(2026-10-20 밤, Z17)**: PAN 뷰 2행에서 이름 있는 스트립 하나라도 팬 값(`-64`~`+63`)이 파싱되면 정상, 전부 `-`면 PAN 홀드 항목 0(Angle)으로 복구, 공백이면 NAME/VALUE. 단위 테스트 4개 추가(292). 실기: 정상 상태에서 configure 2회 `already`(비회귀만, `-` 경로는 실기 재현 불가로 미검증).
- **스펙 3 릴리스 준비 구현(2026-10-21 00:00~00:20, Sonnet 7커밋 + 보정 1커밋, main 7d17fdc)**: requires-python ≥3.12(python-rtmidi 휠 범위), `logic_plugin calibrate`(force 필요), 서버 instructions·version, `scripts/smoke_stdio.py`, `docs/troubleshooting.md`, README 설치 3경로, CHANGELOG, 테스트 워크플로. 검증: 3.14·3.12 각 295 테스트, 빈 캐시에서 `uvx --from git+…` 설치 21초 뒤 initialize ok, `claude mcp add` → Connected, Actions 첫 실행 통과(1m43s). v0.1.0 태그는 사용자 확인 뒤.
- 다음: 스펙 3(공개 릴리스 준비). 수정 후보: `configure`의 값 표시 판정(`-`·`Ch Out`, PAN 파라미터 복구, Z17), `플러그인 윈도우 열기/닫기` 해제 뒤 Z16 재측정.
- 미검증 경로 자리.
- 다음: 스펙 3(공개 준비: GitHub 원격, 설치 문서, 악기 슬롯 검토).

## 실전 사용 교훈 (2026-10-24, guitartone 프로젝트에서 기타 톤 배치)
배경: 사용자의 실제 프로젝트(저장 안 함)에 트랙 1·2 체인과 Bus 1·2 센드, Aux 두 개의 딜레이·리버브를 MCU로 배치. 명령은 서버가 아니라 `build()`로 직접 호출(스크래치 스크립트, 몇 시간 뒤 폴더 비워져 소실).
- **삽입 위치 캐시 불일치(F1)**: 캐시 목록(126개, 10/24 03:01 재스캔)과 이 프로젝트의 메뉴 순서가 달라 `insert`가 위치 58에서 'Tremolo'를 봄(기대 Channel EQ). 모노·스테레오 트랙은 메뉴 항목 수 자체가 다름(10/19 163개 vs 10/24 126개). 해결: `--`로 되감은 뒤 1틱씩 오버레이를 읽어 이름이 맞을 때 확정하는 by-name 삽입(58~111틱 안에 찾음, 9종 모두 verified). → `insert`에 이름 탐색 폴백을 넣을 만함.
- **Aux 스트립(F2)**: 트랙이 없는 Aux는 Plug-in Channel 뷰가 따라가지 않음 — `plugin list`가 Aux 스트립에 **선택된 트랙의 슬롯을 그대로 보고**(오인), `insert`가 선택 트랙 슬롯 1에 들어감(Tape Delay가 트랙 1에 삽입돼 제거). Plug-in Mixer 뷰(V-Pot n = 스트립 n의 슬롯 1)로는 삽입 성공(Tape Delay·ChromaVerb). 그러나 편집 뷰는 선택 트랙 슬롯을 열어(`empty_edit`) Aux 플러그인 파라미터는 못 만짐. `StripKinds.follows`는 Aux를 지원으로 판정(Output 열 있음) → Aux 전용 판정 필요.
- **슬롯 1 편집 불일치(F3)**: 트랙 1 슬롯 1(Tape Delay, Overdrive)은 `press_vpot` 뒤 `empty_edit 1`로 두 번 실패했는데, 트랙 2 슬롯 1(Noise Gate)은 정상. 원인 미확인.
- **enum·매핑 결함(F4)**: Compressor `Circuit Type` 번들 options가 중복('Vintage','VinOpt' 반복)이고 `set_enum`이 'Studio'만 반복 관측 → 실패. Compressor/Noise Gate `Release`는 번들 map이 linear(5~5000)인데 실제는 로그형 → 6회 안에 못 맞추고 프로빙도 실패(130 ms에서 복원). Channel EQ `Low Shelf Gain`은 기본 허용 오차 0.1 dB가 페이더 분해능보다 좁음(+3.2에서 실패, 0.3이면 성공). `page_to` 커서 무응답 1회(Z13 재현).
- **센드 생성 뒤 스트립 이동(S5 재확인)**: Bus 1·2 센드로 Aux1·Aux2 자동 생성, 트랙 2를 만들자 Aux가 스트립 5·6으로 밀림. 스트립 번호를 하드코딩한 패치가 트랙 2를 Aux로 오인(`mixer: 기대 slot 1`).
- **프로젝트 메인 윈도우 닫힘(Z18)**: 세션 중 메인 윈도우만 닫히고 프로젝트·플러그인 창은 남는 현상 2회(03시, 07시). MCU에는 창 닫기 명령이 없음. ⌘1로 복구. 원인 미확인(Z11과 같은 현상일 수 있음).
- 사용 쪽 메모: NAM 플러그인 0.7.13은 2026년 TONE3000 캡처(version 0.7.0 SlimmableContainer)를 못 읽음 → TONE3000 공식 플러그인(AU `aumf T3K0 TFTF`)으로 해결. TONE3000은 프로젝트 재열기 뒤 캡처를 잃기도 함(클린+잡음).
- 다음 후보: ① `insert` 이름 탐색 폴백 ② Aux 스트립 판정·안내 ③ Release 로그 매핑 재수집 ④ by-name 삽입·ops 러너를 `scripts/`로 승격.

## 스펙 4: 실전 수정 (2026-10-27)
- 설계 `docs/superpowers/specs/2026-10-27-field-fixes-design.md`, 계획 `docs/superpowers/plans/2026-10-27-field-fixes.md`. Opus 구현 6커밋 → Opus 최종 리뷰 1회(7건) → 수정 6커밋 → 실기에서 2건 추가(Mixer 뷰 슬롯 유도, 축약명 부분수열 검사) → 327 테스트.
- 내용: F1 `insert` 이름 탐색 폴백(note `name_scan:<틱>`, 캐시에 없는 이름은 접두 일치) / F2 Z19 Input 열로 track·aux·output 판정, Aux는 PL·SE·EQ 명령 skipped(`StripAux`), 슬롯 1 삽입·제거만 Plug-in Mixer 뷰(`after.path="mixer"`), `list`는 Aux 행 슬롯 1만 + `after.aux` / F4 허용 오차 dB 0.2·2 %·보정 10회 / F5 `plugin move`(제거+재삽입, 설정 초기화, 헤더 이름 기준·캐시 목록에 있어야 함) / 리뷰 추가: 편집 뷰 헤더 `Track n`과 스트립 번호 대조(분류 실패 시 fail-closed), `move` 재삽입 예외 시 이름 보존, `list`가 Aux 읽기 실패에도 트랙 행 유지, 축약명은 이름의 부분수열일 때만 학습(load 때 불량 항목 제거).
- 실기(2026-10-27, guitartone 프로젝트, 저장 안 함): ① 트랙 1 슬롯 5 `insert "Channel EQ"` → `name_scan:75` verified, remove verified(2회). ② 슬롯 5 편집 직후 뱅크 `list` → 1차는 "Mixer 뷰 슬롯이 5"로 unverified(트랙 행은 유지) → 슬롯 1 유도 수정 뒤 verified, Aux1 `TapDel`·Aux2 `ChrVer`, `aux: [5, 6]`. Aux 슬롯 2 insert·`eq get` skipped(Z19 note). 이 프로젝트의 축약명 오학습(`Tuner`→Channel EQ 등 7개)은 부분수열 규칙으로 더 이상 학습되지 않고 `name: null`로 보고(reveal 오버레이가 이웃 항목을 보이는 원인은 미해결).
- 실기 ③④(2026-10-27 13:20, 빈 테스트 프로젝트 "무제 2", 오디오 트랙 1개, Logic 12.0.1, `scripts/live_check4.py 1` 2회): 2회 모두 ①②③④ 전부 verified. ① slot 1 insert `name_scan:75`(캐시 위치 없음 → 이름 탐색) ② 뱅크 list `aux: []`, `unsupported: [2, 5]`(빈 프로젝트의 출력·Master 스트립; 뱅크에 스트립 1·2·5만 보고됨) ③ Low Shelf Gain 3 dB: 1회차 `fader` 경로 +3.0 dB, 2회차 +2.9 dB(허용 0.2 안, 옛 0.1이면 실패했을 값) ④ move s1→s2·s2→s1 되돌림 모두 verified(설정 초기화 note). 스크립트는 빈 트랙이면 ①의 Channel EQ를 ③④용으로 남겼다가 끝에 제거하도록 수정.
- 미검증: Aux 센드·EQ 추종 여부는 가정(미측정). Input이 `Bus`가 아닌 Aux는 헤더 대조로만 막힘. move는 설정값 있는 플러그인·슬롯 2 이상 사이의 이동은 실기 안 함(빈 트랙에서 s1↔s2만).
- **파라미터 set 범위 점검(22:46, "무제 2" 스트립 1 슬롯 1, 1회, 스크래치 pcheck.py·pcal.py·pprobe.py)**: 표 없는 플러그인(Chorus·Tremolo·Limiter)도 `params`가 페이지를 읽고 숫자 파라미터는 프로빙으로 set verified(Chorus Mix 15 %·Intensity 5 %, Tremolo Depth 50 %, Limiter Gain +1.0 dB·Lookahead 2.5 ms). 번들 map 없는 항목도 프로빙으로 성공: Channel EQ Low Shelf Q 1.50·Master Gain 1.8 dB(목표 2.0, 허용 0.2), Compressor Gain 3.0 dB, Stereo Delay Left Mix 30 %. 안 되는 것(전부 Compressor): ① `Release` — 페이더 1→'5.0 ms', 16383→'5000.0'(LCD 6자에서 단위가 잘려 unit None) 이라 `infer_mapping`의 단위 불일치 판정으로 프로빙 실패(중간값 29·160·880 ms = 로그형). 수정 방향: 잘린 단위 허용 + 양수이고 비율 큰 범위는 log. ② `Circuit Type` — 선택지 7개가 LCD에서 'PltDig','Studio','Studio',… 로 겹쳐 `set_enum`·calibrate 모두 'Studio' 반복에서 멈춤(F4 확정; 이름으로는 못 고르고 틱 횟수 지정이 필요). ③ `Auto Gain`은 bool이 아니라 Off/-12dB/0dB 3단 enum(True→'On' 실패는 입력 문제). 부수: Chorus 'Intensity'가 'Intensi'/'ty' 두 칸으로 읽혀 표에 쪼개짐(파라미터 적은 1페이지의 긴 이름), Tremolo Rate는 동기 모드면 '1/4'(enum 경로).

## 스펙 4b: set 고장 수정 (2026-10-28, 브랜치 fix/set-failures, Opus 구현 3라운드 + Fable 마진 수정·재수집, 343 테스트)
- 계획 `docs/superpowers/plans/2026-10-27-set-fixes.md`. 내용: ① `infer_mapping` 잘린 단위 허용(양쪽 텍스트가 LCD 6칸을 채우고 짧은 단위가 긴 단위의 접두/None) + 양수·비율 100 초과는 log ② enum `"#n"` 번호 선택(되감기 16틱 뒤 n−1틱), 표에서 이름이 하나면 현재 위치와의 차이만 틱, 겹치면 skipped로 `#i` 안내, 숫자 파라미터에 `#n`은 skipped ③ calibrate 선택지 수집을 고정 횟수로(뒤쪽 동일 반복만 제거) ④ `set_enum` 틱 뒤 읽기 전 오버레이 대기 ⑤ `OVERLAY_MARGIN_S` 0.05→0.5.
- **오버레이 실측(2026-10-28, 무제 2, 스크래치 ptimeline.py)**: enum 틱마다(끝에서 안 움직이는 틱 포함) 21칸 값 오버레이('Vintage Opto')가 틱 뒤 ≈2.0~2.1 s 보이다 축약('VinOpt')으로 재묘사. 2.05 s 대기는 경계에 걸려 읽기가 둘을 번갈아 잡음 → 번들의 'Vintage','VinOpt' 교대 꼬리와 F4의 'Studio' 반복은 모두 이 오버레이 읽기였고 실제 선택지는 겹치지 않음(Circuit Type 7개: PltDig·StudoA·StudoT·ClsscA·VintgA·VintgT·VinOpt). 0.5 s 마진으로 재수집하면 깨끗함.
- 재수집(--write): Compressor(Release log 5~5000, Mode 5개, Auto Gain은 여전히 None), Noise Gate(Release linear 0~10000, Hold 이름 None), Stereo Delay(Delay Time log 5~2000, Mix 채움). 번들 generated 2026-10-28 → 옛 사용자 캐시 표는 번들 이름에 대해 무효(M2 규칙).
- 실기(01:01까지, 무제 2, 각 1회, 스크래치 pset2.py·pset3.py): Compressor Release 100→100.0 ms·1000→980 ms, Circuit Type `#6`→VintgT(19 s)·`StudoT`(8.8 s)·`ClsscA`(8.4 s)·같은 값 재지정 already, Auto Gain `0dB`, Release에 `#2`→skipped, Noise Gate Release 500→509.8 ms, Stereo Delay Left Delay Time 500→496 ms, Limiter(표 없음) Soft Knee Off/On — 전부 verified.
- 비용: enum 텍스트 경로·EQ 슬로프 set이 단계당 ≈2.5 s 느려짐(정확한 읽기의 대가), calibrate는 enum당 ≈30 s 증가(도구 설명 2~30분). 미검증: `#n`은 항상 되감기(차이 경로 안 씀), 'Vintage Opto' 외 긴 오버레이 이름은 같은 패턴이라고 가정, Space Designer 재수집 안 함.

## 번들 표 수집 2차 (2026-11-10~11, 사용자 프로젝트 "프로젝트 1" 트랙 1 슬롯 2, scripts/calibrate_batch.sh, 저장 안 함)
- 결과: 번들 10종 → **67종(1,064 파라미터, map 없음 119)**. `known.json`의 `list` 67개 전부에 표가 있다. 1차(11/10) 20개 중 16개, 2차(11/11) 41개 중 41개(EVOC 20 TrackOscillator는 3번째 시도) verified. 2차 소요 합계 247분, 가장 긴 것은 Pitch Correction 27분·Multipressor 16분·Linear Phase EQ 16분. 전부 `caffeinate -i` 아래에서 돌림.
- 1차 미해결(Multipressor 이름 탐색 실패, Delay Designer·Linear Phase EQ page_to 커서 무응답, Match EQ name_value 무반응)은 컨트롤 서피스 재설치 뒤 재시도에서 전부 한 번에 통과. 원인은 플러그인이 아니라 Logic 재실행 뒤 남은 CS 그룹 상태(표시 모드 "이름")였다. 복구 절차: Logic Pro → 컨트롤 서피스 → 설정… 캔버스에서 Mackie Control 장치만 삭제(MPK는 손대지 않음) → 서버 포트를 열면 Logic이 자동 재설치 → LCD 2행에 팬 값이 보이면 configure 통과.
- 코드 수정 1건: scan 목록 이름이 오버레이 21칸에서 잘린 `EVOC 20 TrackOscillat`는 삽입 뒤 헤더의 전체 이름 `EVOC 20 TrackOscillator`와 접두가 거꾸로라 insert가 unverified로 끝났다(플러그인은 들어감). 헤더 이름이 목록 이름의 연장이면 받아들이고 전체 이름을 쓰도록 수정(테스트 `test_insert_accepts_a_list_name_truncated_to_the_overlay`, 344 테스트).
- page_to 커서 무응답(Z16 패턴)은 EVOC 20 TrackOscillator 2번째 시도에서도 한 번 나왔다(페이지 3). 재시도로 지나가는 일시 현상이며 원인은 미확인. 실패하면 플러그인이 슬롯 2에 남을 수 있으니 수집 뒤 `plugin list`로 확인.
- 맥이 덮개 닫힘·배터리로 유지 절전에 들어가면 수집이 60~84분씩 걸리고 서피스 상태가 깨진다(11/10). 긴 수집은 `caffeinate -i`로 감쌀 것.
- 11/10 사용자 결정: "Logic은 MIDI만, UI 클릭·AX·포커스 뺏기 금지" 규칙 해제. 유지: MPK mini IV 서피스 항목 금지, 기본값 재형성 금지, 사용자 프로젝트 저장 금지, Logic 실행 금지.

## 리팩토링 + 실기 검증 결함 수정 (2026-11-11, 브랜치 refactor-plugin, Opus 구현 2회 + Opus 리뷰 2회, 367 테스트)
- 실기 검증(bundle_check.py, 트랙 1 슬롯 2, 저장 안 함): Silver Compressor·GoldVerb·Vocal Transformer 삽입→params/get/set→제거. 통과: 번들 이름 채움, GoldVerb Mix 페이더 1회 verified, Robotize On·Pitch Base `#3` verified. 결함: ① 구형 플러그인이 파라미터 하나를 LCD 두 칸에 그림(`Thresho`|`ld`, `Frequen`|`cy`) → 뒷칸이 유령 파라미터(14개 표) ② Ratio `2.0  :1`이 숫자로 안 읽힘 ③ 범위 밖 목표(Room Size 1500, 표 10~200 m)가 "틱 반응 없음"으로 끝남. 구현자가 찾은 기존 결함: ④ On/Off 파라미터에 0/1이 "1"로 바뀌어 절대 안 맞음 ⑤ 텍스트 경로 실패 시 파라미터가 최대 16틱 움직인 채 남음.
- 리팩토링(동작 변화 없음): plugin.py 851 → 650줄. Aux Mixer 슬롯 1 경로 → `plugin_mixer.py`(AuxMixer), calibrate·scan → `plugins/calibrate.py`, set 공통 로직 → `setter.coerce/set_option/verdict`(plugin.set·eq.set 공용). 리뷰 1차: main·HEAD에 같은 시나리오 1,028개를 fake Logic으로 비교해 994개 동일, 나머지 34개는 손으로 망가뜨린 map에서만 차이 → `_map_from`을 관대하게(리뷰 A1), options 없는 enum map은 "표 없음"으로 간주(A2, 의도된 변경).
- 결함 수정 5건 + 리뷰 2차 M1(값도 넘침 `12000 H`|`z`) → `pair_columns()`: 축약명이 7자로 칸을 채우면 다음 칸 이름을 잇고, 값이 7자로 칸을 채우면 다음 칸 값을 잇는다. 14개 표 재수집 23분 → 유령 24개 제거(1,064 → 1,040 파라미터), Threshold·Frequency·Distortion Type·Q-Factor 이름 복원.
- 남은 한계: `read_value`·프로빙은 한 칸만 읽어 두 칸 값의 단위가 잘린다(`20000 H`) → Parametric EQ·Exciter·Low/High Pass Filter `Frequency`는 map 없음·숫자 set 불가. Tuner `Output`|`Mute`는 공백으로 갈려 6자라 병합 규칙에 안 걸림(유령 `Mute` 1개 잔존). 캘리브레이트는 기존 map을 다시 프로빙하지 않아 손으로 고친 map은 영구히 남는다.
- 최적화 관찰: bundle_check의 삽입 3회가 모두 캐시 위치 불일치 → 이름 탐색(43·44·84틱). 프로젝트마다 메뉴 순서가 달라 매번 처음부터 훑는다.

## 묶음 set 사전 실기 측정 (2026-11-19 14:27~14:48, "testForMcp_1" 트랙 2 슬롯 1 Compressor, Logic 12.0.1, 저장 안 함, 코드 변경 없음)
- **방법**: 계획 문서의 묶음 순서(뷰 진입 1번 → 항목 사이 `settle_overlay` → `flip(False)` → `toggle_name_value`)를 기존 내부 함수로 흉내 낸 임시 스크립트(스크래치 `batch_proto.py`·`live_plugin.py`·`live_diag.py`·`live_lcd.py`, src 변경 없음)와 기존 `plugin.set`을 실제 Logic에서 호출. 시간은 호출 바깥에서 잰 체감 시간(wall)과 `elapsed_ms`를 함께 기록.
- **낱장 숫자 set(유효 구간, 값이 바뀌고 verified인 호출 10회)**: 체감 6.6~7.7 s. `already` 13회는 6.2~6.6 s. 10회 보정을 다 쓰고 실패한 호출 3회는 10.7 s. 프로세스 첫 호출은 19~26 s(스트립 종류 판정 포함, 2.5 s 대기 8번). 호출마다 2.5 s 대기 2번(합 4.9 s)으로 가짜 시계 측정과 같다.
- **`elapsed_ms`가 체감보다 2.7~2.9 s 짧다(모든 호출)**: 결과를 만든 뒤 `_guarded`의 `finally`에서 PAN으로 돌아가는 시간이 빠진다. 결함은 아니지만 모델·사용자에게 보이는 숫자가 실제보다 작다.
- **묶음 순서(유효 1회)**: `[Rel=100(프로빙 포함), Thrs=-30]` 한 번 진입으로 둘 다 verified, 체감 10.1 s(2.5 s 대기 3번 = 7.2 s). 같은 두 값을 낱장으로 보내면 ≈13.7 s. 여기서 항목 사이 비용 ≈2.6 s. 외삽(측정 아님): 숫자 8개 낱장 ≈55 s → 묶음 ≈29 s. **6·8개 묶음 시간, EQ, 선택지 섞기, 오버레이 타임라인은 못 쟀다**(아래 무효 구간).
- **첫 실패에서 멈춤(유효 3회)**: `[Thrs, Rel=300, …]`에서 둘째가 실패하면 거기서 멈추고 뒤 항목을 `remaining`으로 돌려준 뒤 PAN 복귀(체감 14.0 s, 14.0 s, 13.9 s). 순서 자체는 계획대로 동작.
- **결함 ①: 닿을 수 없는 값에서 10회를 다 쓰고 실패한다(낱장도 같음)**. 컨트롤 서피스로 보이는 파라미터는 단계가 거칠다.
  - Release: 페이더 에코가 단계에 달라붙는다(raw 9640~9720 → 에코 9637 = 290 ms, 9760~9840 → 9774 = 310 ms. 단계 ≈137 raw, 전체 ≈120단계). 틱 한 칸도 160 → 170 → 180, 310 → 330 → 350. 목표 300(허용 오차 6.0)은 5회 중 5회 실패(낱장 2 + 묶음 3): 290 ↔ 310을 10번 오가며 4.5 s를 쓰고 `unverified`.
  - Ratio: raw 1·2048·…·16383에서 1.0·1.6·2.3·3.6·5.6·8.3·13·19·30. 로그 곡선인데 번들 표는 `linear 1~30`. 틱은 5.4·5.6·5.8·6.1·6.3. 목표 4.0(허용 0.08)은 3.9에서 끝남(1회 중 1회 실패).
  - Attack: 0·6.5·12.5·19·50·89·125·164·200(구간별 곡선, 번들은 `linear 0~200`). 단계 26·29·32·35·38. 목표 30(허용 0.6)은 32에서 끝남(1회 중 1회 실패).
  - 실패하면 코드가 표의 map을 지우고 저장한다 → 다음 호출이 프로빙(값을 최소·최대로 한 번씩 보냄)하고 같은 `linear`를 다시 추정한다. 원인은 표가 아니라 단계 폭인데 표를 지운다.
  - 영향: 묶음은 "첫 실패에서 멈춤"이라 Ratio 4, Attack 30, Release 300 같은 흔한 값이 들어가면 그 항목에서 멈춘다. 묶음보다 먼저(또는 같이) 고쳐야 한다.
- **결함 ②(1회 관측, 원인 미확인, 재현 안 함): 다른 페이지의 파라미터에 값이 들어갔다**. 14:42~14:44(덮개 열림) 진단 스크립트가 set과 같은 경로(`_open_edit` → `_goto_param` → `flip(True)` → `fader`)로 Release(1페이지 5열)에 페이더를 보냈는데 에코 10922·값 `Hard`가 돌아옴 = 2페이지 같은 열의 Distortion. 다음 페이더부터는 Release가 맞게 읽힘. 끝난 뒤 그 Compressor의 Distortion은 `Clip`(새로 넣은 Compressor 기본값은 `Off`: 트랙 4에 넣어 확인). 의도하지 않게 바뀐 값은 이것 하나(나머지 비대상 항목은 기본값과 같음). 그날 편집 뷰 진입 약 45회 중 1회.
  - 추정: `probe_pages`·`page_to`가 누른 커서가 늦게 처리됨(커서 지연은 10/20에도 실측). `page_to`는 열 내용이 바뀌면 페이지가 넘어갔다고 보는데, `Page n/N` 토큰이 사라지는 것도 열 변화다. 확인하려면 LCD·버튼 이벤트 로그가 필요.
  - 막을 방법의 근거(LCD 덤프): 편집 뷰 VALUE 모드에서 1행은 축약명이다(`CirTyp Thrs   Ratio  Attack Rel    AutRel      Page 1/3`, 7·8열은 토큰이 ≈2 s 가림). 값을 보내기 직전에 그 열의 1행 이름을 확인할 수 있고, 보낸 뒤에는 오버레이 1행의 이름(`read_overlay_name`)으로 실제로 바뀐 파라미터를 확인할 수 있다(뒤쪽은 코드 근거, 이번에 직접 덤프하지 않음).
- **무효 구간(14:48:15 이후)**: 맥 덮개가 닫혀(배터리) `Clamshell Sleep` 뒤 약 45초마다 잠들었다 깨기를 반복(`pmset -g log`). 이 구간의 현상 — `focus: SELECT LED 변화 없음`이 한 번 걸러 한 번, 묶음 1회가 끝난 뒤 2분 정지(14:52:34~14:54:34 절전과 일치) — 은 Logic·서버 탓으로 볼 수 없다. 14:46~14:48의 focus 실패 1회는 덮개 전후가 불분명해 판정 보류. **실기 측정 전에 `pmset -g log`·`ioreg -r -k AppleClamshellState`로 절전 여부를 먼저 본다.**
- **남긴 상태**: 프로젝트(저장 안 함)에 시험용 Compressor 2개(트랙 2 슬롯 1: 값 바뀜, 트랙 4 슬롯 1: 기본값)와 선택 트랙 변경이 남아 있다. 절전 중에는 조작이 위험해 제거하지 않았다. 사용자 캐시 `~/.logic-mcp/plugins-12.0.1.json`에 생긴 Compressor 항목(Ratio·Attack map = null)은 지워 측정 전 상태로 되돌림.
- **잘못된 프로젝트에 돌린 실행(15:09:16~15:11, 절전은 없었지만 측정으로는 무효)**: 덮개를 다시 연 뒤 열린 프로젝트를 확인하지 않고 낱장 시간 측정 스크립트를 돌렸다. 그 사이 사용자가 "testForMcp_1"을 닫고 실제 작업 프로젝트(guitartone)를 열어 두었다. 14회 전부 트랙 2 슬롯 1(그 프로젝트에서는 Tuner) 편집 뷰 진입에서 `edit: 기대 plugin_edit 슬롯 1, 관측 empty_edit 1`로 실패했고 값은 하나도 보내지 않았다(첫 호출 체감 22.3 s, 이후 7.0 s). 선택 트랙은 바뀌었을 수 있다. 부수 관측: Tuner가 든 슬롯은 편집 뷰가 빈 슬롯처럼 보인다(1개 프로젝트, 원인 미확인). **실기 전에 Logic 창 제목(열린 프로젝트)과 대상 스트립 이름을 매번 확인한다**(절전 점검과 같이).

## 실전 사용 (2026-11-19 15:16~15:31, guitartone 트랙 2, 톤 조정, 저장 안 함, 코드 변경 없음)
- **한 일**: 사용자 요청 3건(EQ, 공간계, 노이즈 게이트)을 제품 경로(`commands.eq.set`, `commands.plugin.set`·`bypass`, `commands.send.set_level`)만으로 처리. 스크래치 스크립트가 `build()`로 만든 `commands`를 직접 호출했다(MCP 도구와 같은 코드, 모델 왕복만 없음).
- **결과**: 쓰기 17회 전부 verified(Channel EQ 값 6, Tape Delay 값 4 + 바이패스 해제 1, 센드 레벨 1, Noise Gate 값 5). 읽기 7회 중 1회 실패: 센드 읽기 직후 `plugin.params` 슬롯 8이 `edit: 기대 plugin_edit 슬롯 8, 관측 pan`, 바로 다시 하니 성공(1회 관측, 원인 미확인).
- **묶음 크기**: 실제 요청은 플러그인 하나에 값 4~6개씩이었다. 묶음 set 계획이 줄이려는 경우와 같은 모양이다.
- **단계 폭(위 결함 ①과 같은 현상, 허용 오차 안이라 verified)**: EQ Frequency 목표 1000 → 990 Hz, Noise Gate Release 목표 400 → 397.4 ms.
- **시간(1회)**: Noise Gate 숫자 5개를 한 프로세스에서 낱장 5번 = 15:29:50~15:30:57(≈67 s, 프로세스 시작과 첫 호출의 스트립 판정 포함).
- **쓰지 않은 것**: 노이즈 게이트 Threshold를 실제 잡음 크기를 재지 않고 정했다(사용자가 듣고 고쳐야 한다). 서버는 MCU 미터 메시지(4비트 값 0~15, `strips[ch].meter`, 스트립 상태의 `meter`)를 이미 받고 있는데 쓰지 않았다. 이 값이 dB로 얼마인지, 게이트 문턱을 잡을 만큼 촘촘한지는 미확인.

## 늦은 커서 결함(위 결함 ②) 원인과 수정 (2026-11-20, 브랜치 `fix/late-cursor` 2164ef4. 실기 확인과 머지는 아래 11/21 절)
- **원인**: Logic이 Cursor ◀▶ 누름을 몇 초 늦게 처리할 때가 있다(실측 Z16·Z17, 최대 3.8 s). 드라이버의 판단 두 곳이 그 사이에 틀린다.
  - `probe_pages`: ▶·◀가 각각 0.6 s 안에 LCD를 안 바꾸면 "1페이지"로 본다. 그 뒤 늦은 ▶가 처리되면 Logic은 2페이지, 드라이버는 1페이지라고 믿는다.
  - `page_to`: 열 내용이 바뀌면 페이지가 넘어갔다고 본다. NAME 모드 헤더의 `Page n/N` 토큰은 누름 뒤 ≈2 s에 사라지고(아래 실측), 그때 1행만 바뀐다. 이것을 이동으로 세면 늦은 누름을 처리된 것으로 친다.
  - `_goto_param`은 화면을 보지 않고 `index → 페이지·열` 계산만으로 열을 정한다. 그래서 믿는 페이지가 틀리면 같은 열의 다른 파라미터를 읽고 쓴다.
- **근거**
  - 11/19 진단 출력: 첫 페이더가 `Hard`(Distortion, 2페이지 5열)로 갔고, 둘째 페이더의 에코가 8122·`150.0 m`(직전에 남겨 둔 Release 값)였다. 드라이버 조작 없이 페이지가 1로 돌아온 것 = 늦게 처리된 커서 누름.
  - 가짜 Logic 재현(코드 변경 없이, 표가 있는 Compressor, 첫 커서 누름만 지연): 지연 0.8~3.8 s에서 `set Rel=100`이 Distortion을 `Hard`로 바꾸거나 Distortion 선택지를 훑었다. 0~0.4 s와 4.5 s는 정상.
  - 실기 재현(11/20 16:50, main 0049f28, testForMcp_1 트랙 2 Compressor, 첫 ▶ 누름을 2.0 s 늦게 전달): `set Rel=300`의 결과가 `after 'Clip'`, note `V-Pot 틱에 LCD 반응 없음`. 보정 틱이 Distortion 열로 갔다(이미 끝값 `Clip`이라 값은 안 바뀜). 지연 1.4 s·1.6 s에서 페이더 한 번에 끝나는 set(Rel=150·100)은 늦은 누름보다 먼저 끝나 정상(각 1회).
- **수정(Opus 구현, 가짜 Logic 테스트 367 → 377, 기존 테스트 변경 없음)**
  - `probe_pages(expect)`: 무반응이면 `CURSOR_LATE_S`를 더 기다린다. 표가 1페이지면 누르지 않는다. 여러 페이지인데 끝까지 무반응이면 ModeError.
  - `page_to`: 토큰이 다른 페이지 번호를 보이거나 2행이 바뀔 때만 이동으로 본다.
  - 페이지 확인 가드: `_goto_param`이 그 페이지의 축약명(VALUE 모드 1행)을 표와 비교하는 확인을 `ModeDriver.guard`에 걸고, `fader`·`tick`이 보내기 직전마다 부른다. 틀리면 3 s 기다린 뒤 ModeError(보내지 않음). 가짜 Logic에 `page_token_ttl_s`(토큰 만기) 추가.
- **실기 실측(11/20 16:43~16:45, testForMcp_1 트랙 2 Compressor, 읽기만)**
  - 토큰 수명: NAME 모드 ▶·◀ 뒤 2031·2035 ms에 헤더가 토큰 없는 형태로 돌아가고 1행만 바뀐다. VALUE 모드도 2026·2033 ms.
  - VALUE 모드 1행은 그 페이지의 축약명이다. 1페이지 `CirTyp Thrs Ratio Attack Rel AutRel MakeUp AutGai`, 2페이지 `Knee Peak/S LimrOn LimThr Distrt Mix SiChDe State`. 페이지 이동 뒤 ≈2 s 동안 7·8열을 토큰이 가린다.
  - 마지막 페이지는 끝에 맞춰진다: 3페이지가 `Distrt Mix SiChDe State Mode Freq Q Gain`(13~20번째)이고 표는 뒤 4개를 index 21~24로 갖는다. 앞 4열은 2페이지와 겹친다(가드는 표에 이름이 있는 열만 비교하므로 맞다).
- **닿을 수 없는 값(결함 ①)의 다른 방법: 없음**. Apple 문서의 CMD/ALT 고해상도 모드를 실기로 확인: ALT(0x49)·SHIFT·CONTROL을 누른 채 V-Pot 틱의 한 칸은 보통 틱과 같다(Release 210 → 220 → 230 → 240 → 260 → 270 → 290 → 310, Ratio 0.2~0.3씩, Attack 3 ms씩). Release 눈금에는 200·250·280·300이 없다. 페이더도 같은 눈금에 붙는다(11/19). → 컨트롤 서피스로는 가까운 값이 한계다. 끝내는 방식(가까운 값으로 성공 대 실패)은 사용자 결정 대기, 미구현.
- **못 한 것(사용자가 기타를 쳐야 해서 16:50에 중단)**: 수정 브랜치의 실기 확인(Compressor·Space Designer·두 칸 파라미터 플러그인에서 가드가 정상 호출을 막지 않는지, 늦은 ▶ 전달 시 막는지), 결함 ① 조기 종료 수정, 묶음 시간 측정. 16:49:50의 `set`·`get` 2회가 `track_menu: 기대 항목 0 = 'Volume', 관측 pan ''`로 실패(프로세스 첫 호출, 1회 관측, 원인 미확인).
- **사고 기록**: 16:39 `open`으로 testForMcp_1을 열자 Logic이 "닫지 않음" 선택지 없이 열려 있던 사용자 프로젝트를 닫으며 저장 여부를 물었고, 그 창은 스크립트가 누르지 않았는데 1~2초 안에 닫혔다(프로젝트는 저장되지 않고 닫힘, 파일은 전날 17:01 저장본 그대로). **사용자 프로젝트가 열려 있으면 다른 프로젝트를 직접 열지 않는다. 사용자에게 바꿔 달라고 한다.** 플러그인 윈도우도 subrole이 AXDialog라 "대화상자 찾기"는 버튼 이름과 문구로 가려야 한다.
- **남긴 상태**: 테스트 프로젝트는 저장 안 함(파일은 11/19 15:08 그대로). 사용자 캐시는 측정 전 백업으로 되돌림. 수정 브랜치 작업 폴더는 `.claude/worktrees/agent-a13e98a26d2632c55`.

## 늦은 커서 수정 실기 확인 + 결함 ③④ 수정 + 결함 ⑤ 발견 (2026-11-21 17:51~18:42, 11/25 02:24~04:09, "testForMcp_1", Logic 12.0.1, 저장 안 함, 브랜치 `fix/last-column-overlay`, 383 테스트)
- **방식**: 사용자가 guitartone을 저장하고 닫은 뒤(17:48) testForMcp_1을 열어 줬다. 사용자 지시로 실기 실행과 구현은 하위 에이전트가 했다(Opus 실기 디버깅 1, Sonnet 코드 1, Sonnet 실기 실행 2). Fable은 계획·diff 검토·브랜치 합치기·기록. 실기는 한 번에 한 프로세스만, 실행 스크립트가 매번 열린 프로젝트 이름과 절전·덮개를 확인했다. 실측 원문은 `docs/mcu-protocol.md` Z20~Z23.
- **늦은 커서 수정 확인(수정 브랜치, 트랙 2 Compressor·트랙 1 Space Designer·트랙 3 Chorus)**
  - 정상 호출이 가드에 막히지 않음: Compressor 읽기 7·쓰기 5, Space Designer(1·2·12·22·23페이지) 읽기 8·쓰기 1, Chorus(1페이지, 두 칸 이름) 읽기 5·쓰기 2.
  - 첫 ▶ 누름을 1.0·2.0·3.0·4.5·8.0초 늦게 전달: 5건 모두 Release에 들어갔고 Distortion은 그대로(각 1회). main은 11/20에 2.0초 지연에서 Distortion 열로 갔다.
  - 가드: 대상 열에 선 뒤 드라이버 모르게 ▶를 보내고 0.3초·2.6초(2회) 뒤 틱 시도 → 3회 모두 3.0초 기다린 뒤 `guard` 오류, 값은 보내지 않음.
  - 소요 시간은 main과 같다(두 브랜치 2회씩): get 5.8~6.0초, 숫자 set 6.2~6.5초, 프로세스 첫 호출 ≈21초.
- **가드 strip 결함(가짜 Logic에서 발견, 실기 전)**: 두 칸 축약명이 칸 경계에 공백을 두면(`Lo Cut `|`Freq`) strip한 LCD 칸과 안 맞아 정상 호출이 막혔다. 기대 이름도 strip해서 비교하도록 수정.
- **결함 ③ 마지막 열 값 오독(main에도 있던 결함, Z22)**: 8열의 값 오버레이는 오른쪽 정렬로 열 7에 넘치는데 `read_value`가 열 칸만 읽어 `-24.0 dB`를 `4.0 dB`로 읽었다. `set Gain=3`이 실제 23.0 dB에서 `verified '3.0 dB'`를 보고했고, 번들 표 Compressor `Gain`이 0~4로 들어가 있었다(실제 −24~+24). → 마지막 열은 2행 42~55칸이 숫자 하나로 읽히면 그것을 쓴다(Sonnet 구현 + Fable이 1행 조건 제거: 긴 이름 오버레이가 열 7을 덮으면 조건이 틀렸다). 수정 뒤 실기: 페이더 1·8191·12287·16383과 틱 2회의 읽기가 LCD와 일치, `set Gain=3·-12·0`이 verified이고 뒤이은 get과 일치(각 1회).
- **결함 ④ 편집 뷰가 직전 플러그인의 페이지로 열림(main에도 있던 결함, Z23)**: Compressor를 3페이지에 둔 뒤 1페이지짜리 Chorus를 열면 빈 슬롯 화면이 보여 `empty_edit`로 실패했다(수정 전 연속 8회). Opus가 원인을 찾고 `_open_edit`에 Cursor ◀ 한 번 복구를 넣었다. 실기: Chorus 복구 2회 관찰, Space Designer 23페이지 뒤 Compressor(3페이지)는 복구 없이 열림(2회).
- **번들 표 마지막 열 범위 재측정(11/25 02:24~03:20, 트랙 5 슬롯 1에 넣었다 뺌, Sonnet 실행, 전 묶음 절전 0회)**: 대상은 8열(index % 8 == 0)의 숫자·map 없음 항목 89개(32종). Flip 페이더 1·16383에서 오버레이 읽기와 정착 읽기를 둘 다 기록했다. 결과 ok 81, 범위 추정 불가 2(Compressor `AutGai` Off~-12dB, Space Designer `VoDTim` ms↔s), 숫자 아님 3, 가드 거부 3(아래 결함 ⑤). `known.json` 반영 30개(16종): 틀린 범위 14개 수정(Compressor `Gain` 0~4 → −24~24, Tape Delay `DelTim` 0.3~9.9 → 0.3~4999.9, 주파수 `20~0` → 20~20000 4건, ChromaVerb Q 3건 0.1~20000 → 0.1~100, Fuzz-Wah `ComRat` 1~0 → 1~30, AutoFilter `MaiOut` 0~6 → −50~6, Match EQ `Ea-Out`, Space Designer `IROffs` 18.3 → 1.83, EVOC 20 TrackOscillator `Rel` 2~0 → 2~2000) + 빈 map 16개 채움. map 없음 96 → 80. 바뀐 것은 8열 항목의 map뿐임을 diff로 확인. 11/21 1차 시도는 덮개가 닫혀 무효 처리하고 처음부터 다시 쟀다.
  - 반영하지 않은 것: SubBass `Wet`(측정 110~500 %, 처음 값도 110 %라 최소 이동이 먹었는지 불확실, map 없음 유지). Space Designer `X-OvrF`(#128)는 정착 칸이 `16.0 kHz`를 못 담아 정착 읽기가 달랐지만 오버레이 `200 Hz`~`16.0 kHz`로 반영.
  - 남은 수상한 범위(8열 아님, 이번에 안 잼): Space Designer #39 `X-OvrF` 200~16(kHz 단위 잘림), `AnlTop` 3종·DeEsser `Suprss`는 내림 범위(맞는지 미확인).
  - EVOC 20 TrackOscillator는 측정 중 사용자 캐시의 축약 기록이 잘린 이름(`EVOC 20 TrackOscillat`, 스캔 목록의 21칸 이름)으로 바뀌어 `_open_edit`가 그 이름으로 빈 표를 봤다(1차에 기록 0건, 표 이름을 직접 줘서 다시 잼). 측정 전 백업에는 전체 이름이 있었다. 어느 단계가 덮어썼는지는 미확인이고, 실사용에서도 삽입 뒤 번들 표를 못 쓰게 될 수 있다(미수정).
- **결함 ⑤ 번들 표가 스테레오 인스턴스와 안 맞는 플러그인 15종(main에도 있던 결함, 미수정, Z24)**: 재측정에서 가드가 31종 중 3종(Modulation Delay 1페이지, PlatinumVerb·Guitar Amp Pro 3페이지)을 거부했다. Opus 실기 진단(9회): 측정 순서 탓이 아니라 새 인스턴스부터 화면이 표와 다르다. 전수 대조(Sonnet 실행, 값 변경 없음, 66종 삽입): 51종 같음, 15종 다름(13종은 파라미터 묶음이 두 벌, 2종은 좌·우 파라미터). 표는 묶음이 한 벌인 형식에서 수집된 것으로 보인다(모노로 추정, 수집 트랙 형식 기록 없음).
  - main은 위치만 믿으므로 이 15종의 스테레오 인스턴스에서 표와 어긋난 자리를 읽고 쓰게 된다(배치에서 따진 것, main에서 실행은 안 함). 수정 브랜치의 가드는 이름이 다른 페이지를 거부한다. **가드는 엄격한 채로 둔다**: 대상 열 이름만 맞으면 통과시키는 완화를 검토했지만, 이름이 겹치는 둘째 묶음을 가려내지 못하는 경우가 생기고 얻는 것은 Modulation Delay 1페이지·Scanner Vibrato 정도라 넣지 않았다. 근거: 번들 표 902개 페이지 쌍 중 같은 열에 같은 이름이 있는 쌍은 6개(Multipressor·Ringshifter)뿐이라 지금의 "페이지 이름 전체 비교"는 다른 페이지를 확실히 가려낸다.
  - 가드를 넣으면서 잃는 것(main에서는 위치가 우연히 맞아 동작하던 것): 스테레오 Modulation Delay 1페이지 8개(이름 2개만 다름), Scanner Vibrato `Type`·`Depth`.
  - 미확인: 둘째 묶음의 정체(좌·우 채널이면 첫 묶음만 바꾸는 지금 동작은 한쪽 채널만 바꾼다. PlatinumVerb는 두 묶음의 Dry/Wet 기본값이 달라 단순한 좌·우 복사는 아닌 듯), 모노 인스턴스가 표와 같은지.
  - 같이 드러난 것: ① 표가 1페이지면 서버는 커서를 누르지 않는데(11/20 수정), 스테레오에서 2페이지가 되는 DeEsser·DJ EQ가 직전 플러그인의 페이지 위치로 열리면 가드에 계속 걸린다(DeEsser 1회 관찰). ② `_merge_items`는 index가 같으면 같은 파라미터로 보고 이름·map을 남기므로, 배치가 다른 인스턴스에서 페이지를 다시 읽으면(`params`, 표에 없는 이름 조회) 표가 섞인다(코드로 확인, 실기 미실행). ③ Tuner 삽입이 2번 중 1번 실패(`이름 탐색 317틱 뒤에도 못 찾음`).
- **관찰만 하고 고치지 않은 것**
  - Space Designer `Predelay`가 싱크 값(`1/2`)을 보일 때 숫자 `set 40`이 `1/128`로 옮기고 `V-Pot 틱에 LCD 반응 없음`으로 실패했다(값은 되돌리지 않음, 1회).
  - Compressor get·set은 표가 있는데도 호출마다 ▶·◀를 2~3번 눌러 페이지 수를 센다(두 브랜치 공통). 속도 최적화 후보.
  - Chorus 1페이지의 VALUE 화면 배치가 둘이다(한 칸 이름 대 두 칸 이름, 원인 미확인, 서버 경로에는 영향 없음).
  - 11/20의 `track_menu` 시작 실패는 이번에 못 봤다(재현 안 됨, 원인 미확인).
- **남긴 상태**: 테스트 프로젝트는 저장 안 함. 트랙 1 Space Designer `Predelay` `1/128`·index 9 60 %, 트랙 2 Compressor(Rel 100·Thrs −25·Knee 0.5·Gain 0), 트랙 3 슬롯 1에 Chorus가 들어가 있다(11/21 삽입). 트랙 5 슬롯 1·트랙 1·2 슬롯 2의 임시 인스턴스는 전부 제거 확인. 사용자 캐시(`~/.logic-mcp/plugins-12.0.1.json`)는 11/21 측정 전 백업으로 되돌림. 실기 스크립트(재측정·대조·진단)는 세션 임시 폴더에만 있고 레포에 넣지 않았다.

## 가까운 단계 성공 처리 + 묶음 set + 결함 ⑥ 수정 (2026-11-25 04:28~05:41, "testForMcp_1", Logic 12.0.1, 저장 안 함, 브랜치 `feat/batch-set`, 414 테스트)
- **계기**: 사용자 결정(11/25) — 닿을 수 없는 값은 가까운 값으로 성공 처리, 묶음 set 계획 승인, 모노 확인용 오디오 트랙 추가(트랙 6 "오디오 6").
- **방식**: 구현과 실기 실행은 하위 에이전트(Sonnet 코드 3, Sonnet 실기 실행 2, Opus 실기 진단 1). Fable은 계획 갱신·지시서·diff 검토·변이 확인·기록. 실기는 가드 달린 스크립트로 한 번에 한 프로세스(프로젝트 이름·덮개·절전 확인), 실행 4회 모두 Sleep 0회.
- **가까운 단계 규칙(8893756)**: `set_numeric`의 틱 루프에서 한 칸(`abs(ticks) == 1`)으로 목표를 건너뛰면 그 사이에 닿는 단계가 없다고 보고, 더 가까운 쪽에 두고 `ok=true`·`verified`로 끝낸다(차이가 같으면 지금 값에 둔다. 이전 값이 가까우면 보낸 만큼 되돌리고 읽어서 확인). note는 `목표 300에 닿는 단계 없음(290.0 m 다음이 310.0 m): 가까운 310.0 m로 맞춤`. 허용 오차를 직접 줘도 같다(허용 오차는 "도착"의 기준만 정한다. Fable 판단, 사용자 미확인: 기존 테스트 `test_tolerance_argument_overrides_default`의 마지막 기대를 실패 → 가까운 단계 성공으로 바꿨다). map은 지우지 않는다.
- **묶음 set(d1410f7·a0cca81·ebb8a95·141e82b·a8d6240·f01f2b2)**: 계획 `docs/superpowers/plans/2026-11-19-batch-set.md`(11/25 갱신 f515fc7) 그대로. `logic_plugin set`·`logic_eq set`에 `changes=[...]`(1~32개). 뷰에 한 번 들어가 받은 순서대로 맞추고, 보내기 전에 전부 검사하며, 첫 실패에서 멈추고 `after.results`·`after.done`·`after.remaining`을 돌려준다. 낱장 set의 결과는 그대로(기존 테스트 무수정).
  - 검토에서 고친 것: 이웃 열 테스트가 항목 사이 대기(`settle_overlay`)를 빼도 통과했다(가짜에서는 페이지 가드가 오버레이가 걷힐 때까지 기다려 결과가 같았다). 둘째 항목의 첫 읽기가 앞 항목 마지막 쓰기 뒤 `OVERLAY_S + OVERLAY_MARGIN_S` 이상인지 재는 단언을 넣었다(f01f2b2, 대기를 빼면 실패 확인). 변이 4건(플러그인·EQ 대기 제거, 첫 실패에서 안 멈춤, 중복 검사 제거) 모두 테스트가 잡는다.
  - 가짜 시계(Logic 응답 시간 제외): 플러그인 3항목 낱장 합 37.4 s → 묶음 31.8 s, EQ 4항목 53.4 s → 37.6 s.
- **결함 ⑥(기존 결함, 실기 확인 1·2회차에서 발견): 틱 한 칸이 표시 단위보다 작으면 "V-Pot 틱에 LCD 반응 없음"으로 실패한다.** Compressor Ratio 2.0·3.0이 낱장·묶음 합쳐 4회 중 4회 실패. main(06d4236) 코드로 Ratio에 틱을 하나씩 보내니 `1.3 → 1.4 → 1.4(무반응) → 1.5 → 1.6 → 1.6(무반응) → 1.7 → 1.8 → 1.8(무반응) → 1.9 → 2.0 → 2.1`로 12틱 중 3틱이 LCD를 바꾸지 않았고, −12틱으로 처음 값 1.3에 정확히 돌아왔다(값은 움직였다. 실측 `docs/mcu-protocol.md` Z26). 번들 표의 Ratio가 `linear 1~30`(실제는 로그)이라 페이더가 낮은 값에 떨어지고, 거기서 보낸 첫 틱이 무반응이면 바로 실패했다.
  - 수정 A(5bb054f): 무반응이면 같은 방향으로 한 틱씩 더 보내고, 한 라운드에 `SILENT_TICKS = 6`틱까지 무반응일 때만 실패로 본다. 틱당 변화 추정과 가까운 단계 되돌림은 실제로 보낸 틱 수를 쓴다.
  - 수정 B(974333a): 번들 Compressor `Ratio`를 `log 1~30`으로(11/19 실측 9점: raw 1·2048·…·16383 → 1.0·1.6·2.3·3.6·5.6·8.3·13·19·30).
- **실기 확인(`live_batch.py`, 트랙 4 슬롯 1 Compressor + 트랙 5 Channel EQ, 4회: f01f2b2로 2회, 수정 뒤 974333a로 2회)**
  - 가까운 단계(낱장, 4회 중 4회 같은 결과): Rel 300 → `310.0 m`(290과 같은 거리라 도착한 쪽), Ratio 4.0 → `4.1:1`, Attack 30 → `29.0 ms`(29 대 32). 4.4~7.5 s, 화면 대조 3/3. 이전에는 10회를 다 쓰고 실패했다(11/19).
  - 플러그인 묶음 4개(Thrs −30, Ratio 3.0, Attack 20, AutRel On): 수정 전 2회는 Ratio에서 결함 ⑥으로 멈췄고(`remaining` 2개, Thrs만 바뀜), 수정 뒤 2회는 4개 모두 성공(Ratio는 `2.9:1`, 2.9와 3.1 사이), 화면 대조 4/4. `elapsed_ms` 16.7 s 대 낱장 4회 합 18.8 s, 벽시계 19.4 s 대 30.1 s(낱장은 호출마다 `elapsed_ms`에 안 잡히는 PAN 복귀 ≈2.8 s가 붙는다).
  - 멈춤(4회 중 4회): 둘째에 Ratio 100 → `ok=false`·`skipped`, note `3개 중 1개 완료, 2번째 Ratio 실패: 범위 밖: 1~30 :1. 남은 1개는 보내지 않음`, `remaining` = Attack 10, 화면의 Attack은 12.0 그대로.
  - 가운데 닿을 수 없는 값(4회 중 4회): `[Thrs −25, Rel 300, Attack 15]` 3개 모두 성공, Rel은 가까운 단계 note, 12.0~12.2 s.
  - EQ 묶음 8개(밴드 2·3·4·6의 freq·gain, Channel EQ가 없던 트랙이라 삽입됨, 4회 중 4회): 8개 성공, `eq get`과 8/8 일치, `elapsed_ms` 26.9~28.4 s 대 낱장 8회 합 45.1~45.2 s, 벽시계 29.8~31.2 s 대 67.7~67.9 s. 삽입된 Channel EQ는 매번 제거 확인.
  - 시작 값 되돌리기 묶음 5개: 수정 전 1회는 Ratio에서 멈췄고, 나머지 3회는 성공.
- **결함 ⑤ 후속: 모노 대조와 둘째 묶음(트랙 6 = 모노 오디오 `(m/m)`, 실측 `docs/mcu-protocol.md` Z25)**
  - 모노 전수 대조(04:31~06:16, 10묶음 모두 유효): 67종 중 65종이 번들 표와 같고 2종이 다르다(Space Designer 12페이지·89개, Level Meter 5개: 이 둘은 표가 스테레오 배치). 스테레오에서 달랐던 15종은 모노에서 전부 표와 같다. → 번들 표는 플러그인마다 수집 형식이 섞여 있다. 두 형식 모두 같은 것 49종, 스테레오에서만 다른 것 15종, 모노에서만 다른 것 2종, Tuner는 스테레오 미확인.
  - 스테레오의 둘째 묶음(Opus 실기 6회): 이름(긴 이름 포함)·기본값·묶음 안 연동이 첫 묶음과 같고 값만 따로다. 첫 묶음은 모노 인스턴스와 같다. 11/25 새벽에 적은 "기본값이 다르다(둘째 75/25)"는 오독이라 Z24를 정정했다.
  - 못 정한 것: 플러그인(창·소리)이 어느 묶음을 쓰는지(편집 뷰에 들어가도 플러그인 창이 생기지 않아 화면으로 못 봤다), 두 벌이 스테레오 때문인지 소프트웨어 악기 트랙 때문인지(스테레오 오디오 트랙이 없다. 트랙 11 "오디오 1"도 모노).
- **관찰만 하고 고치지 않은 것**: 값 오버레이에서 읽은 텍스트는 단위가 잘린다(`-30.0 d`, `310.0 m`, 값은 맞다) / 낱장 호출의 PAN 복귀 ≈2.8 s가 `elapsed_ms`에 들어가지 않는다 / 번들 표의 곡선 종류는 Ratio 한 건만 고쳤다. 양 끝만 재는 프로빙은 비율 100 이하의 로그 곡선을 linear로 적는다(다른 항목 미확인, 가운데 점 재측정이 필요).

## 형식별 표 계획 준비 (2026-11-25 10:55~11:40, "testForMcp_1", Logic 12.0.1, 저장 안 함, 코드 변경 없음)
- **계기**: 사용자 "continue"(11/25 오전). 다음 순서 ①(형식별 표 계획)에 필요하다고 적어 둔 두 가지(플러그인이 어느 묶음을 쓰는지, 스테레오 오디오 트랙)를 직접 확인하려 했다.
- **실기(Opus 에이전트 1회, 가드 달린 `run_live_main.sh`, 모든 실행 유효)**: 오디오 트랙 12~15에 PlatinumVerb를 임시로 넣어 보니 4개 모두 헤더 `(m/m)`·3페이지(한 벌)였다(각 1회). 테스트 프로젝트의 오디오 트랙 6·11~15는 전부 모노다. 넣은 것은 매번 뺐고 트랙 5·12~15 슬롯은 비어 있다.
- **못 한 것**: 플러그인 창을 여는 UI 조작. `mcp__cmux-cua__*`가 `Computer Use onboarding is still in progress`로 시작되지 않았다(2회). System Events는 다른 Space에 있는 Logic 창을 0개로 본다. Logic을 앞으로 가져오면 사용자의 키 입력이 Logic에 들어갈 수 있어 하지 않았다. 그래서 "플러그인이 두 묶음을 어떻게 쓰는지"와 "스테레오 오디오 트랙에서도 두 벌인지"는 여전히 모른다. 편집 뷰 진입 때 플러그인 창이 열리는지는 컨트롤 서피스 설정의 `플러그인 윈도우 열기/닫기` 체크박스에 달려 있다(`docs/troubleshooting.md` 4번, 지금은 꺼져 있어 창이 안 생긴다).
- **오프라인으로 확인한 것(번들 `known.json`, 실기 없음)**
  - **결함 ⑦ Space Designer는 이름으로 못 찾는다(기존 결함)**: 번들 표가 스테레오 배치(89개 × 2벌)라 `_locate("Output Dry")`가 `'Output Dry'가 여럿에 맞음: ['OutDry', 'OutDry']`로 거절된다. 84개 이름 중 83개가 두 번 나온다. index로는 된다. 두 묶음의 `name`·map 종류는 2곳이 다르다(index 3 `Predelay` linear / index 92 enum).
  - 번들 67종 중 "축약명 앞 절반 = 뒤 절반"인 표는 Space Designer뿐이다. 축약명이 일부만 겹치는 표는 7종 더 있다(Multipressor·Ringshifter·EVOC 2종 등, 서로 다른 파라미터). 1페이지에 8칸이 꽉 찬 표는 없다(1페이지 표 35종).
- **계획**: `docs/superpowers/plans/2026-11-25-layouts.md`(사용자 검토 대기). 요지: 표를 이름 → 배치 목록으로 넓히고, 편집 뷰를 연 직후 페이지 수와 1페이지 이름으로 배치를 고른다(헤더 접미는 긴 트랙 이름에서 잘려 쓰지 않는다). 두 벌 배치는 `copies: 2`로 표시해 이름으로 찾으면 첫 묶음, 이름으로 쓰면 두 묶음 모두. 사용자가 정할 것 1건: 두 묶음 모두 쓰기(Fable 추천: 둘째 묶음의 정체가 무엇이든 결과가 맞다) 대 첫 묶음만.

## 곡선 종류 재측정 + 번들 표 수정 + 프로빙 결함 수정 (2026-11-25 11:28~12:36, 11/26 00:17~01:37, "testForMcp_1", Logic 12.0.1, 저장 안 함, 브랜치 `fix/curve-types`, 418 테스트)
- **계기**: 사용자 "continue"(11/25 오전, 11/26 00:17). 다음 순서 ②(번들 표의 곡선 종류)를 진행했다. 실측 `docs/mcu-protocol.md` Z27·Z28·Z29.
- **방식**: Fable이 측정·분석·적용 스크립트를 쓰고 2종으로 시험한 뒤, 묶음 실행은 Sonnet 에이전트(묶음 1~4)와 백그라운드 순차 스크립트(나머지)로. 코드 수정과 테스트는 Sonnet(실패 먼저 확인, 변이 확인), diff는 Fable이 검토.
- **무효 처리 2회**: 덮개가 닫혀 맥이 잠들면서 묶음 4(11/25 11:50, Sleep 1회)와 묶음 8(12:36, Sleep 6회)이 무효가 됐다. 둘 다 통째로 다시 돌렸다. 두 번 모두 뮤트 해제가 실패로 보고됐지만 다음 확인(12:07, 11/26 00:17)에서 트랙 6은 슬롯이 비어 있고 뮤트도 없었다.
- **측정 결과(66종 318개, Z27)**: 맞음 230, 종류 오류 35, linear도 log도 아님 45(25종), 숫자로 못 읽음 7, 단위 바뀜 1. 두 번 잰 67개는 전부 같은 글자로 읽혔다.
- **번들 표 수정(71abcf0)**: `type` 43개(종류 오류 35 + Space Designer 둘째 묶음의 짝 8, 17종), 최솟값 3개(Adaptive Limiter `Lookahead` 50 → 20, Channel EQ `Analyzer Decay` 10 → 0, Pitch Correction `Response` 122 → 0), `generated` 2026-11-26(사용자 캐시에 있던 번들 플러그인 표는 기존 규칙대로 번들 것으로 바뀐다). 테스트 2개(가운데 점 10곳이 map과 3 % 안, 최솟값 3곳).
- **실기 비교(같은 set 12개: 수정 전 1회, 수정 후 2회, 모두 유효)**: `elapsed_ms` 합 75.3 s → 49.0 s·48.9 s. 실패 1건 → 0건(Tape Delay `Delay Time` 250은 수정 전 10회 소진 `1132.7 ms`, 수정 후 `249.6 ms` 3.5 s). 대조군 Compressor `Thrs`는 3.8 s 그대로. 느려진 것 1개: Compressor `Q` 2.0이 4.1 s → 7.5 s·7.4 s(첫 페이더 이동이 무시돼 틱으로 돌아감, Z28. 무시되지 않은 시도에서는 새 map의 위치가 `2.00`에 바로 떨어졌다).
- **결함 ⑧ 프로빙이 무시된 이동 뒤의 값을 최솟값으로 적는다(기존 결함, 4ea4f5a 수정)**: `probe_mapping`이 에코가 없는 이동을 그대로 믿었다. 이제 반대쪽 끝을 거쳐 한 번 더 보낸다(가짜 옵션 `drop_next_faders`, 테스트 2개, 변이 확인). 실기 1회 4개 파라미터에서 표와 같은 범위(이미 맨 아래인 DeEsser `Suprss` 포함). 무시되는 조건을 재현하지 못해 그 경로 자체는 실기로 확인하지 못했다.
- **관찰만 하고 고치지 않은 것**
  - linear도 log도 아닌 곡선 45개(Z27): 지금 map 형식으로는 못 적는다. 첫 이동이 범위의 25 %(중앙값) 빗나가 틱으로 보정한다. 제안: 측정한 점을 표에 넣고 사이를 보간하는 map 종류(계획 필요, 전체 측정 필요).
  - 재지 않은 `linear` 약 350개(0·음수에서 시작): 표본 114개 중 20개가 선형이 아니었다. 나머지는 미확인이고, 최솟값이 기본값으로 적힌 항목이 더 있을 수 있다.
  - `set_numeric`의 첫 페이더 이동 무시(Z28): Compressor `Q`에서 10회 중 3회. 조건 미확인.
  - Space Designer가 스테레오 트랙에서 한 번 12페이지로 읽힘(Z29). 형식별 표 계획의 배치 고르기가 이런 순간에 모노 배치를 고를 수 있다(1~11페이지 이름은 같아 첫 묶음 쓰기는 맞게 된다).
  - **Test Oscillator**: 넣는 순간 테스트 톤을 내는 플러그인인데 11/25의 전수 대조 3회에서 뮤트 없이 넣었다 뺐다(소리가 났는지는 확인 못 함). 이번 측정부터 트랙을 뮤트하고 이 플러그인은 뺐다. 앞으로 임시 삽입을 도는 스크립트는 트랙 뮤트를 기본으로 한다.
  - UI 조작 도구(cmux Computer Use)는 온보딩 미완료로 시작되지 않는다(11/25). 플러그인 창 실험은 그대로 남아 있다.

## TODO
- **사용자 지시(2026-11-26 01:48)**: 지금까지 한 작업을 정리해 커밋하고, 다음은 속도 쪽이 아니라 **코드 최적화**(코드 정리·구조 개선)로 간다. 아래 ①②③은 그 뒤로 미룬다. 진행 중인 것: 곡선 2차 측정(1차에서 재지 않은 linear 306개, 48종, 01:44 시작, 백그라운드). 끝나면 `docs/measurements/`에 측정값만 추가하고, 분석과 표 수정은 나중에 한다. 측정이 도는 동안 main 트리의 코드는 고치지 않는다(실기 스크립트가 이 트리의 코드를 쓴다).
- **다음 순서(2026-11-26 01:40 갱신)**: ① 형식별 표 계획(`docs/superpowers/plans/2026-11-25-layouts.md`)의 사용자 검토·승인 → 구현 → 번들 배치 수집. ② 곡선 종류는 위 절에서 처리했다(35 + 8개). 남은 것: linear도 log도 아닌 45개를 위한 "측정 점 보간" map 제안(계획 필요), 재지 않은 linear 약 350개의 측정, 첫 페이더 이동 무시(Z28) 조건 찾기. ③ 남은 속도 후보는 아래 그대로. (이하 11/25 아침 기록) ① 형식별 표(결함 ⑤·⑦) 계획은 썼다(`docs/superpowers/plans/2026-11-25-layouts.md`) → 사용자 검토·승인 뒤 구현. 아래 "계획 전에 사용자가 정하거나 도와줄 것"은 계획의 "정할 것" 1건으로 줄었다(창 확인은 선택). 확인된 것: 표는 플러그인마다 형식이 섞여 있고(모노 배치 65종, 스테레오 배치 2종), 형식은 편집 뷰 헤더 접미(`(m/m)`·`(s/s)`·`(m/s)`)로 읽힌다. 계획 전에 사용자가 정하거나 도와줄 것: 스테레오 인스턴스에서 두 묶음 중 어디에 쓸지(첫 묶음만·둘 다), 그 근거로 플러그인 창을 한 번 열어 둔 상태의 확인 또는 귀로 확인, 스테레오 오디오 트랙 하나. ② 번들 표의 곡선 종류 재측정(가운데 점): 지금은 Compressor Ratio 한 건만 고쳤다. ③ 남은 속도 후보(항목 사이 대기 줄이기, 표가 있는 플러그인의 페이지 수 확인 생략).
- **작은 수정 후보(2026-11-25, 미구현)**: 1페이지 표라도 화면 이름이 표와 다르면 커서로 페이지를 확인(DeEsser·DJ EQ 스테레오) / `_merge_items`가 축약명이 바뀐 항목의 이름·map을 버리기 / 축약 기록이 잘린 목록 이름(`EVOC 20 TrackOscillat`)으로 덮이는 경로 찾기 / 사용자 캐시에 남은 깨진 표 이름(`Tape DeFeedback      ge 1/3`)의 출처 확인 / Space Designer `Predelay` 싱크 값에서 숫자 set / 표가 있는 플러그인에서 페이지 수를 세는 ▶·◀ 생략(속도) / SubBass `Wet` 범위·내림 범위 4건·Space Designer #39 `X-OvrF` 재측정 / 두 칸 값(`16.0 kHz`)의 정착 읽기.
- **설치 신뢰(2026-11-17 기록)**: 유명 MCP 레포 6곳 조사 결과에 맞춰 ① README 주의 섹션에 건드리는 범위·제거 방법 ② SECURITY.md·Dependabot(월 1회, 묶음) 추가 완료. 남은 것: ③ **PyPI 신뢰 게시** — `logic-mcp` 이름은 11/17 기준 비어 있음. 사용자 몫: pypi.org 계정 → Publishing에서 pending trusted publisher 추가(project `logic-mcp`, owner `Imtylerrrrrr`, repo `logic-mcp`, workflow `publish.yml`, environment `pypi`) → 릴리스 태그에서 Actions `publish`를 수동 실행. 성공하면 README 설치 명령을 `uvx logic-mcp`로 바꾸고 트리거를 `release: published`로 전환. `publish.yml`은 실행해 본 적 없음(미검증). ④ **읽기 전용 모드**(환경 변수로 모든 쓰기 명령 거부, github-mcp-server·supabase·playwright에 있음)는 최적화 설계 때 같이. ⑤ GitHub 비공개 취약점 제보는 11/17에 켰다(API로 `enabled: true` 확인). ⑥ Dependabot PR #1(actions/checkout v7·setup-uv v7)·#2(pydantic·pytest·anyio)는 11/17 머지, main 261c53a에서 367 테스트·CI 통과.
- **속도 최적화(2026-11-10 기록, 보류)**: set 하나가 10초 안팎인 이유는 `settle_overlay` 2.5 s가 뷰 진입·Flip·페이더 이동(라운드마다)·PAN 복귀에서 4번 이상 들어가고, 호출이 파라미터 하나 단위라 진입·복귀가 매번 반복되기 때문(분석만, 코드 변경 없음). 후보: ① `logic_eq set`·`logic_plugin set`에 여러 파라미터 묶음(뷰 진입·Flip·복귀 1회, 중간 실패 시 멈추고 PAN 복귀) ② 매핑이 확실한 숫자는 라운드마다 읽지 않고 마지막에 한 번 확인 ③ 오버레이 마진 0.5 s는 10/28 경계 실패 전력이 있어 줄이지 않음.
  - 정정(2026-11-19, 가짜 Logic의 가상 시계로 측정. Logic의 실제 응답 시간은 빠져 있다): `settle_overlay`는 Flip·페이더 이동에는 없다. 숫자 set 1회는 서버 대기 6.2 s 중 5.1 s가 뷰 진입 1번 + PAN 복귀 1번(각 ≈2.5 s)이고, 숫자 값은 21칸 오버레이에서 바로 읽는다(`read_value`). 틱마다 2.5 s를 기다리는 것은 선택지(enum) 파라미터뿐이다(set 8.3 s, 대기 3번). get도 5.5 s(대기 2번). → 묶음 set의 이득은 뷰 진입·복귀 반복이 없어지는 만큼이다. 다만 값 오버레이가 ≈2 s 동안 이웃 열을 덮고 NAME/VALUE 전환으로도 지워지지 않아(실측 10/20 G2) 묶음 안에서도 항목 사이에 2.5 s를 기다려야 한다: 숫자 8개 기준 플러그인 ≈50 s → ≈33 s, EQ ≈65 s → ≈29 s(가짜 시계 수치로 계산한 추정, 실기 미측정. 같은 날 먼저 적었던 "≈14 s"는 이 대기를 빼먹은 값). 11/17 영상(`~/reports/logic-mcp-실행흐름.mp4`)의 주문서 ② 장면과 '미세 조정 2.5초 × 0~10회'는 숫자 파라미터에는 맞지 않는다.
- **실기에서 나온 수정 후보(2026-11-19. ①은 11/25 가까운 단계 규칙으로, ②는 11/20 페이지 가드로 구현됨. ③④⑤는 남음)**: 위 "묶음 set 사전 실기 측정" 참고.
  - ① 닿을 수 없는 값: 틱 한 칸으로 목표를 넘나들면(오차 부호가 바뀌면) 더 가까운 쪽에 멈추고 끝낸다(10회 소진·map 삭제 없음). 결과를 `ok=true`(note에 단계 설명)로 할지 `ok=false`로 빨리 끝낼지는 사용자 결정. 번들 표의 곡선 종류(Ratio 로그 등)는 프로빙이 양 끝만 보고 추정하는 한계라 별도 과제.
  - ② 쓰기 가드: 값을 보내기 직전 그 열의 1행 이름(또는 `Page n/N` 토큰의 페이지)이 기대와 다르면 보내지 않는다. 보낸 뒤 오버레이 이름이 기대 파라미터가 아니면 즉시 멈춘다. 먼저 이벤트 로그로 결함 ②의 원인을 확인한다.
  - ③ `elapsed_ms`에 PAN 복귀 시간 포함 여부.
  - ④ 남은 측정(덮개를 연 상태에서): 6~8개 묶음 2회 이상, EQ 숫자 8개 낱장 대 묶음, 숫자 + 선택지 섞기, 오버레이 타임라인, 시험용 Compressor 제거.
  - ⑤ 레벨 읽기 활용(11/19 실전 사용에서 나옴): 게이트·컴프레서 Threshold를 근거 있게 잡으려면 트랙 레벨이 필요하다. 서버는 MCU 미터(4비트)를 이미 받아 스트립 상태에 `meter`로 내보낸다. 이 값의 dB 대응과 해상도를 실측해야 쓸 수 있는지 알 수 있다(미확인).
- **묶음 set 계획(2026-11-19 정리 → 2026-11-25 승인·구현·실기 확인 완료, 위 절)**: 속도 최적화 후보 ①. 구현 계획은 `docs/superpowers/plans/2026-11-19-batch-set.md`(사용자 결정: 실패 시 멈춤). 아래 요약과 다르면 계획 문서가 맞다(항목 사이 `settle_overlay` 대기, 결과 키 `done`, 최대 32개).
  - 문제: set 1회의 서버 대기 6.2 s 중 5.1 s가 뷰 진입 + PAN 복귀다(위 정정의 가짜 시계 측정). 값 8개를 바꾸면 이 5.1 s와 모델 왕복이 8번 반복된다.
  - 방식: 한 호출에 같은 트랙·같은 슬롯(EQ는 그 트랙의 Channel EQ)의 값 여러 개를 받는다. 뷰 진입 1번 → 항목마다 [찾기 → 맞추기 → 읽어 확인] → PAN 복귀 1번. 항목은 받은 순서대로 처리한다.
  - 입력(제안): `logic_plugin` `action="set"`에 `changes: [{param, value, tolerance?}]`, `logic_eq` `action="set"`에 `changes: [{band, param, value}]`. 기존 `param`·`value` 한 개 형식은 그대로 두고, 둘을 같이 주면 skipped.
  - 결과(제안): `ToolResult` 형식은 그대로. `after = {"results": [{param(·band), ok, verified, before, after, note}], "applied": n, "remaining": [보내지 않은 changes]}`. `ok`는 전부 성공일 때만 true, `note`는 한 줄 요약("3개 중 2개 적용, 3번째 Attack 실패: … 남은 1개는 보내지 않음").
  - 실패 처리(제안): ① 보내기 전에 모든 항목을 검사한다(플러그인: 편집 뷰를 연 뒤 표에서 param 전부 찾기 / EQ: 밴드·param 조합과 값 형식). 하나라도 틀리면 아무 값도 바꾸지 않고 skipped. ② 실행 중 항목이 `ok=false`면 거기서 멈추고 남은 항목은 `remaining`으로 돌려준다. 이미 바꾼 값은 되돌리지 않는다(낱장 호출과 같음). `already`는 성공으로 보고 계속한다.
  - 변경 ① `plugin.py`: `set` body에서 "편집 뷰가 열린 상태에서 항목 하나를 맞추는" 부분을 `_set_one`으로 떼고, 한 개짜리 set도 항목 1개 묶음으로 같은 길을 탄다. `_goto_param`은 NAME 모드에서 시작한다고 가정하므로 항목 사이에 NAME 모드로 되돌린다. 선택지 항목은 낱장과 같은 조건이 되도록 Flip을 끈 상태에서 틱한다(Flip 켠 채 선택지 틱은 실기 미확인).
  - 변경 ② `eq.py`: 같은 구조(`_set_one(band, param, value)`), 항목마다 `_goto_page(band)`, Channel EQ 삽입 여부는 호출당 한 번만 판단. 변경 ③ `server/tools.py`: 두 도구에 `changes` 인자와 설명(영어). 변경 ④ `skills/logic-plugins/SKILL.md`·README(.ko)·CHANGELOG(.ko): 값 여러 개는 `changes`로 한 번에 보내라는 안내.
  - 테스트(가짜 Logic): 숫자 3개 묶음에서 뷰 진입·PAN 복귀 버튼이 1번씩이고 가상 시계가 낱장 3회보다 짧음 / 한 개 형식은 기존 테스트 그대로 통과 / 없는 param이 섞이면 MIDI를 하나도 안 보냄 / 2번째 실패 시 1번째는 적용·3번째는 미전송·`remaining` / 숫자와 선택지 섞임 / 서로 다른 페이지의 param / EQ 여러 밴드와 slope 밴드 규칙 / `allow_insert` 삽입 뒤 묶음 / `param`과 `changes`를 같이 주면 skipped / 중간 ModeError에도 PAN 복귀하고 적용된 항목을 결과에 남김.
  - 실기 확인(사용자가 Logic을 켠 뒤, 빈 테스트 프로젝트, 저장 안 함): Channel EQ 숫자 8개를 낱장 8회와 묶음 1회로 각각 보내 `elapsed_ms` 비교, Compressor에서 숫자 + 선택지 섞은 묶음.
  - 범위 밖: 여러 트랙·여러 슬롯을 한 호출에, 같은 페이지 페이더 동시 이동, 되돌리기, get 묶음(`params`가 이미 전체를 읽는다).
  - 사용자 결정 대기: 실패 시 멈춤(제안) 대 끝까지 진행, 입력 이름 `changes`.
- **삽입 자리 기억 계획(2026-11-19 정리, 승인 대기, 미구현)**: 속도 최적화 후보 ③.
  - 문제: 삽입 목록은 Logic 버전당 한 벌(`~/.logic-mcp/plugins-<버전>.json`의 `list`)인데 실제 메뉴 순서가 다르면 `seek_by_name`이 `--`부터 1틱씩 읽는다(틱마다 최소 `TICK_QUIET_S` 0.4 s). 기록된 탐색 길이는 43·44·75·84틱. 저장된 목록에서 Channel EQ는 58번째, 실제 메뉴에서는 38번째(75틱)였다.
  - 원인은 미확정: 위 11/11 메모의 "프로젝트마다 순서가 다르다"는 추측이다. 10/27에는 서로 다른 두 프로젝트(guitartone·무제 2)에서 Channel EQ가 같은 75틱에 있었고, 모노 트랙 메뉴는 163개·스테레오는 126개였다. 서버는 MIDI로 프로젝트 이름을 알 수 없다. → 원인을 몰라도 되는 방식으로 간다.
  - 방식: 목록 한 벌 대신 플러그인 이름마다 "실제로 본 항목 번호"를 최근 3개까지 기억한다. 기억한 번호로 바로 가서 이름을 읽고, 맞을 때만 확정한다. 틀리면 지금 흐름으로 넘어가고 기억을 고친다.
  - 변경 ① `plugins/cache.py`: `PluginCache.spots: dict[str, list[int]]`(키 = 접미를 뗀 오버레이 이름, 값 = 항목 번호 `(틱+1)//2`, 최근 것이 앞, 최대 3개), `learn_spots(trail: dict[str, int])`, 사용자 파일 키 `"spots"`(없는 옛 파일은 빈 dict).
  - 변경 ② `plugins/scan.py`: `seek_by_name`이 지나온 이름 → 항목 번호 `trail`을 넷째 값으로 돌려준다(호출 3곳 수정).
  - 변경 ③ `plugin.py` `_insert_body`: 되감은 뒤 spots 후보를 차례로(상대 이동 `2·(i−현재)`) 가서 `_shown`으로 이름 확인 → 맞으면 기존 확정·헤더 검증으로. 전부 틀리면 기존 흐름(목록 위치 → 근처 보정 3회 → 이름 탐색) 그대로. 이름 탐색이 끝나면 찾았든 못 찾았든 `learn_spots(trail)` 후 저장. spots·목록 위치로 맞힌 번호는 맨 앞으로 올린다. 목록에 없는 이름은 기억한 이름들에서 `find`가 하나로 정할 때만 그 spots를 쓴다. 결과 note는 `spot:<번호>`.
  - 변경 ④ `plugin_mixer.py` `AuxMixer.insert`: 같은 순서(spots → 이름 탐색). 변경 ⑤ `plugins/calibrate.py` `scan`: 수집한 목록의 순번을 `learn_spots`로 넘긴다(새 종류의 트랙에서 scan 한 번이면 그 메뉴 전체가 기억됨).
  - 지킬 것: 확정 누름은 오버레이 이름이 맞을 때만(지금과 같음). 기억이 틀려도 엉뚱한 플러그인은 들어가지 않는다. 한 번에 `2·i`틱 점프가 i번째에 선다는 가정은 기존 목록 위치 경로와 같다.
  - 테스트(가짜 Logic, `tests/test_assign_plugin.py`·`test_plugins.py`): 순서가 다른 메뉴에서 1회차 `name_scan:` → 2회차 같은 플러그인은 `spot:`이고 보낸 V-Pot 메시지가 줄어듦 / 1회차에 지나친 다른 플러그인도 바로 감 / 메뉴가 바뀌면 누르지 않고 이름 탐색으로 넘어가 새 번호가 앞·옛 번호가 뒤 / 4번째 번호가 오면 가장 오래된 것 탈락 / 저장·재로드와 `spots` 없는 옛 파일 / 목록에 없는 이름의 조회 / Aux 슬롯 1 경로.
  - 실기 확인(사용자가 Logic을 켠 뒤, 빈 테스트 프로젝트, 저장 안 함): 같은 플러그인 삽입·제거 2회 + 1회차에 지나친 플러그인 1회, note와 걸린 시간 기록. 모노·스테레오 트랙에서 각각 해서 순서 차이의 원인도 같이 본다.
  - 범위 밖: 틱당 대기 줄이기, 트랙 종류·프로젝트별로 목록 나누기. 한계: 한 번도 지나친 적 없는 플러그인은 처음에 여전히 훑는다. 효과(초)는 실측 전.
