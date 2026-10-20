# 변경 기록

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다.

## [0.1.0] - 미정(태그 때 날짜)

### Added
- 툴 8개: 트랜스포트·트랙·믹서·뱅크 (`logic_transport`, `logic_track`, `logic_mixer`, `logic_bank`, `logic_session`)
- Channel EQ (`logic_eq`): 밴드 8개의 주파수·게인·Q·슬로프·온/오프 읽기·쓰기
- 인서트 플러그인 (`logic_plugin`): 목록·삽입·제거·바이패스·파라미터 읽기·쓰기·스캔·calibrate
- 센드 (`logic_send`): 목적지·레벨·위치·뮤트 읽기·쓰기, 제거
- 번들 파라미터 표 10종 357개 (Logic Pro 12.0.1 실측)
- 서버 instructions (클라이언트가 시작 순서를 받는다)
- 문제 해결 문서 `docs/troubleshooting.md`
- Python 3.12 지원, stdio 스모크 스크립트 `scripts/smoke_stdio.py`, 테스트 워크플로

## 릴리스 절차(메모)

`uv build` → `gh release create v0.1.0 dist/*`. PyPI는 쓰지 않는다(`uv publish`는 하지 않음).
