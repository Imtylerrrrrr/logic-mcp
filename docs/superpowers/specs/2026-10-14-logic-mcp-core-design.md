# logic-mcp 스펙 1 — 코어 + MCU 제어 (설계)

작성 2026-10-14. 상태: 사용자 리뷰 대기.

## 1. 목적과 범위

Claude Code가 Logic Pro를 조작하는 MCP 서버. 용도는 작곡·편곡 보조(A), 세션·믹싱 제어(B), AI가 DAW를 조작하는 데모(D). 지금은 Tyler의 맥 한 대, 나중에 공개.

스펙 1의 범위는 **코어 + B-1**이다.

- 트랜스포트: 재생, 정지, 녹음, 사이클, 되감기, 빨리감기
- 트랙: 뮤트, 솔로, 녹음 활성, 선택
- 믹서: 볼륨(dB), 팬
- 뱅크 이동과 절대 트랙 번호 주소
- 세션: 연결 상태, 준비 대기, 서피스 설정 보정
- 읽기 리소스: 상태, 트랜스포트, 스트립 8개, LCD 원문

다음 스펙으로 미루는 것: Send/EQ/Plug-in 모드와 Flip(스펙 2), 키커맨드 세트와 SMF 가져오기·내보내기(스펙 3). AX(접근성) 자동화는 쓰지 않는다. Logic 12에서 바깥 프로세스가 창 목록조차 믿을 수 없음을 실측했다.

## 2. 핵심 결정과 근거

**제어 채널은 Mackie Control(MCU) 에뮬레이션 over CoreMIDI 하나다.** Logic은 공개 API가 없고 OSC 수신기도 없다. MCU는 Logic이 공식 지원하는 유일한 양방향·상태형 채널이다. 2026-10-13~14 스파이크(Logic Pro 12.0.1, macOS 26.5)로 확인한 사실:

- Logic은 프로젝트를 열 때 모든 MIDI 포트에 디바이스 쿼리 sysex를 보낸다(ID 0x10, 0x11, 0x14, 0x15, 0x17). 응답하면 "자동 설치"로 등록된다. **0x14(Mackie Control 본체)에만 응답**한다. 전부 응답하면 Extender(0x15)가 설치돼 트랜스포트가 무시된다.
- 포트당 기기 1대만 설치된다. 설치 직후 수십 초 환영 애니메이션 동안 버튼이 무시된다.
- 명령 → 피드백 왕복 100ms 안쪽. MUTE LED, PLAY/STOP LED, 타임 디스플레이(자리별 CC), 페이더 에코값, LCD 값 텍스트(`+0.0 dB`, `-oo dB`, 팬 `+5`)를 모두 받는다.
- OPTION+NAME/VALUE로 LCD 1행이 `번호:이름`(`1:1 2:StOu 5:Mast`)으로 바뀐다. 이 번호가 절대 주소다.
- 포트가 사라졌다 다시 뜨면 Logic은 핸드셰이크 없이 이름으로 재바인딩한다.

**스택은 Python 3.13 + uv.** `python-rtmidi`(가상 포트), `mcp>=2.3,<3`(v2 `MCPServer`). Swift 포팅은 계획하지 않되, 프로토콜 계층을 순수 함수와 언어 중립 픽스처로 만들어 포팅이 싸도록 한다.

## 3. 아키텍처

```
Claude Code ──stdio──▶ logic-mcp ──CoreMIDI 가상 포트 "LogicMCP"──▶ Logic Pro (Mackie Control)
```

단일 Python 프로세스. 계층은 위에서 아래로, 각 계층은 아래 계층만 안다.

