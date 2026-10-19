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
- 다음: Space Designer 수집(23페이지, 약 1시간 예상) → 스펙 3.
- 미검증 경로 자리.
- 다음: 스펙 3(공개 준비: GitHub 원격, 설치 문서, 악기 슬롯 검토).
