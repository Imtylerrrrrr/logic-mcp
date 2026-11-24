[한국어 (Korean)](CHANGELOG.ko.md) / [English](CHANGELOG.md)

# 변경 기록

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다.

## [Unreleased]
### Added
- Logic 12.0.1 삽입 메뉴의 플러그인 67종 전부에 번들 파라미터 표(이전 10종). MCU로 보이는 메뉴 항목마다 표가 있고, 파라미터는 모두 1,064개. Space Designer(178)·EVOC 20 Filterbank(61)가 가장 크다.
- `SECURITY.md`(취약점 제보 방법, 서버가 건드리는 것), Python 의존성과 GitHub Actions용 Dependabot 설정, 신뢰 게시로 PyPI에 올리는 수동 `publish` 워크플로. README 주의 섹션에 서버가 건드리는 것과 제거 방법을 적었다.
- `scripts/calibrate_batch.sh [strip] "이름" ...`: 여러 플러그인을 차례로 `calibrate_plugin.py --write --yes`로 수집한다. 번들에 이미 있는 이름은 건너뛰고, 플러그인마다 로그를 `~/.logic-mcp/calib-logs/`에 남긴다.
- `logic_plugin set`과 `logic_eq set`의 `changes=[...]`: 같은 플러그인(또는 Channel EQ)의 값을 최대 32개까지 한 호출, 편집 뷰 한 번 진입으로 맞춘다. 항목은 받은 순서대로 적용하고, 보내기 전에 전부 검사하며, 첫 실패에서 멈추고 `after.results`·`after.remaining`을 돌려준다. 이미 맞춘 값은 그대로 둔다. 한 개짜리 `set`은 달라지지 않는다.

### Changed
- 숫자 `set`은 목표가 컨트롤 서피스의 두 단계 사이에 있으면 가까운 단계에 맞추고 ok로 돌려준다. 이전에는 두 단계 사이를 10회 오가다 실패했다(예: Compressor Release 300은 290과 310 사이). `note`에 두 단계가 적힌다.
- 내부 리팩토링(동작 변화 없음): Aux Plug-in Mixer 경로를 `plugin_mixer.py`로, `calibrate`/`scan`을 `plugins/calibrate.py`로, set 공통 로직(숫자/선택지 판별, `#n`·선택지 선택, 결과 판정)을 `setter.py`로 옮겨 `logic_plugin set`과 `logic_eq set`이 함께 쓴다.

