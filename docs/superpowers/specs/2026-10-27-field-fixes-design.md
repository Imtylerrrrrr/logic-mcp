# 스펙 4: 실전 수정(field fixes) 설계 (Korean)

2026-10-24 guitartone 프로젝트 실전 투입에서 드러난 결함(`docs/progress.md` "실전 사용 교훈" F1·F2·F4)과 사용자가 아쉬워한 "슬롯 순서 변경"을 다룬다. 기준 커밋 main fd60b19.

## 의도
MCP 사용자가 실제 프로젝트에서 플러그인을 넣고 빼고 옮길 때, 도구가 (1) 캐시 목록이 어긋나도 이름으로 정확히 넣고, (2) Aux 스트립을 미리 가려 엉뚱한 트랙에 넣지 않으며, (3) 숫자 값을 페이더 분해능·표시 정밀도 안에서 맞추고, (4) 슬롯 이동을 제거+재삽입으로 흉내 낼 수 있게 한다.

## 목표 / 비목표 / 반(反)목표
- 목표: F1 이름 탐색 폴백, F2 Aux 판정(Z19)과 슬롯 1 Mixer 뷰 경로, F4 허용 오차·보정 횟수, F5 `plugin move`.
- 비목표: Compressor·Noise Gate `Release` 로그 매핑 재수집(테스트 프로젝트에서 calibrate 필요), Aux의 센드·EQ 지원 여부 측정, 축약명 오학습(F6: `TO3000`→`Splice Sounds Listene`) 정리, 설정값을 보존하는 순서 변경(MCU에 이동 명령 없음).
- 반목표: 미리 선택(pre-select) 상태에서 확정을 누르는 경로가 늘어나 엉뚱한 트랙에 삽입되는 것. 모든 새 경로는 누르기 전에 대상 스트립과 오버레이 이름을 확인한다. Logic UI 조작·AX 자동화 없음(MIDI만).

## 실측 근거
- Z19(2026-10-27): TRACK 홀드 메뉴 항목 3 `Input` → CS 뷰 2행이 오디오 트랙 `1`, Aux `Bus 1`·`Bus 2`, 출력·Master 빈칸. Volume 복원 뒤 Output 열은 트랙·Aux 모두 `St Out`. → Aux = Output 비어 있지 않음 ∧ Input이 `Bus`로 시작.
- F2(10/24): Aux를 선택하고 PL에 들어가도 2행은 **선택 전 트랙**의 슬롯. 그 상태에서 미리 선택+확정하면 그 트랙에 삽입된다. Plug-in Mixer 뷰(`plugin_mixer`)는 V-Pot n = 스트립 n의 슬롯 1이라 Aux 슬롯 1 삽입이 됐다(Tape Delay·ChromaVerb). 확정 뒤 편집 뷰는 선택 트랙 기준이라 헤더 검증은 못 한다 → 삽입 검증은 Mixer 뷰 2행의 해당 열 텍스트 변화로.
- F1(10/24): 캐시 위치 58에 'Tremolo'(기대 Channel EQ). `--`로 되감고 1틱씩 오버레이를 읽어 이름이 맞으면(0.4초 뒤 재확인) 확정 → 9종 58~111틱 안에 verified.
- 제거는 슬롯을 당겨 채우지 않는다(10/24 트랙 1 슬롯 1 제거 뒤 `1: --, 2: TO3000 …`). 따라서 "이동"은 제거 + 빈 목표 슬롯에 재삽입으로 흉내 낼 수 있다(설정값 초기화).
- F4(10/24): Channel EQ Low Shelf Gain 목표 3 → 6회 뒤 +3.2(허용 0.1), Peak 3 Freq 3500 → 3380(허용 35), High Shelf Freq 5000 → 5200(허용 50). 모두 "fader+보정" 경로에서 6회 소진.

## 설계

