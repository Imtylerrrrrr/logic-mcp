# logic-mcp

Claude Code가 Logic Pro를 조작하는 MCP 서버. Logic이 공식 지원하는 Mackie Control 프로토콜을 CoreMIDI 가상 포트로 에뮬레이션하고, 모든 명령을 Logic의 LED·페이더·LCD 피드백으로 검증한다.

## 설치 (macOS, Logic Pro 11/12)

1. `uv sync` (Python 3.13 이상)
2. Claude Code 프로젝트에 `.mcp.json` 추가 (`.mcp.json.example` 참고)
3. Claude Code를 켠 뒤 Logic에서 프로젝트를 연다. Logic이 "LogicMCP" 포트를 Mackie Control로 자동 설치한다.
4. 처음 한 번 `logic_session configure`를 호출한다(트랙 번호 표시, 값 표시 모드, Beats 클락).

## 툴

| 툴 | 설명 |
|---|---|
| `logic_transport` | 재생·정지·녹음 등 트랜스포트 |
| `logic_track` | 트랙 선택·뮤트·솔로·녹음 대기 |
| `logic_mixer` | 볼륨·팬 |
| `logic_bank` | 뱅크·채널 이동 |
| `logic_session` | 연결 상태, configure |
| `logic_eq` | Channel EQ 밴드 8개의 주파수·게인·Q·슬로프·온/오프 읽기·쓰기 |
| `logic_plugin` | 인서트 목록·삽입·제거·바이패스, 파라미터 읽기·쓰기, 플러그인 스캔 |

리소스: `logic://status`, `logic://transport`, `logic://strips`, `logic://lcd`, `logic://plugins`, `logic://inserts`, `logic://view`.

플러그인 목록은 번들(Logic 12.0.1 내장) + `logic_plugin scan`(사용자 캐시 `~/.logic-mcp/plugins-<버전>.json`)으로 이뤄진다.

부작용: EQ·플러그인 명령은 Logic의 트랙 선택을 바꾸고, 트랙에 Channel EQ가 없으면 EQ 명령이 자동으로 삽입하며, 플러그인 창이 열릴 수 있다.

## 개발

`uv run pytest` (실제 Logic 불필요). 실제 검증은 `uv run python scripts/live_check.py`.
설계: `docs/superpowers/specs/`, 프로토콜 실측: `docs/mcu-protocol.md`.
