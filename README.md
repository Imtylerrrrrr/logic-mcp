# logic-mcp

Claude Code가 Logic Pro를 조작하는 MCP 서버. Logic이 공식 지원하는 Mackie Control 프로토콜을 CoreMIDI 가상 포트로 에뮬레이션하고, 모든 명령을 Logic의 LED·페이더·LCD 피드백으로 검증한다.

## 설치 (macOS, Logic Pro 11/12)

1. `uv sync` (Python 3.13 이상)
2. Claude Code 프로젝트에 `.mcp.json` 추가 (`.mcp.json.example` 참고)
3. Claude Code를 켠 뒤 Logic에서 프로젝트를 연다. Logic이 "LogicMCP" 포트를 Mackie Control로 자동 설치한다.
4. 처음 한 번 `logic_session configure`를 호출한다(트랙 번호 표시, 값 표시 모드, Beats 클락).

## 툴

`logic_transport`, `logic_track`, `logic_mixer`, `logic_bank`, `logic_session`. 리소스 `logic://status`, `logic://transport`, `logic://strips`, `logic://lcd`.

## 개발

`uv run pytest` (실제 Logic 불필요). 실제 검증은 `uv run python scripts/live_check.py`.
설계: `docs/superpowers/specs/`, 프로토콜 실측: `docs/mcu-protocol.md`.
