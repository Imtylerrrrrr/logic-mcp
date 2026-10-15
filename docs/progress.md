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