| 계층 | 모듈 | 책임 | 의존 |
|---|---|---|---|
| server | `server/main.py`, `server/tools.py`, `server/resources.py` | MCPServer 등록, 입력 검증, 응답 모델 | logic |
| logic | `logic/commands.py`, `logic/faders.py` | 명령 헬퍼(보내기→기대 피드백 대기→판정), dB 변환, 팬 델타, 주소 해석 | mcu |
| mcu/state | `mcu/state.py` | 순수 리듀서: 이벤트 → `SurfaceState`, 잠잠해짐 판정 | protocol |
| mcu/protocol | `mcu/protocol.py` | 바이트 ↔ 이벤트 순수 함수, 핸드셰이크 응답 생성 | 없음 |
| mcu/transport | `mcu/transport.py` | rtmidi 가상 포트, 수신 콜백 → 큐, 송신 | protocol |

**연결 상태 머신** (`logic://status`로 노출):

```
no_logic ──디바이스 쿼리 수신, 0x14 응답──▶ handshake ──LCD 첫 그리기──▶ animating ──LCD·링 500ms 조용──▶ ready
   ▲                                                                                              │
   └──────────────── 30초 동안 수신 없음(재생 중 제외) 또는 포트 오류 ─────────────────────────────┘
```

30초 무수신·포트 오류 전이는 어느 상태에서든 일어난다. `session` 툴 외 모든 툴은 `ready`에서만 동작한다.

**스레드 모델.** rtmidi 콜백은 CoreMIDI 스레드에서 불린다. 콜백은 `(timestamp, bytes)`를 큐에 넣기만 한다. 리듀서 스레드 하나가 큐를 소비해 상태를 갱신하고 `threading.Condition`으로 대기자를 깨운다. MCP 툴 핸들러는 전역 명령 락을 잡고 상태를 읽거나 송신한다. 가상 포트 인스턴스(`MidiIn`, `MidiOut`)는 프로세스 수명 동안 하나씩 유지하고 종료 시 `.delete()`한다. 이름을 바꾸거나 다시 만들지 않는다.

## 4. MCP 인터페이스

툴 이름은 `logic_` 접두사. 각 툴은 `action: Literal[...]`과 action별 파라미터를 받는다. 스펙 1은 5개, 3개는 이름만 예약한다.

| 툴 | action | 파라미터 | 검증 근거 |
|---|---|---|---|
| `logic_transport` | play, stop, record, cycle_on, cycle_off, rewind, fast_forward | 없음 | PLAY/STOP/REC/CYCLE LED, 타임 디스플레이 |
| `logic_track` | mute, unmute, solo, unsolo, arm, disarm, select | `strip` 1-8 또는 `number` | 해당 LED |
| `logic_mixer` | set_volume, set_pan | `strip`/`number`, `db` 또는 `pan` | 페이더 에코값, LCD 2행 값 |
| `logic_bank` | left, right, channel_left, channel_right, first, last, show | `number`(show) | LCD 1행 번호 |
| `logic_session` | status, wait_ready, configure | `timeout_s` | 상태 머신, LCD |
| `logic_assign` | 스펙 2 예약 | | |
| `logic_keycmd` | 스펙 3 예약 | | |
| `logic_midi` | 스펙 3 예약 | | |

**주소.** `strip`은 현재 뱅크의 1-8. `number`는 LCD 1행 `번호:` 접두사에 찍히는 Logic 채널 번호다(Logic이 매기는 번호이며 연속이 아닐 수 있다. 실측: `1:1 2:StOu 5:Mast`). 둘 중 하나만 받는다. `number`가 현재 뱅크에 없으면 `logic_bank show`와 같은 절차로 뱅크를 옮긴 뒤 실행한다. `show`의 절차: OPTION+BANK◀로 첫 세트 → LCD 1행에 번호가 보일 때까지 BANK▶ 반복(최대 32회) → LCD가 더 변하지 않으면 끝에 닿은 것이므로 `ok=false`, `note`에 "번호 N 없음, 보이는 번호: ...". LCD에 번호 접두사가 없으면(`configure` 전) `number` 주소는 거부한다. 트랙 이름은 7자 ASCII로만 오고 한글은 통째로 사라지므로 이름 주소는 두지 않는다.

**값.** `db`는 -inf(문자열 `"-inf"` 허용)부터 +6.0까지, 0.1 단위로 반올림. `pan`은 -64부터 +63 정수.