### F1. `insert` 이름 탐색 폴백 (`src/logic_mcp/logic/plugin.py`, `plugins/scan.py`)
- 현행: 캐시 위치로 `2·idx` 틱 → 3회 근처 보정 → 불일치면 unverified("`logic_plugin scan` 권장").
- 변경: 보정 3회 뒤에도 불일치면 **이름 탐색**으로 넘어간다. `rewind_to_empty` → `SCAN_STEP`(1틱)씩 전진하며 `strip_suffix(read_overlay_text)`를 읽고, `normalize(shown) == normalize(want)`면 0.4초 뒤 한 번 더 읽어 같을 때 멈춘다(실측 S: 오버레이 지연). 상한은 `scan_list`와 같은 `MAX_ITEMS * ITEM_TICKS`와 `STALE_LIMIT`, 그리고 `--`로 한 바퀴 돌면 중단. 찾으면 기존 확정·헤더 검증 경로 그대로. 못 찾으면 unverified, note에 "이름 탐색 N틱 뒤에도 못 찾음(마지막 '…'). 설치 목록이 다른 듯. `logic_plugin scan` 권장".
- 캐시에 이름이 없을 때(`find`가 None이고 후보도 없음): 지금은 skipped. 변경: 바로 이름 탐색을 시도하되 비교는 `normalize(shown).startswith(normalize(query))`(접두 일치)로, 찾은 전체 이름을 `after.plugin`으로 돌려준다. 후보가 여럿(`cands`)이면 지금처럼 skipped.
- 성공 시 `note`에 경로를 남긴다: `""`(캐시 위치) / `"name_scan:<틱수>"`.
- 새 헬퍼 `scan.py: seek_by_name(d, ch, want, prefix=False) -> tuple[bool, int, str]`(찾음, 틱 수, 마지막 텍스트). `scan_list`와 틱·stale 규칙을 공유한다.

### F2. Aux 스트립 판정과 슬롯 1 Mixer 경로 (`strips.py`, `modes.py`, `plugin.py`, `commands.py`)
- `StripKinds.cache` 값을 `bool`에서 `StripKind = Literal["track", "aux", "output"]`로 바꾼다. 판정은 한 번에: `read_strip_outputs()`와 같은 경로로 `Input` 열(`TRACK_MENU_INPUT = (3, "Input")`)도 읽는다(`modes.read_strip_kinds() -> list[StripKind]`: Output 빈칸 → output, Input `Bus…` → aux, 그 외 → track). 기존 `follows()`는 `kind != "output"`을 유지하되, 새 `kind(d, state, ch)`를 추가. 홀드 메뉴 두 번(Input, Output) + Volume 복원 한 번. `_cs_dirty` 규칙 그대로.
- `Commands._channel(ch, kind)`: 스트립이 `aux`이고 kind가 `plugin_channel`/`send`/`eq`이면 `StripUnsupported`의 자매 예외 `StripAux(ch, number, name)`(note: "스트립 N(Aux …)은 채널 뷰(PL·SE·EQ)가 따라가지 않음(실측 Z19). 플러그인은 슬롯 1 삽입·제거만 Plug-in Mixer 뷰로 지원")를 던진다. `_guarded`에서 `StripAux` → skipped e.note.
- `plugin.insert`·`plugin.remove`는 **슬롯 1 ∧ aux**일 때 Mixer 경로를 쓴다:
  - `b._fresh()` → `d.enter("plugin_mixer")` → `d.view.index`가 1이 아니면 unverified("Mixer 뷰 슬롯이 N") → 열 `ch`의 2행 텍스트가 `EMPTY_TEXTS`인지로 비어 있음 판정(insert는 비어 있어야, remove는 차 있어야) → insert: `rewind_to_empty(d, ch)` + F1 이름 탐색(`seek_by_name`) → `press_vpot_until(ch, …)`은 편집 뷰를 기대하지 않고 `d.settle_smart()` 뒤 다시 `enter("plugin_mixer")`하여 열 `ch` 텍스트가 바뀌었고 다른 7열은 그대로인지로 verified. remove: `rewind_to_empty` → 누름 → 같은 방식으로 `--` 확인.
  - 슬롯 2~8의 aux는 `StripAux` skipped.
  - 결과 `after`에 `"path": "mixer"`를 넣는다.
