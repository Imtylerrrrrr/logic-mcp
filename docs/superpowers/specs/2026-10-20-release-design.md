# 스펙 3: v0.1.0 공개 릴리스 준비 (2026-10-20)

## 의도
지금은 레포를 클론하고 `uv sync`한 뒤 `.mcp.json`에 절대 경로를 써야 쓸 수 있다. 공개 사용자가 **한 줄로 설치**해 Claude Code·Claude Desktop에서 쓰고, 막혔을 때 **문서만 보고 스스로 복구**할 수 있게 한다. 새 MCU 기능은 넣지 않는다.

## 목표
- G1 설치 한 줄: `uvx --python 3.12 --from git+https://github.com/Imtylerrrrrr/logic-mcp logic-mcp`. Claude Code는 `claude mcp add logic -- uvx …`, Claude Desktop은 `claude_desktop_config.json` 예시.
- G2 Python 3.12 지원: `requires-python = ">=3.12"`. 근거(2026-10-20 실측): python-rtmidi 1.5.8은 macOS 휠을 cp312까지만 제공한다. 3.13·3.14는 Xcode Command Line Tools로 소스 빌드가 되지만(로컬 3.14.7에서 meson 빌드 동작) 공개 사용자에게 요구할 수 없다. 3.12에서 전체 테스트 292개 통과.
- G3 장애 복구 문서 `docs/troubleshooting.md`: 증상 → 진단 순서 → 조치. 내용은 `docs/mcu-protocol.md`의 실측(Z6·Z10·Z11·Z12·Z14·Z16·Z17)만 쓴다.
- G4 `logic_plugin` 툴에 `calibrate` 액션: 플러그인 파라미터 표를 한 번에 수집해 사용자 캐시에 저장. 값을 되돌리지 않고 움직이므로 `force=true`가 없으면 `skipped`.
- G5 서버 `instructions`: 스킬 디렉토리가 없는 클라이언트(Claude Desktop)도 시작 순서를 알도록, `MCPServer(..., instructions=…)`에 시작 순서·결과 필드 뜻을 짧게 넣는다.
- G6 `CHANGELOG.md`(Keep a Changelog 형식, 0.1.0 항목) + GitHub 테스트 워크플로(macos-latest, Python 3.12, `uv run pytest`).
- G7 `v0.1.0` 태그 + GitHub Release(wheel·sdist 첨부). **태그와 릴리스는 모든 항목이 main에 들어간 뒤 사용자가 확인하고 만든다.**

## 하지 않는 것
- PyPI 업로드(이름 `logic-mcp`는 2026-10-20 기준 비어 있음. 명령만 CHANGELOG 아래 "릴리스 절차"에 적어 둔다).
- 영어 번역, 새 툴·새 MCU 기능, Logic 11 실측, macOS 밖 플랫폼.
- 기존 툴의 결과 형식·이름 변경.

## 실패로 치는 것
- 설치·점검 과정이 사용자의 Logic 프로젝트를 건드리거나 저장하는 것.
- `calibrate`가 `force` 없이 값을 움직이는 것.
- 문서에 실측하지 않은 복구 절차를 적는 것.

## 제약
- Logic과는 MIDI로만 상호작용한다(UI 클릭·AX 없음). MPK mini IV 항목과 "기본값 재형성"은 문서에서도 건드리지 말라고 쓴다.
- `uv build` 휠에 `fader_db.json`·`plugins/known.json`이 들어간다(확인됨, 32파일). 유지.
- 테스트는 3.12와 로컬 3.14 양쪽에서 통과.

