# logic-mcp

Claude Code가 Logic Pro를 조작하는 MCP 서버. Logic이 공식 지원하는 Mackie Control(MCU) 프로토콜을 CoreMIDI 가상 포트로 에뮬레이션하고, 모든 명령을 Logic이 서피스로 돌려보내는 LED·페이더·LCD 피드백으로 검증한다. 화면을 클릭하거나 접근성 API를 쓰지 않는다. 오가는 것은 MIDI만이다.

> **English:** An MCP server that lets Claude Code (or any MCP client) operate Logic Pro by emulating a Mackie Control surface over a CoreMIDI virtual port. Every command is checked against the LED, fader and LCD feedback Logic sends back to the surface, so each result says whether it actually happened. No UI scripting, no accessibility hooks, MIDI only. Measured against Logic Pro 12.0.1. Documentation is in Korean.

## 할 수 있는 것

- 트랜스포트: 재생·정지·녹음·사이클·되감기·빨리감기
- 트랙: 선택·뮤트·솔로·녹음 대기
- 믹서: 볼륨(dB, -∞ ~ +6.0)·팬(-64 ~ 63), 8스트립 뱅크 이동
- Channel EQ: 밴드 8개의 주파수·게인·Q·슬로프·온/오프 읽기·쓰기
- 인서트 플러그인: 슬롯 1~8의 목록·삽입·제거·바이패스, 파라미터 읽기·쓰기, 삽입 메뉴 스캔
- 센드: 센드 1~8의 목적지(버스)·레벨(dB)·위치(Pre/Post/Post Pan)·뮤트 읽기·쓰기, 제거

작동 방식: 서버가 "LogicMCP"라는 가상 MIDI 포트를 열면 Logic이 이를 Mackie Control로 자동 설치한다. 서버는 버튼·V-Pot·페이더 메시지를 보내고, Logic이 돌려보내는 LCD(2×56자)·LED·페이더 위치로 상태를 재구성한다. 모든 툴 결과에는 `verified`(피드백으로 확인됨), `skipped`(이미 그 상태라 보내지 않음), `unverified`(보냈지만 확인 못 함), `timeout`(응답 없음) 중 하나가 붙는다. 추측으로 "됐다"고 말하지 않는다.

## 요구 사항