**`logic_session configure`.** 서버가 의존하는 서피스 설정을 보장한다. 순서: (1) LCD 1행에 `번호:` 접두사가 없으면 OPTION+NAME/VALUE, (2) 페이더 1을 현재값으로 다시 보내 LCD 2행에 `dB` 텍스트가 뜨는지 확인, 안 뜨면 NAME/VALUE(값 표시 모드), (3) BEATS LED가 꺼져 있으면 SMPTE/BEATS. 각 단계는 LCD나 LED로 확인한다.

**리소스**(읽기 전용, `resources/list`에 노출):

- `logic://status`: `state`, `port`, `last_rx_age_ms`, `settling`, `assignment_mode`, `flip`, `name_format_ok`(LCD 1행에 `번호:` 접두사가 있는지), `configured`(마지막 `configure` 성공 여부, `no_logic`이 되면 false).
- `logic://transport`: LED 6개, `time.mode`(beats/smpte), `time.text`, `time.parsed`(bars, beats, division, ticks 또는 hh, mm, ss, ff). 재생 중에도 안정 대기 없이 최신값.
- `logic://strips`: 스트립 8개. `strip`, `number`, `name`, `rec`, `solo`, `mute`, `select`, `fader_raw`, `fader_db`, `pan_ring`, `meter`, `value_text`.
- `logic://lcd`: `row1`, `row2`(각 56자), `settling`.

**응답 모델**(모든 툴 공통, Pydantic):

```
ok: bool
verified: Literal["verified", "unverified", "timeout", "skipped"]
action: str
target: {strip, number, name} | None
before: dict | None      # 건드린 대상의 관련 필드만
after: dict | None
elapsed_ms: int
note: str                # "already muted", "clamped to +6.0 dB", 실패 시 다음에 할 일
```

`verified`는 기대 피드백이 왔음, `unverified`는 피드백이 왔지만 기대와 다름, `timeout`은 피드백 없음, `skipped`는 멱등 규칙으로 보내지 않음. `ok=false`면 `note`에 원인과 다음 행동을 쓴다("상태가 animating. `logic_session wait_ready` 후 재시도").

툴 애너테이션: `logic_session status`는 `read_only_hint`, 상태 설정 액션은 `idempotent_hint`. `destructive_hint`는 모두 false.

## 5. 검증 규칙

**전제.** `ready`가 아니면 보내지 않고 `ok=false`. 한 번에 명령 하나(전역 락). 자동 재시도 없음.

**순서.** `before` 스냅샷 → 송신 → 조건 대기(제한 시간) → 잠잠해짐 대기 → `after` 스냅샷 → 판정.

**멱등.** mute/unmute/solo/unsolo/arm/disarm/cycle_on/cycle_off/play/stop/record는 먼저 LED를 본다. 이미 목표 상태면 `skipped`. 토글 명령은 노출하지 않는다.

**조건과 제한 시간.** 실측 왕복이 100ms 안쪽이라 5배 여유.

| 액션 | 성공 조건 | 제한 |
|---|---|---|
| track 계열, transport | 해당 LED가 기대값 | 500ms |
| set_volume | 페이더 에코값이 Logic이 양자화한 값 기준 ±32/16383. Logic은 보낸 값을 양자화해 돌려준다(10000 → 9990). +6.0 dB(14845) 위는 클램프되며 `note`에 적는다 | 800ms |
| set_pan | LCD 2행 값 텍스트가 목표와 일치 | 500ms |
| bank 계열 | LCD 1행 변화 후 150ms 조용 | 1000ms |

**잠잠해짐.** 타임 디스플레이와 LCD는 자리·구간 단위로 조각나서 온다. 조각이 올 때마다 `dirty_until = now + 120ms`. 리소스는 마지막 안정 스냅샷을 돌려주고 `settling`을 표시한다. 예외: `logic://transport`는 최신값. Logic은 컨트롤을 움직이면 LCD에 긴 파라미터명을 잠깐 띄우므로, set_volume의 1차 근거는 페이더 에코값이고 LCD 2행은 조용해진 뒤 `dB`가 포함된 텍스트만 참고한다.

