# logic-mcp

[English](README.md)

Claude Code가 Logic Pro를 조작하는 MCP 서버. Logic이 공식 지원하는 Mackie Control(MCU) 프로토콜을 CoreMIDI 가상 포트로 에뮬레이션하고, 모든 명령을 Logic이 서피스로 돌려보내는 LED·페이더·LCD 피드백으로 검증한다. 화면을 클릭하거나 접근성 API를 쓰지 않는다. 오가는 것은 MIDI만이다.

## 빠른 사용법

1. Claude Code에 서버를 추가한다(다른 클라이언트는 [설치](#설치-macos-logic-pro-1112) 참고).

   ```
   claude mcp add logic -- uvx --python 3.12 --from git+https://github.com/Imtylerrrrrr/logic-mcp logic-mcp
   ```

2. Logic에서 프로젝트를 연다. 처음엔 버려도 되는 복사본으로. 변경은 열린 프로젝트에 바로 들어가고, 서버는 저장을 하지 않는다.
3. Claude에게 "Logic 연결 설정해줘"라고 한 번 말하고(`logic_session configure`가 돈다), 그다음 하고 싶은 걸 말한다.

## 이렇게 시키면 된다

플러그인 이름을 몰라도 된다. 원하는 소리를 말로 묘사한다:

- *"1번 트랙에 내 노래 녹음했어. 완성된 팝 보컬처럼 들리게 해줘"*
- *"보컬에 티 나는 오토튠 걸어줘. 곡은 D 메이저야"*
- *"기타가 너무 답답해. 넓고 깔끔하게 만들어줘"*

용어를 알면 원하는 만큼 구체적으로 말한다:

- *"2번 트랙에 게이트, 살짝 컴프, 앰프, 딜레이 조금, 리버브는 버스로 크게"*
- *"1번 트랙 Channel EQ 밴드 3을 1 kHz, +3 dB로"*

## 쓰면서 느낄 것

- 큰 요청 하나가 작은 단계 열몇 개로 쪼개지고, 단계마다 몇 초 걸린다. Claude가 가상 콘솔의 페이더·노브를 움직인 뒤 Logic 전광판에 새 값이 뜨는 걸 확인하고 다음으로 넘어가기 때문이다. 톤 하나에 몇 분쯤 든다.
- 모든 답에 `verified`, `skipped`(이미 그 상태), `unverified`(보냈지만 Logic이 확인해 주지 않음) 중 하나가 붙는다. `unverified`면 이유도 같이 말한다.
- 트랙은 가상 콘솔의 현재 뱅크 8개 기준이다. "3번 트랙"은 세 번째 스트립, "트랙 번호 12"는 Logic 트랙 헤더의 번호. 필요하면 Claude가 뱅크를 옮긴다.

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
- Python 3.12 (python-rtmidi가 macOS 휠을 3.12까지 제공한다. 3.13 이상은 Xcode Command Line Tools로 소스 빌드가 필요하다), [uv](https://docs.astral.sh/uv/)
- MCP 클라이언트 (Claude Code, Claude Desktop 등)

## 설치 (macOS, Logic Pro 11/12)

### A. Claude Code

```
claude mcp add logic -- uvx --python 3.12 --from git+https://github.com/Imtylerrrrrr/logic-mcp logic-mcp
```

선택(Claude Code 전용): EQ·플러그인·센드 명령의 순서와 함정을 담은 스킬을 복사한다.

```
git clone https://github.com/Imtylerrrrrr/logic-mcp.git && cp -R logic-mcp/skills/logic-plugins ~/.claude/skills/
```

### B. Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json`에 추가한다. `command`는 `which uvx`로 얻은 절대 경로를 쓴다(Finder에서 뜬 앱은 PATH가 짧다).

```json
{"mcpServers": {"logic": {"command": "/Users/<사용자>/.local/bin/uvx",
  "args": ["--python", "3.12", "--from", "git+https://github.com/Imtylerrrrrr/logic-mcp", "logic-mcp"]}}}
```

### C. 개발

1. 클론하고 의존성을 설치한다: `git clone https://github.com/Imtylerrrrrr/logic-mcp.git && cd logic-mcp && uv sync`
2. Claude Code 프로젝트에 `.mcp.json` 추가 (`.mcp.json.example`의 경로를 클론한 위치로 바꾼다)

### 공통

Logic에서 프로젝트를 열면 "LogicMCP" 포트가 Mackie Control로 자동 설치된다. 처음 한 번 `logic_session configure`를 호출한다(트랙 번호 표시, 값 표시 모드, Beats 클락).

## 툴

| 툴 | 설명 |
|---|---|
| `logic_transport` | 재생·정지·녹음·사이클·되감기·빨리감기 |
| `logic_track` | 트랙 선택·뮤트·솔로·녹음 대기 |
| `logic_mixer` | 볼륨(dB)·팬 |
| `logic_bank` | 뱅크·채널 이동, 번호가 보이도록 뱅크 찾기 |
| `logic_session` | 연결 상태, 서피스 설치 대기, configure |
| `logic_eq` | Channel EQ 밴드 8개의 주파수·게인·Q·슬로프·온/오프 읽기·쓰기 |
| `logic_plugin` | 인서트 슬롯 1~8의 목록·삽입·제거·바이패스, 파라미터 읽기·쓰기, 플러그인 스캔, 파라미터 표 수집(calibrate, force 필요) |
| `logic_send` | 센드 1~8의 목적지(버스)·레벨·위치·뮤트 읽기·쓰기 |

리소스: `logic://status`, `logic://transport`, `logic://strips`, `logic://lcd`, `logic://plugins`, `logic://inserts`, `logic://view`.

툴을 직접 부르면 이런 모양이다. 트랙은 `strip`(현재 뱅크의 1~8) 또는 `number`(LCD에 찍히는 Logic 트랙 번호) 둘 중 하나로 가리킨다.

```json
logic_mixer {"action": "set_volume", "strip": 3, "db": -6.0}
→ {"ok": true, "verified": "verified", "action": "set_volume",
   "target": {...}, "before": {...}, "after": {...}, "elapsed_ms": 176, "note": ""}
```

`ok`가 false이거나 `verified`가 `unverified`·`timeout`이면 `note`에 이유가 들어 있다(Flip이 켜져 있음, LCD 변화 없음 등).

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
| 플러그인 파라미터 번들 표 | 67종, MCU로 보이는 Logic 12.0.1 삽입 메뉴 전체(10/19~11/11 실기 수집, 두 칸 표 14개는 11/11 재수집, 마지막 열 범위는 11/25 재측정, 1,040 파라미터, map 없음 80개). map 없는 파라미터는 쓸 때 프로빙. map 없는 것은 대부분 동작 파라미터·Mute 같은 최소값·단위 변화(Space Designer 20, ChromaVerb 10) |
| 캘리브레이션·스캔 보정(10/19) | 완료 (1틱 스캔 163개가 진단과 일치, 재수집 표에 enum 오판 0건; insert 근처 탐색은 미확인) |

## 주의

- 변경은 Logic 프로젝트에 그대로 반영된다. 처음에는 버려도 되는 테스트 프로젝트에서 써 보라. 서버는 프로젝트를 저장하지 않는다.
- Logic을 재시작한 뒤 EQ·플러그인 같은 할당 버튼이 반응하지 않으면 [문제 해결](docs/troubleshooting.ko.md)의 1-4(Mackie Control 장치 삭제·재연결)를 따른다.
- 버스 센드를 새로 만들면 Logic이 Aux 트랙을 만들어 뒤쪽 트랙 번호가 밀린다. 그 뒤에는 `logic_bank show`나 `plugin list`로 번호를 다시 확인하라.
- `logic_plugin calibrate`와 `scripts/calibrate_plugin.py`는 열린 프로젝트에 플러그인을 넣고 값을 움직인 뒤 되돌리지 않는다. 테스트 프로젝트에서만 쓰고 저장하지 마라.
- 사용자가 이미 쓰는 다른 컨트롤 서피스는 건드리지 않는다. 이 서버는 자기 포트 "LogicMCP"만 연다.
- 서버가 건드리는 것: MCP 클라이언트와 stdio로만 통신하고 네트워크 연결을 하지 않으며, macOS 개인정보 보호 권한(접근성, 화면 기록, 자동화)을 요구하지 않는다. `~/.logic-mcp/`(플러그인 캐시)에만 쓰고, 버전 확인용으로 Logic의 `Info.plist`를 읽고, Logic이 켜져 있는지 보려고 외부 명령 `pgrep` 하나를 실행한다. 의존성은 `mcp`, `python-rtmidi`, `pydantic` 세 개다.
- 제거하려면: `claude mcp remove logic`을 실행하고(Claude Desktop은 설정 파일에서 항목 삭제), Logic > 설정 > 컨트롤 서피스 > 설정에서 LogicMCP 포트를 쓰는 Mackie Control 장치를 삭제하고, `~/.logic-mcp/`를 지운다.

문제가 생기면 [docs/troubleshooting.md](docs/troubleshooting.ko.md)를 위에서 아래 순서로 확인하라. 보안 문제 제보는 [SECURITY.ko.md](SECURITY.ko.md)를 보라.

## 개발

- 단위 테스트: `uv run pytest` (실제 Logic 불필요, 가짜 Logic 모델로 295개)
- Python 3.12 확인: `uv run --isolated -p 3.12 pytest -q`
- stdio 스모크(서버를 띄워 initialize만 주고받음, Logic 불필요): `uv run python scripts/smoke_stdio.py`
- 배포 파일 빌드: `uv build`
- 실기 검증(Logic에서 테스트 프로젝트를 열어 둔 채): `uv run python scripts/live_check.py` (트랜스포트·트랙·믹서), `uv run python scripts/live_check2.py [strip] [--scan]` (EQ·플러그인·센드)
- `scripts/calibrate_plugin.py "<플러그인>" [strip] [--write] [--yes]` 플러그인 파라미터 표 수집(`--write`면 번들 `known.json`에 병합)
- `scripts/capture.py` MCU 트래픽 캡처, `scripts/calibrate_fader.py` 페이더 dB 표 생성
- 문서: 설계 `docs/superpowers/specs/`, 구현 계획 `docs/superpowers/plans/`, 프로토콜 실측 `docs/mcu-protocol.md`, 진행 기록 `docs/progress.md`, 리뷰 `docs/reviews/`

## 라이선스

[MIT](LICENSE). Logic Pro는 Apple Inc.의 상표이고 Mackie Control은 LOUD Technologies의 상표다. 이 프로젝트는 두 회사와 무관하다.