## 구성 요소
1. **pyproject.toml**: `requires-python = ">=3.12"`, `[project.urls]`에 `Changelog`·`Issues` 추가. 버전은 0.1.0 유지.
2. **README.md**: 요구 사항(Python 3.12 권장과 그 이유 한 줄), 설치를 세 경로로: (A) Claude Code `claude mcp add` 한 줄, (B) Claude Desktop JSON — Finder에서 뜬 앱은 PATH가 짧으므로 `command`에 `which uvx`로 얻은 절대 경로를 쓰라고 적는다, (C) 개발용 클론. 스킬 복사는 Claude Code 전용으로 표시. "문제가 생기면" 링크 → troubleshooting. `.mcp.json.example`은 (C)용으로 유지.
3. **docs/troubleshooting.md**: ① `no_logic`/`wait_ready` 실패: Logic 실행? 프로젝트 열림(Z11 '시작' 대화상자)? 모달 알림(Z10 "오디오 인터페이스를 사용할 수 없습니다" → 확인)? 컨트롤 서피스 설정에 Mackie Control이 0개 또는 2개(Z6·Z14 → 삭제 후 서버 재시작하면 재설치)? ② `configure` unverified: NAME 상태(Z12)·PAN 2행 `-`(Z17, configure가 자동 복구). ③ 편집 뷰에서 플러그인 창이 열림: 컨트롤 서피스 설정 CS 그룹 `플러그인 윈도우 열기/닫기` 해제. ④ `page_to … 커서 반응 없음`(Z16): 재시도. ⑤ 다른 컨트롤 서피스와 공존: 그 항목은 건드리지 않음, "기본값 재형성" 금지.
4. **calibrate 액션**: `tools.py` `logic_plugin` action Literal에 `"calibrate"` 추가. `slot` 필요, `force=False`면 `skipped`(note: "calibrate는 파라미터 값을 되돌리지 않고 움직인다. 테스트 프로젝트에서 force=true로 실행"). `force=True`면 `commands.plugin.calibrate(strip, number, slot)`(이미 있음, 사용자 캐시에 저장). 툴 설명 문자열에 한 줄 추가.
5. **instructions**: `create_server`에서 `MCPServer("logic-mcp", instructions=INSTRUCTIONS, lifespan=…)`. 내용: 시작 순서(`logic_session wait_ready` → `configure` 처음 한 번 → `logic://plugins` 확인), 결과 필드(`ok`·`verified`·`note`) 한 줄, 트랙 지정(`strip`/`number`) 한 줄, 플러그인·EQ·센드 함정은 `skills/logic-plugins/SKILL.md` 참조. mcp 2.3.0의 `MCPServer` 생성자가 `instructions`를 받는지 먼저 확인하고, 안 받으면 이 항목은 빼고 보고한다.
6. **CHANGELOG.md** + **.github/workflows/test.yml**(push·PR에 `uv sync` → `uv run pytest -q`, macos-latest, Python 3.12).
7. **scripts/smoke_stdio.py**: 서버 명령을 자식 프로세스로 띄워 JSON-RPC `initialize`를 보내고 `serverInfo.name`을 찍는 30줄 안팎 스크립트(V1·V2용).

## 검증
- V1 새 설치: 빈 임시 디렉토리에서 `UV_CACHE_DIR`을 임시로 두고 `uvx --python 3.12 --from git+https://github.com/Imtylerrrrrr/logic-mcp@<브랜치> logic-mcp`를 띄워 stdin으로 JSON-RPC `initialize`를 보내고 `serverInfo.name == "logic-mcp"` 응답을 받는다(스크립트 `scripts/smoke_stdio.py`). 네트워크 설치 1회 = 예시 1회.
- V2 Claude Code: 임시 프로젝트 디렉토리에서 `claude mcp add` 뒤 `claude mcp list`에 연결됨 → 끝나면 `claude mcp remove`.
- V3 Claude Desktop: JSON 예시의 문법만 검사(`python -m json.tool`). 실제 Desktop 연결은 사용자가 확인.
- V4 `uv run pytest -q`(3.14 로컬)와 3.12 격리 환경 모두 통과.
- V5 calibrate 액션: 툴 단위 테스트(force 없음 → skipped, force → 호출). 실기는 Space Designer 수집으로 함수 자체가 검증돼 있어 생략.
- V6 워크플로: 브랜치 push 뒤 Actions 결과 확인(실패하면 수정 후 재확인).

## 구현자에게 맡기는 것
문서 문장, CHANGELOG 항목 묶음, instructions 정확한 문구(위 네 줄 범위 안에서), 워크플로 세부(캐시 등).

## 내가 정한 것(사용자가 뒤집을 수 있음)
- PyPI는 이번에 안 올린다. git 설치로 충분하고, 올리면 되돌리기 어렵다.
- 태그·릴리스는 사용자 확인 뒤.
- CI는 테스트 워크플로 하나만.