### Fixed
- Logic이 Cursor ◀/▶ 누름을 몇 초 늦게 처리하면(실측 최대 3.8초) `logic_plugin` `get`/`set`이 다른 페이지의 같은 열을 읽고 쓰던 문제. Compressor Release를 바꾸려던 값이 다음 페이지의 Distortion에 들어갔다. 이제 페이지 수 확인은 반응 없는 누름을 3초 더 기다리고, 표가 여러 페이지인데 끝까지 반응이 없으면 1페이지로 보지 않고 실패한다. 페이지 이동은 페이지 토큰이나 값 행이 바뀔 때만 센다. 페이더·V-Pot을 보내기 직전마다 LCD의 축약명을 표의 그 페이지와 비교하고, 다르면 보내지 않는다(note가 `guard:`로 시작). 번들 표와 배치가 다른 인스턴스도 같은 이유로 거부된다: 스테레오 인스턴스에서 66종 중 15종이 파라미터 묶음을 두 번 보이거나 좌·우 파라미터를 따로 둔다(예: PlatinumVerb `Dry`·`Wet`). 이전에는 이런 파라미터가 표의 위치대로 다른 파라미터에 쓰였다. `docs/troubleshooting.ko.md` 7번 참고.
- 맨 끝 LCD 열의 값을 오버레이가 떠 있는 동안 틀리게 읽던 문제. 그 열의 오버레이는 오른쪽 정렬이라 6자를 넘으면 7열로 넘치는데, `-24.0 dB`를 `4.0 dB`로 읽었다. `set`이 틀린 값에서 `verified`를 보고할 수 있었고(Compressor 사이드체인 `Gain` 3 → 실제 23 dB), 캘리브레이션이 이런 파라미터의 범위를 틀리게 배웠다. 이제 넘친 글자까지 읽는다. 번들 표의 맨 끝 열 파라미터 범위를 Logic 12.0.1에서 다시 쟀다: 16개 플러그인에서 틀린 범위 14개를 고치고(Compressor `Gain` 0~4 → −24~24 dB, 주파수 `20~0` → 20~20000 Hz 여러 건, Tape Delay `Delay Time` 0.3~9.9 → 0.3~4999.9 ms) 비어 있던 16개를 채웠다.
- 페이지가 많은 플러그인의 뒤쪽 페이지를 본 직후 다른 플러그인을 열면 슬롯이 차 있는데도 `empty_edit`로 실패하던 문제(Compressor 3페이지 뒤 Chorus). Logic은 편집 뷰를 직전 페이지 위치로 열고, 페이지가 더 적은 플러그인은 그 자리에서 빈 슬롯과 같은 화면을 보인다. 이제 Cursor ◀를 한 번 눌러 그 플러그인의 마지막 페이지로 온다.
- 파라미터 하나를 LCD 두 칸에 걸쳐 그리는 구형 플러그인(Silver Compressor `Threshold`, Parametric EQ `Frequency` 등 14종)을 한 파라미터로 읽는다. 이름·값이 칸을 꽉 채우면 다음 칸과 잇는다. 이전에는 뒷칸이 유령 파라미터(`ld`, `cy`)가 되고 이름이 잘렸다. 번들 표 14개를 재수집했다. 남은 한계: set·프로빙 때 값은 여전히 한 칸만 읽어, Parametric EQ·Exciter·Low Pass Filter·High Pass Filter의 `Frequency`는 범위 map이 없고 숫자 set이 아직 안 된다.
- `2.0  :1`처럼 단위 앞에 공백이 둘인 비율 값을 숫자로 읽어 Silver Compressor Ratio를 set할 수 있다.
- 숫자 `set`의 목표가 캘리브레이션 범위 밖이면(GoldVerb Room Size 1500, 표는 10~200 m) 페이더를 끝까지 보내고 "LCD 반응 없음"이라 하는 대신 범위를 적어 skipped로 끝낸다.
- `logic_plugin set`이 선택지가 정확히 Off/On인 파라미터에 0/1을 받는다(이전에는 "1"이 절대 맞지 않았다).
- 선택지 텍스트를 16스텝 안에 못 찾으면 파라미터를 시작 위치로 되돌리고 그렇게 적는다(이전에는 멈춘 자리에 남겼다).
- `logic_plugin` `insert`가 캐시 목록 이름이 오버레이 21칸에서 잘린 플러그인(`EVOC 20 TrackOscillat`)도 편집 뷰 헤더에 전체 이름이 보이면 받아들이고 전체 이름으로 보고한다. 이전에는 플러그인이 슬롯에 들어갔는데도 unverified로 끝났다.
- V-Pot 틱 한 번이 화면에 보이는 단위보다 작을 때(예: Compressor Ratio 1.4·1.6·1.8) 숫자 `set`이 "V-Pot 틱에 LCD 반응 없음"으로 실패하던 문제를 고쳤다. 반응이 없으면 최대 6틱까지 계속 돌려 본 뒤에야 반응 없음으로 판단한다. 번들 Compressor Ratio 범위는 이제 로그 곡선이다.

