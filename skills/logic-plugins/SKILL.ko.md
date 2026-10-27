[한국어 (Korean)](SKILL.ko.md) / [English](SKILL.md)


# Logic Pro 플러그인·EQ·센드 조작 (logic-mcp)

## 시작할 때
1. `logic_session wait_ready` → `logic_session configure`(처음 한 번. Logic이 서피스를 다시 설치한 뒤에도 한 번 더).
2. `logic://plugins` 리소스를 읽는다. `scanned_at`이 없거나 `logic_version`이 다르면 `logic_plugin scan`을 권한다(60~180초, 빈 슬롯 1개 필요, 화면의 슬롯이 깜박이지만 삽입은 없음).

## 플러그인
- 캐시 목록 위치에 다른 플러그인이 보이거나 이름이 목록에 없으면 `insert`가 삽입 메뉴를 이름으로 훑는다(모르는 이름은 접두 일치, `note`는 `name_scan:<틱 수>`, 최대 2~3분). 그래도 못 찾으면(`unverified`, 확정 없음) `scan` 뒤 다시. 차 있는 슬롯은 `replace=true`가 있어야 바꾼다.
- `move`(slot → 빈 `to_slot`)는 제거 + 재삽입이라 플러그인 설정값이 초기화된다. 결과가 "제거는 됐으나 재삽입 실패"면 그 이름의 플러그인을 직접 다시 넣는다.
- `params`를 먼저 읽고 `short`(축약명)나 `index`로 `get`/`set`. 마지막 페이지는 index가 건너뛸 수 있으니 params가 준 index를 그대로 쓴다.
- 서드파티가 이름 없이 `Control #N`(0~1000)만 주면 index로 다루고 값은 0~1000 정수.
- 인서트 슬롯은 1~8만.

## EQ
- `logic_eq get`은 삽입하지 않는다. `set`은 EQ가 없으면 `allow_insert`(기본 true)에 따라 Channel EQ를 넣는다. 밴드 1·8은 gain 대신 slope(6/12/18/24/36/48).

## 센드
- `logic_send set_dest`의 dest는 버스 번호("Bus 3", "3", 3) 또는 "--"(제거). 버스 센드를 새로 만들면 Logic이 Aux 트랙을 자동 생성해 **뒤 트랙 번호가 바뀐다** → 이어서 number로 부르기 전에 `logic://strips`를 다시 읽는다.
- 레벨은 dB(-inf..+6.0), 위치 pre|post|post_pan, 뮤트는 on. 센드가 없는 번호에 레벨·위치·뮤트는 skipped.

## 지원하지 않는 것
- 출력(Stereo Out)·Master 스트립: EQ 채널·플러그인·센드 명령은 `skipped`(Logic의 채널 뷰가 그 스트립을 따라가지 않아 엉뚱한 트랙을 바꾸게 된다). `eq get`은 EQ 유무만 알려 준다.
- Aux 스트립(트랙 없음, `plugin list`의 `aux`): 플러그인 슬롯 1 삽입·제거만 된다(Plug-in Mixer 뷰 경로). `list`는 슬롯 1만 보고한다. 그 밖의 플러그인 명령·센드·EQ는 `skipped`.
- 인서트 슬롯 9~15, 악기·MIDI FX 슬롯, 서라운드, 버스가 아닌 센드 목적지.

## 안전
- 모든 명령은 끝나면 PAN 모드·Flip 꺼짐으로 돌아온다. `verified`가 아니면 결과를 믿지 말고 `note`를 읽는다.
- 스펙 1 도구(`logic_track` mute/solo/select, `logic_transport`, `logic_bank`)는 어사인먼트 뷰 중에도 안전하다. `logic_mixer`의 set_volume·set_pan은 스스로 PAN으로 돌아간 뒤 실행한다.
- Logic을 다시 켠 뒤 EQ·플러그인·센드 명령이 전부 `unverified`("버튼 반응 없음")이면 Logic Pro → 설정 → 컨트롤 서피스 → 설정…에서 **Mackie Control 장치를 지우고** 다시 연결하도록 사용자에게 안내한다(MPK 등 다른 장치는 건드리지 않음, "기본값 재형성"은 누르지 않음).
