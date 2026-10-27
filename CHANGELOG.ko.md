[한국어 (Korean)](CHANGELOG.ko.md) / [English](CHANGELOG.md)

# 변경 기록

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다.

## [Unreleased]
### Added
- `logic_plugin` `move`: 플러그인을 빈 슬롯(`to_slot`)으로 옮긴다(제거 뒤 재삽입). MCU에 이동 명령이 없어 플러그인 설정값은 초기화된다. 제거 뒤 재삽입이 실패하면 unverified로 플러그인 이름을 알려 직접 다시 넣을 수 있게 한다.
- `logic_plugin` `insert`가 캐시 목록 위치에 다른 플러그인이 보이면(프로젝트마다 메뉴 순서가 다름) 삽입 메뉴를 이름으로 훑는다. 캐시 목록에 없는 이름은 접두 일치로 찾는다(`note`는 `name_scan:<틱 수>`). 오버레이에 요청한 이름이 보이지 않으면 확정하지 않는다.
- 트랙이 없는 Aux 스트립을 TRACK 홀드 메뉴 Input 열(`Bus n`)로 가려낸다. Plug-in Channel 뷰는 Aux 스트립을 따라가지 않고(실측), Send Channel·EQ Channel 뷰도 따라가지 않는다고 가정한다(가정, 미측정). 그래서 Aux 스트립의 플러그인·센드·EQ 명령은 직전에 선택한 트랙을 바꾸는 대신 skipped로 끝난다. Aux 스트립의 플러그인 슬롯 1은 Plug-in Mixer 뷰로 삽입·제거할 수 있고, `list`는 Aux 스트립의 슬롯 1만 보고한다(결과의 `aux`).
- 플러그인 명령은 편집 뷰 헤더의 트랙 번호(`Track <n>`)가 대상 스트립 번호와 같은지 확인한다. Aux로 가려내지 못한 스트립이라도 채널 뷰가 다른 트랙을 보여 주면 조용히 바꾸지 않는다.
- `logic_plugin` `set`에서 선택지 파라미터는 `"#n"`으로 n번째 선택지를 고를 수 있다(1부터). 첫 선택지까지 돌린 뒤 n-1칸 나아간다. LCD 6자 칸에서 여러 선택지가 같은 텍스트로 보이면(Compressor Circuit Type `Studio`, `Vintag`) 그 이름은 skipped로 끝나고 note에 번호를 알려 준다. calibrate한 선택지 표가 없으면 `#n`도 움직이지만 결과는 unverified이고 도착한 텍스트만 보고한다.

### Changed
- `set` 기본 허용 오차를 넓혔다: 0.2 dB(이전 0.1), 단위가 있는 그 밖의 값 2 %(이전 1 %). 숫자 설정의 보정은 최대 10회(이전 6회). `tolerance`를 주면 그 값이 우선한다.
- LCD 축약은 플러그인 이름의 부분 수열일 때만 배운다(공백·`-`·`.`·`/`·`*`·대소문자 무시). 드러내기가 이웃 메뉴 항목을 보인 경우(`Tuner` → "Channel EQ")는 배우지 않고, 사용자 캐시 파일에 이미 있는 맞지 않는 항목은 불러올 때 버린다.

### Fixed
- 범위 프로빙이 LCD 6자 칸에서 잘린 단위를 받아들이고(Compressor Release `5.0 ms` … `5000.0`), 양 끝이 양수이고 100배보다 넓으면 로그 매핑으로 추정한다. 이제 Compressor Release를 설정할 수 있다.
- `calibrate`가 선택지를 텍스트가 반복되면 멈추는 대신 고정 틱 수로 모은다. 축약 텍스트가 같은 선택지(Compressor Circuit Type)도 순서대로 모두 남는다. 목록 맨 끝에 연속된 같은 텍스트는 여전히 하나로 합쳐진다.
- 번들의 Compressor·Noise Gate Release와 Stereo Delay Left/Right Delay Time 맵은 잘못 수집된 것이라 지웠다. 이 파라미터들은 첫 `set`에서 프로빙한다.

## [0.1.1] - 2026-10-22
### Changed
- 기본 언어를 영어로 전환: README·문제 해결 문서·CHANGELOG·`logic-plugins` 스킬·MCP 툴 설명·서버 instructions가 영어. 한국어판은 `*.ko.md` 파일로 분리하고 맨 위에서 상호 링크.
- README의 Quick start 예시를 영어로.

## [0.1.0] - 2026-10-22

### Added
- 툴 8개: 트랜스포트·트랙·믹서·뱅크 (`logic_transport`, `logic_track`, `logic_mixer`, `logic_bank`, `logic_session`)
- Channel EQ (`logic_eq`): 밴드 8개의 주파수·게인·Q·슬로프·온/오프 읽기·쓰기
- 인서트 플러그인 (`logic_plugin`): 목록·삽입·제거·바이패스·파라미터 읽기·쓰기·스캔·calibrate
- 센드 (`logic_send`): 목적지·레벨·위치·뮤트 읽기·쓰기, 제거
- 번들 파라미터 표 10종 357개 (Logic Pro 12.0.1 실측)
- 서버 instructions (클라이언트가 시작 순서를 받는다)
- 문제 해결 문서 `docs/troubleshooting.ko.md`
- Python 3.12 지원, stdio 스모크 스크립트 `scripts/smoke_stdio.py`, 테스트 워크플로

## 릴리스 절차(메모)

`uv build` → `gh release create v0.1.0 dist/*`. PyPI는 쓰지 않는다(`uv publish`는 하지 않음).