## [0.1.2] - 2026-11-02
### Added
- `logic_plugin` `move`: 플러그인을 빈 슬롯(`to_slot`)으로 옮긴다(제거 뒤 재삽입). MCU에 이동 명령이 없어 플러그인 설정값은 초기화된다. 제거 뒤 재삽입이 실패하면 unverified로 플러그인 이름을 알려 직접 다시 넣을 수 있게 한다.
- `logic_plugin` `insert`가 캐시 목록 위치에 다른 플러그인이 보이면(프로젝트마다 메뉴 순서가 다름) 삽입 메뉴를 이름으로 훑는다. 캐시 목록에 없는 이름은 접두 일치로 찾는다(`note`는 `name_scan:<틱 수>`). 오버레이에 요청한 이름이 보이지 않으면 확정하지 않는다.
- 트랙이 없는 Aux 스트립을 TRACK 홀드 메뉴 Input 열(`Bus n`)로 가려낸다. Plug-in Channel 뷰는 Aux 스트립을 따라가지 않고(실측), Send Channel·EQ Channel 뷰도 따라가지 않는다고 가정한다(가정, 미측정). 그래서 Aux 스트립의 플러그인·센드·EQ 명령은 직전에 선택한 트랙을 바꾸는 대신 skipped로 끝난다. Aux 스트립의 플러그인 슬롯 1은 Plug-in Mixer 뷰로 삽입·제거할 수 있고, `list`는 Aux 스트립의 슬롯 1만 보고한다(결과의 `aux`).
- 플러그인 명령은 편집 뷰 헤더의 트랙 번호(`Track <n>`)가 대상 스트립 번호와 같은지 확인한다. Aux로 가려내지 못한 스트립이라도 채널 뷰가 다른 트랙을 보여 주면 조용히 바꾸지 않는다.
- `logic_plugin` `set`에서 선택지 파라미터는 `"#n"`으로 n번째 선택지를 고를 수 있다(1부터). 첫 선택지까지 돌린 뒤 n-1칸 나아간다. LCD 6자 칸에서 여러 선택지가 같은 텍스트로 보이면 그 이름은 skipped로 끝나고 note에 번호를 알려 준다. calibrate한 선택지 표가 없으면 `#n`도 움직이지만 결과는 unverified이고 도착한 텍스트만 보고한다. 숫자 파라미터에 `#n`을 주면 skipped. 표에서 하나뿐인 이름은 지금 선택지도 표에서 하나뿐이면 차이만큼만 움직인다(되감기 없음, `already` 유지).

### Changed
- `set` 기본 허용 오차를 넓혔다: 0.2 dB(이전 0.1), 단위가 있는 그 밖의 값 2 %(이전 1 %). 숫자 설정의 보정은 최대 10회(이전 6회). `tolerance`를 주면 그 값이 우선한다.
- LCD 축약은 플러그인 이름의 부분 수열일 때만 배운다(공백·`-`·`.`·`/`·`*`·대소문자 무시). 드러내기가 이웃 메뉴 항목을 보인 경우(`Tuner` → "Channel EQ")는 배우지 않고, 사용자 캐시 파일에 이미 있는 맞지 않는 항목은 불러올 때 버린다.

### Fixed
- 범위 프로빙이 LCD 6자 칸에서 잘린 단위를 받아들이고(Compressor Release `5.0 ms` … `5000.0`), 양 끝이 양수이고 100배보다 넓으면 로그 매핑으로 추정한다. 이제 Compressor Release를 설정할 수 있다.
- `calibrate`가 선택지를 텍스트가 반복되면 멈추는 대신 고정 틱 수로 모은다. 축약 텍스트가 같은 선택지도 순서대로 모두 남는다. 목록 맨 끝에 연속된 같은 텍스트는 여전히 하나로 합쳐진다. 선택지 파라미터마다 calibrate가 30초쯤 더 걸린다.
- 이름으로 선택지를 고를 때 틱마다 값 오버레이(약 2초)가 걷힌 뒤 읽는다. 전에는 오버레이 텍스트(`VinOpt` 위의 `Vintage`)를 읽어 목록 끝으로 오인하고 선택지를 못 찾을 수 있었다.
- 번들의 Compressor·Noise Gate·Stereo Delay 표를 다시 수집했다. Release와 Stereo Delay 시간 맵이 바로잡혔고(이전 맵은 잘못 수집됨), Compressor Circuit Type은 선택지 7개를 모두 갖는다.

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