**거부.** `set_pan`은 할당 모드 LED가 PAN일 때만 보낸다. 다른 모드면 같은 CC가 다른 파라미터를 돌리므로 `ok=false`. 페이더는 터치 ON → 피치벤드 → 터치 OFF 순서로만 보낸다(Logic 기본값이 터치 필요).

**연결 끊김.** 포트 오류 또는 30초 무수신(재생 중은 타임 디스플레이가 계속 오므로 제외)이면 `no_logic`. 툴은 즉시 실패. 포트는 유지한다.

## 6. 상태 모델

`SurfaceState`는 리듀서가 만드는 불변 스냅샷(dataclass, `replace`로 갱신).

- `strips[8]`: `number: int | None`(LCD 1행 `번호:` 파싱), `name`, `rec`, `solo`, `mute`, `select`, `fader_raw`(0-16383), `fader_db`, `pan_ring`(mode, pos, center), `meter`, `value_text`(LCD 2행 7자).
- `transport`: PLAY, STOP, REC, CYCLE, REW, FFWD LED.
- `time`: `digits[10]`, `dots[10]`, `mode`(LED 0x71 SMPTE / 0x72 BEATS), 파싱값. Beats 형식은 자리 배치 `bbb bb bb ttt`.
- `assignment`: TRACK/SEND/PAN/PLUGIN/EQ/INST LED, 2자리 표시(CC 0x4A/0x4B), FLIP LED.
- `lcd`: 2×56 문자 배열. `connection`: 상태, 마지막 수신 시각, `dirty_until`.

**dB 변환.** Logic의 페이더 커브는 공개 자료가 없다. `scripts/calibrate_fader.py`가 0부터 14845까지 64 간격으로 보내고 LCD 2행 dB 텍스트를 읽어 `tests/fixtures/mcu/fader_db.json`을 만든다. 변환은 표의 선형 보간. 스팟 체크: 0 → `-oo dB`, 9990 → `-5.8 dB`, 12443 → `+0.0 dB`, 14845 → `+6.0 dB`.

**팬.** 현재값은 LCD 2행 텍스트(`0`, `+5`, `-12`)에서 읽는다. 목표와의 차이를 V-Pot 상대 CC 한 메시지로 보낸다(크기 비트, 한 메시지에 최대 63). 실측: `+5` 한 메시지 → LCD `+5`. 보낸 뒤 LCD가 목표와 다르면 차이를 다시 한 번만 보내고, 그래도 다르면 `unverified`.

## 7. 테스트, 레포, 설치

**레포 구조**

```
logic-mcp/
  pyproject.toml            # uv, python 3.13, mcp>=2.3,<3, python-rtmidi, pydantic
  src/logic_mcp/
    mcu/protocol.py  mcu/state.py  mcu/transport.py
    logic/commands.py  logic/faders.py
    server/main.py  server/tools.py  server/resources.py
  tests/
    fixtures/mcu/cap_raw*.log   # ~/logic-mcp-spike 에서 복사, 형식 "ts RX|TX hex"
    fixtures/mcu/fader_db.json
    test_protocol.py  test_state.py  test_commands.py  test_server.py
  scripts/capture.py  scripts/calibrate_fader.py  scripts/live_check.py
  docs/mcu-protocol.md      # 실측 기록(핸드셰이크, 노트·CC 표, 타이밍)
  docs/progress.md
  docs/superpowers/specs/
```

**테스트 4층.** CI는 1~4만 돈다.

