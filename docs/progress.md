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

## TODO
- **설치 신뢰(2026-11-17 기록)**: 유명 MCP 레포 6곳 조사 결과에 맞춰 ① README 주의 섹션에 건드리는 범위·제거 방법 ② SECURITY.md·Dependabot(월 1회, 묶음) 추가 완료. 남은 것: ③ **PyPI 신뢰 게시** — `logic-mcp` 이름은 11/17 기준 비어 있음. 사용자 몫: pypi.org 계정 → Publishing에서 pending trusted publisher 추가(project `logic-mcp`, owner `Imtylerrrrrr`, repo `logic-mcp`, workflow `publish.yml`, environment `pypi`) → 릴리스 태그에서 Actions `publish`를 수동 실행. 성공하면 README 설치 명령을 `uvx logic-mcp`로 바꾸고 트리거를 `release: published`로 전환. `publish.yml`은 실행해 본 적 없음(미검증). ④ **읽기 전용 모드**(환경 변수로 모든 쓰기 명령 거부, github-mcp-server·supabase·playwright에 있음)는 최적화 설계 때 같이. ⑤ GitHub 비공개 취약점 제보는 11/17에 켰다(API로 `enabled: true` 확인). ⑥ Dependabot PR #1(actions/checkout v7·setup-uv v7)·#2(pydantic·pytest·anyio)는 11/17 머지, main 261c53a에서 367 테스트·CI 통과.
- **속도 최적화(2026-11-10 기록, 보류)**: set 하나가 10초 안팎인 이유는 `settle_overlay` 2.5 s가 뷰 진입·Flip·페이더 이동(라운드마다)·PAN 복귀에서 4번 이상 들어가고, 호출이 파라미터 하나 단위라 진입·복귀가 매번 반복되기 때문(분석만, 코드 변경 없음). 후보: ① `logic_eq set`·`logic_plugin set`에 여러 파라미터 묶음(뷰 진입·Flip·복귀 1회, 중간 실패 시 멈추고 PAN 복귀) ② 매핑이 확실한 숫자는 라운드마다 읽지 않고 마지막에 한 번 확인 ③ 오버레이 마진 0.5 s는 10/28 경계 실패 전력이 있어 줄이지 않음.
  - 정정(2026-11-19, 가짜 Logic의 가상 시계로 측정. Logic의 실제 응답 시간은 빠져 있다): `settle_overlay`는 Flip·페이더 이동에는 없다. 숫자 set 1회는 서버 대기 6.2 s 중 5.1 s가 뷰 진입 1번 + PAN 복귀 1번(각 ≈2.5 s)이고, 숫자 값은 21칸 오버레이에서 바로 읽는다(`read_value`). 틱마다 2.5 s를 기다리는 것은 선택지(enum) 파라미터뿐이다(set 8.3 s, 대기 3번). get도 5.5 s(대기 2번). → 묶음 set의 이득은 뷰 진입·복귀 반복이 없어지는 만큼이다. 다만 값 오버레이가 ≈2 s 동안 이웃 열을 덮고 NAME/VALUE 전환으로도 지워지지 않아(실측 10/20 G2) 묶음 안에서도 항목 사이에 2.5 s를 기다려야 한다: 숫자 8개 기준 플러그인 ≈50 s → ≈33 s, EQ ≈65 s → ≈29 s(가짜 시계 수치로 계산한 추정, 실기 미측정. 같은 날 먼저 적었던 "≈14 s"는 이 대기를 빼먹은 값). 11/17 영상(`~/reports/logic-mcp-실행흐름.mp4`)의 주문서 ② 장면과 '미세 조정 2.5초 × 0~10회'는 숫자 파라미터에는 맞지 않는다.
- **실기에서 나온 수정 후보(2026-11-19, 결정 대기, 미구현)**: 위 "묶음 set 사전 실기 측정" 참고.
  - ① 닿을 수 없는 값: 틱 한 칸으로 목표를 넘나들면(오차 부호가 바뀌면) 더 가까운 쪽에 멈추고 끝낸다(10회 소진·map 삭제 없음). 결과를 `ok=true`(note에 단계 설명)로 할지 `ok=false`로 빨리 끝낼지는 사용자 결정. 번들 표의 곡선 종류(Ratio 로그 등)는 프로빙이 양 끝만 보고 추정하는 한계라 별도 과제.
  - ② 쓰기 가드: 값을 보내기 직전 그 열의 1행 이름(또는 `Page n/N` 토큰의 페이지)이 기대와 다르면 보내지 않는다. 보낸 뒤 오버레이 이름이 기대 파라미터가 아니면 즉시 멈춘다. 먼저 이벤트 로그로 결함 ②의 원인을 확인한다.
  - ③ `elapsed_ms`에 PAN 복귀 시간 포함 여부.
  - ④ 남은 측정(덮개를 연 상태에서): 6~8개 묶음 2회 이상, EQ 숫자 8개 낱장 대 묶음, 숫자 + 선택지 섞기, 오버레이 타임라인, 시험용 Compressor 제거.
  - ⑤ 레벨 읽기 활용(11/19 실전 사용에서 나옴): 게이트·컴프레서 Threshold를 근거 있게 잡으려면 트랙 레벨이 필요하다. 서버는 MCU 미터(4비트)를 이미 받아 스트립 상태에 `meter`로 내보낸다. 이 값의 dB 대응과 해상도를 실측해야 쓸 수 있는지 알 수 있다(미확인).
- **묶음 set 계획(2026-11-19 정리, 승인 대기, 미구현)**: 속도 최적화 후보 ①. 구현 계획은 `docs/superpowers/plans/2026-11-19-batch-set.md`(사용자 결정: 실패 시 멈춤). 아래 요약과 다르면 계획 문서가 맞다(항목 사이 `settle_overlay` 대기, 결과 키 `done`, 최대 32개).
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