- macOS, Logic Pro 11 또는 12 (12.0.1에서 실측)
- Python 3.13 이상, [uv](https://docs.astral.sh/uv/)
- MCP 클라이언트 (아래는 Claude Code 기준)

## 설치 (macOS, Logic Pro 11/12)

1. 클론하고 의존성을 설치한다: `git clone https://github.com/Imtylerrrrrr/logic-mcp.git && cd logic-mcp && uv sync`
2. Claude Code 프로젝트에 `.mcp.json` 추가 (`.mcp.json.example`의 경로를 클론한 위치로 바꾼다)
3. Claude Code를 켠 뒤 Logic에서 프로젝트를 연다. Logic이 "LogicMCP" 포트를 Mackie Control로 자동 설치한다.
4. 처음 한 번 `logic_session configure`를 호출한다(트랙 번호 표시, 값 표시 모드, Beats 클락).
5. 스킬을 복사한다: `cp -R skills/logic-plugins ~/.claude/skills/`

## 빠른 사용법

Claude Code에 자연어로 말하면 된다. 설치 5번의 스킬을 넣어 두면 Claude가 EQ·플러그인·센드 명령의 순서와 함정을 먼저 읽는다.

```
1번 트랙 뮤트해
3번 트랙 볼륨 -6 dB로 맞춰
2번 트랙 Channel EQ 밴드 3을 1 kHz, +3 dB로
1번 트랙 인서트 슬롯 2에 Compressor 넣어줘
그 Compressor의 Threshold를 -20 dB로
현재 뱅크 플러그인 목록 보여줘
1번 트랙 센드 1을 Bus 2로 보내고 레벨 -12 dB
```

트랙은 `strip`(현재 뱅크의 1~8) 또는 `number`(LCD에 찍히는 Logic 트랙 번호) 둘 중 하나로 가리킨다. 툴을 직접 부르면 이런 모양이다.

```json
logic_mixer {"action": "set_volume", "strip": 3, "db": -6.0}
→ {"ok": true, "verified": "verified", "action": "set_volume",
   "target": {...}, "before": {...}, "after": {...}, "elapsed_ms": 176, "note": ""}
```

`ok`가 false이거나 `verified`가 `unverified`·`timeout`이면 `note`에 이유가 들어 있다(Flip이 켜져 있음, LCD 변화 없음 등).

## 툴

| 툴 | 설명 |
|---|---|
| `logic_transport` | 재생·정지·녹음·사이클·되감기·빨리감기 |
| `logic_track` | 트랙 선택·뮤트·솔로·녹음 대기 |
| `logic_mixer` | 볼륨(dB)·팬 |
| `logic_bank` | 뱅크·채널 이동, 번호가 보이도록 뱅크 찾기 |
| `logic_session` | 연결 상태, 서피스 설치 대기, configure |
| `logic_eq` | Channel EQ 밴드 8개의 주파수·게인·Q·슬로프·온/오프 읽기·쓰기 |
| `logic_plugin` | 인서트 슬롯 1~8의 목록·삽입·제거·바이패스, 파라미터 읽기·쓰기, 플러그인 스캔 |
| `logic_send` | 센드 1~8의 목적지(버스)·레벨·위치·뮤트 읽기·쓰기 |

리소스: `logic://status`, `logic://transport`, `logic://strips`, `logic://lcd`, `logic://plugins`, `logic://inserts`, `logic://view`.

인서트 슬롯은 1~8, 센드는 1~8만 지원한다. 출력(Stereo Out)·Master 스트립은 EQ 채널·플러그인·센드 명령을 받지 않는다(Logic의 채널 뷰가 그 스트립을 따라가지 않음, `docs/mcu-protocol.md` Z4).

플러그인 목록은 번들(Logic 12.0.1 내장) + `logic_plugin scan`(사용자 캐시 `~/.logic-mcp/plugins-<버전>.json`)으로 이뤄진다. 번들 파라미터 표는 `uv run python scripts/calibrate_plugin.py "<플러그인>" [strip] --write`로 만든다(테스트 프로젝트에서).

부작용: EQ·플러그인·센드 명령은 Logic의 트랙 선택을 바꾸고, 트랙에 Channel EQ가 없으면 EQ 명령이 자동으로 삽입하며, 플러그인 창이 열릴 수 있다. 버스 센드를 새로 만들면 Logic이 Aux 트랙을 자동 생성해 뒤 트랙 번호가 바뀐다.

## 상태

| 기능 | 실제 Logic 12.0.1 검증 |
|---|---|
| 트랜스포트·트랙·믹서·뱅크 | 완료 |
| Channel EQ·인서트 플러그인 | 완료 (실기 9차 17/17) |
| 출력·Master 스트립 가드 | 완료 (실기 10차, Stereo Out 스트립에서 skipped) |
| 센드(`logic_send`) | 완료 (실기 10차 9/9) |
| 플러그인 파라미터 번들 표 | 9종(10/19 실기 수집: Channel EQ·Compressor·Adaptive Limiter·Noise Gate·Tape Delay·Stereo Delay·Overdrive·Distortion·ChromaVerb, 179 파라미터). map 없는 파라미터는 쓸 때 프로빙. Space Designer는 편집 뷰 페이지 이동 실패로 미수집 |
| 캘리브레이션·스캔 보정(10/19) | 완료 (1틱 스캔 163개가 진단과 일치, 재수집 표에 enum 오판 0건; insert 근처 탐색은 미확인) |

## 주의

- 변경은 Logic 프로젝트에 그대로 반영된다. 처음에는 버려도 되는 테스트 프로젝트에서 써 보라. 서버는 프로젝트를 저장하지 않는다.
- Logic을 재시작한 뒤 EQ·플러그인 같은 할당 버튼이 반응하지 않으면, Logic > 설정 > 컨트롤 서피스 > 설정에서 Mackie Control 장치를 삭제하고 서버를 다시 연결한다. Logic이 기본값으로 다시 설치한다(`docs/mcu-protocol.md` Z6). 그 뒤 `logic_session configure`를 한 번 더.
- 버스 센드를 새로 만들면 Logic이 Aux 트랙을 만들어 뒤쪽 트랙 번호가 밀린다. 그 뒤에는 `logic_bank show`나 `plugin list`로 번호를 다시 확인하라.
- `scripts/calibrate_plugin.py`는 열린 프로젝트에 플러그인을 넣고 값을 움직인 뒤 되돌리지 않는다. 테스트 프로젝트에서만 쓰고 저장하지 마라.
- 사용자가 이미 쓰는 다른 컨트롤 서피스는 건드리지 않는다. 이 서버는 자기 포트 "LogicMCP"만 연다.

## 개발

- 단위 테스트: `uv run pytest` (실제 Logic 불필요, 가짜 Logic 모델로 273개)
- 실기 검증(Logic에서 테스트 프로젝트를 열어 둔 채): `uv run python scripts/live_check.py` (트랜스포트·트랙·믹서), `uv run python scripts/live_check2.py [strip] [--scan]` (EQ·플러그인·센드)
- `scripts/calibrate_plugin.py "<플러그인>" [strip] [--write] [--yes]` 플러그인 파라미터 표 수집(`--write`면 번들 `known.json`에 병합)
- `scripts/capture.py` MCU 트래픽 캡처, `scripts/calibrate_fader.py` 페이더 dB 표 생성
- 문서: 설계 `docs/superpowers/specs/`, 구현 계획 `docs/superpowers/plans/`, 프로토콜 실측 `docs/mcu-protocol.md`, 진행 기록 `docs/progress.md`, 리뷰 `docs/reviews/`

## 라이선스

[MIT](LICENSE). Logic Pro는 Apple Inc.의 상표이고 Mackie Control은 LOUD Technologies의 상표다. 이 프로젝트는 두 회사와 무관하다.