- `plugin.list`: aux 스트립 행은 슬롯 1만(Mixer 뷰에서 읽은 텍스트) 채우고 2~8은 `null`, `unsupported`와 별도로 `"aux": [스트립 번호…]`를 돌려준다. 현재처럼 선택 트랙 슬롯을 그대로 보고하는 오인은 없앤다.
- 툴 설명(`server/tools.py`, 영어): logic_plugin에 "Aux strips (no track): only slot 1 insert/remove, via the Plug-in Mixer view." logic_send·logic_eq는 변경 없음(Aux 센드·EQ 지원 여부는 미측정이므로 지금 동작 유지).
- 문서: `docs/mcu-protocol.md`에 Z19 항목 추가(위 실측 그대로).

### F4. 허용 오차·보정 횟수 (`values.py`, `setter.py`)
- `tolerance_for`: dB 0.1 → 0.2(표시 1자리, 페이더 보정이 ±0.2 안에서 흔들림), Hz 등 단위 있는 값 1% → 2%, 단위 없는 값 2% 유지. 사용자가 `tolerance`를 주면 그대로.
- `MAX_ROUNDS` 6 → 10. 실패 note는 횟수를 그대로 보여준다.
- 기존 테스트의 기대값이 바뀌는 곳만 수정(테스트를 약화시키지 않는다 — 새 기본값을 검증하도록 숫자만 바꾼다).

### F5. `plugin move` (`plugin.py`, `server/tools.py`)
- 시그니처: `logic_plugin(action="move", strip|number, slot=from, to_slot=to)`. `to_slot` 새 인자(1~8, move 전용).
- 절차(한 `_guarded` 안에서): ① `_open_edit(ch, from)`으로 헤더 전체 이름 확보(축약명 캐시를 믿지 않는다, F6 회피) → `d.enter("plugin_channel")` ② 목표 슬롯이 `EMPTY_TEXTS`가 아니면 skipped("슬롯 N에 … 있음") ③ `remove(from)` 경로 ④ `insert(to, full_name)` 경로(F1 폴백 포함). ⑤ after: `{"from": a, "to": b, "plugin": name}`, note "설정값은 초기화됨(MCU에 이동 명령이 없어 제거+재삽입)". ③ 성공 ④ 실패면 unverified에 "제거는 됐으나 재삽입 실패: …"를 남긴다(되돌리지 않는다 — 되돌리기도 삽입이라 같은 실패 가능).
- aux 스트립은 `StripAux` skipped(슬롯 1 하나뿐이라 이동 의미 없음).
- 툴 설명에 한 줄: "move: remove + reinsert into an empty slot; plug-in settings are reset."

## 검증
- 단위 테스트(가짜 Logic): F1 폴백이 캐시 불일치에서 이름으로 찾는 경우·못 찾는 경우·접두 일치, F2 `read_strip_kinds` 세 종류·aux 슬롯 1 insert/remove Mixer 경로·슬롯 2 skipped·list의 aux 행, F4 기본 오차 숫자, F5 성공·목표 슬롯 점유·재삽입 실패.
- 실기: guitartone 프로젝트(저장 안 함)에서 ① 트랙 2 슬롯 8에 `insert "Channel EQ"` 뒤 `remove`(F1 경로 note 확인) ② Aux1 `plugin list`가 슬롯 1만 보고하는지, Aux1 슬롯 2 insert가 skipped인지 ③ 트랙 2 Channel EQ Low Shelf Gain 3 dB set이 10회 안에 verified인지 ④ 트랙 2에서 빈 슬롯 8로 `move` 뒤 되돌리기. 결과는 `docs/progress.md`에 기록.

## 빌더에게 맡기는 것
- `seek_by_name`의 stale 처리 세부, 테스트 가짜(`tests/fakes.py`)에 Input 열·Mixer 뷰 행을 넣는 방식.
- `StripKind` 캐시 키·무효화는 기존 `(number, name)` 규칙 유지.
- 영어 문구(툴 설명·CHANGELOG)는 기존 톤에 맞춘다. 코드 note 문자열은 기존처럼 한국어.