1. protocol: 픽스처의 RX 줄 전부를 디코드해 예외 없음. 알려진 오프셋에서 LCD 텍스트, LED, 페이더값, 타임 자리값 일치. 핸드셰이크 응답 바이트가 캡처의 TX와 일치.
2. state: run6 구간을 재생해 설치 → animating → ready 전이, 754s MUTE1 on, 755s PLAY on과 타임 파싱, 4570s 페이더 9990과 `-5.8 dB`.
3. commands: 가짜 트랜스포트에 피드백 스크립트를 넣어 verified/unverified/timeout/skipped 네 경로, PAN 모드 아닐 때 거부, number 주소의 뱅크 이동.
4. server: SDK 인프로세스 클라이언트로 툴 목록·스키마, mute 1건, 리소스 4개 읽기.
5. live: `scripts/live_check.py`가 실제 Logic으로 MUTE/PLAY/STOP/볼륨/팬을 돌리고 결과를 표로 출력. 수동 실행.

**설치.** Claude Code `.mcp.json`:

```json
{"mcpServers": {"logic": {"command": "uv", "args": ["run", "--directory", "<repo>", "logic-mcp"]}}}
```

Logic 쪽은 서버를 켠 뒤 프로젝트를 열면 자동 설치된다. 그다음 `logic_session configure` 한 번. README는 이 두 단계만 적는다. "모든 모델 스캔"은 설치 창과 알림을 같이 띄우므로 안내하지 않는다.

**작업 단위.** 기능 하나씩 커밋, 변경 200줄 안쪽, 실제 Logic으로 확인한 뒤에만 완료 표시. `docs/progress.md`를 먼저 읽고 시작한다.

## 8. 비범위와 알려진 제약

- 트랙 이름으로 주소 지정 불가(7자 ASCII, 한글 소실).
- 플레이헤드 위치 지정 없음(MCU에 직접 로케이트가 없다. 스펙 3 키커맨드에서 다룬다).
- 미터는 읽기만 하며 값의 dB 의미는 정의하지 않는다.
- MPK mini IV 등 사용자의 다른 컨트롤 서피스 설정은 절대 건드리지 않는다. "기본값 재형성" 메뉴는 누르지 않는다.
- 스파이크 스크립트(`~/logic-mcp-spike/capture2.py` 등)는 버린다. 픽스처와 실측 기록만 가져온다.

## 부록 A. 프로토콜 실측 요약

디바이스 ID 0x14. sysex 헤더 `F0 00 00 66 14`.

- 핸드셰이크: 쿼리 `00` → 응답 `01` + 시리얼 7바이트 + 챌린지 4바이트. 버전 요청 `13` → 응답 `14` + `V1.00`.
- LCD 쓰기 `12 <offset 0-111> <text>`, 2행은 56. 페이더 터치 감도 `0E <ch> <0-5>`. `72 ...`는 미해독(픽스처만).
- 버튼/LED: Note On ch1, 0x7F on / 0x00 off. REC 00-07, SOLO 08-0F, MUTE 10-17, SELECT 18-1F, V-Pot push 20-27, TRACK 28 SEND 29 PAN 2A PLUGIN 2B EQ 2C INST 2D, BANK◀ 2E CH◀ 2F BANK▶ 30 CH▶ 31, FLIP 32, NAME/VALUE 34, SMPTE/BEATS 35, SHIFT 46 OPTION 47 CTRL 48 ALT 49, CYCLE 56, REW 5B FFWD 5C STOP 5D PLAY 5E REC 5F, 페이더 터치 68-6F, LED SMPTE 71 BEATS 72 RUDE SOLO 73.
- 페이더: Pitch Bend ch1-8, 14비트. Logic 범위 0-14845(+6.0 dB), 0 dB = 12443, 에코는 양자화.
- V-Pot 회전 CC 10-17: 01-3F 시계, 41-7F 반시계, 하위 비트가 크기. 링 CC 30-37: bit6 중앙점, bit4-5 모드, 하위 4비트 위치.
- 타임 디스플레이 CC 40-49(자리별), 값 bit6=점. 할당 표시 CC 4A-4B. 미터 Channel Pressure `(ch<<4)|level`.
- 교차검증: REAPER `csurf_mcu.cpp`(LGPL), Apple 컨트롤 서피스 지원 가이드. 코드 복사 없음.
