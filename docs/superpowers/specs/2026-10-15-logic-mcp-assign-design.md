# logic-mcp 스펙 2 — Send/EQ/Plug-in 모드 + Flip (설계)

작성 2026-10-15. 스펙 1(`2026-10-14-logic-mcp-core-design.md`)이 만든 코어(Surface, 상태 리듀서, Commands, MCP 서버) 위에 MCU의 어사인먼트 모드(EQ, SEND, PLUG-IN)와 FLIP을 올린다. 모든 수치·레이아웃은 Logic Pro 12.0.1에서 3회 스파이크로 실측했다(`~/logic-mcp-spike/스펙2-스파이크.md`, 원시 로그 `cap_assign{,2,3}.log`).

## 1. 목적과 범위

Claude가 Logic 프로젝트의 **Channel EQ, 인서트 플러그인, 센드**를 읽고 정확한 값으로 바꾼다. 사용자 우선순위: EQ → 플러그인 → 센드. 셋 다 이 스펙에 들어가며, 바이패스 토글은 포함하되 마지막 순위다.

스펙 2가 끝나면 다음이 된다.
- "보컬 트랙 밴드 3을 1 kHz, -3 dB로" → `logic_eq set` 한 번에 verified.
- "3번 트랙 2번 슬롯에 Compressor 넣고 Threshold -20 dB" → `logic_plugin insert` + `set`.
- "어떤 트랙에 뭐가 꽂혀 있나" → `logic_plugin list`, `logic://inserts`.
- "리버브 센드 -6 dB" → `logic_send set_dest` + `set_level`.
- 사용자마다 다른 서드파티 플러그인은 `logic_plugin scan`으로 목록을 만들고, 레포의 스킬이 그 절차를 안내한다.

범위 밖(9절): 소프트웨어 악기 슬롯 편집, MIDI FX 편집, 서라운드, EQ Frequency/Gain 특수 뷰, User 모드, Logic UI 자동화.

구현 계획은 둘로 나눌 수 있다: 2a = 모드 드라이버·상태 모델·값 설정·EQ·플러그인, 2b = 센드·번들 데이터·스캔·스킬. 2a만으로도 사용자 우선순위 두 개가 동작한다.

## 2. 핵심 결정과 근거

1. **모드 드라이버 한 계층이 모든 뷰 전환을 소유한다.** 어사인먼트 모드는 Logic 쪽 전역 상태(선택 트랙, 현재 뷰, 페이지, 미리 선택)를 바꾸므로, 명령마다 "진입 → 작업 → PAN 복귀 + Flip 해제"를 보장하는 한 곳이 필요하다. 스펙 1 도구는 PAN 모드와 Flip 해제를 전제한다.
2. **도구는 도메인별 3개**(`logic_eq`, `logic_plugin`, `logic_send`). 스펙 1에 예약했던 `logic_assign` 하나로 합치면 인자가 모드마다 갈려 스키마가 흐려진다. 겹치지 않는 범위가 호출 정확도를 올린다. `logic_assign` 예약은 폐기한다.
3. **값 설정은 Flip+페이더(거친 위치) 뒤 V-Pot 틱(미세 보정).** 실측: FLIP을 켜면 페이더가 각 V-Pot 파라미터의 절대 위치로 점프하고(EQ 채널 뷰·플러그인 편집 뷰 모두), 페이더를 보내면 파라미터가 그 위치로 간다. 주파수는 로그, 게인 dB는 선형, 열거형은 인덱스 등분이다. 틱만 쓰면 20 Hz → 1 kHz 같은 이동에 수십 틱이 든다.
4. **읽기는 LCD 열 텍스트 + 2초 오버레이.** 값을 바꾸면 Logic이 그 스트립 1~3칸에 전체 이름, 2행에 단위 포함 전체 값을 2.0초 보여준다. 정확한 값은 오버레이에서, 정착 값은 7칸 열에서 읽는다.
5. **플러그인 목록은 번들 + 스캔.** Logic 내장 플러그인과 자주 쓰는 것의 파라미터 표는 레포에 생성 데이터로 넣는다(사용자 지시: 공통 항목 하드코딩 허용). 서드파티·새 버전은 사용자의 Logic에서 스캔해 캐시하고 번들과 병합한다.
6. **미리 선택은 확정(V-Pot 누름)이 있어야 적용된다.** 플러그인 삽입·센드 목적지 모두 돌리기만 하면 깜박이는 미리 선택 상태이고, 모드 전환으로 취소된다. 그래서 스캔은 아무것도 삽입하지 않는다.
7. **자동 삽입은 명시적으로만.** EQ 채널 뷰 진입은 선택 트랙에 Channel EQ를 삽입한다. 읽기는 삽입하지 않는 E1 뷰로 하고, 쓰기만 삽입을 허용하며 결과에 적는다.

## 3. 아키텍처

```
server/tools.py ─ logic_eq / logic_plugin / logic_send
      │
logic/commands.py (스펙 1) ── logic/assign.py (EqCommands, PluginCommands, SendCommands)
      │                              │
      │                     logic/modes.py (ModeDriver: 진입·페이지·확정·복귀)
      │                              │
      │                     logic/values.py (파싱, 매핑, 설정 루프)
      │                              │
      │                     logic/plugins/ (known.json, cache.py, scan.py, match.py)
      └──────────────────────────────┤
                             mcu/surface.py, mcu/state.py (뷰 상태 추가), mcu/protocol.py (노트 추가)
```

### 3.1 ModeDriver (`logic/modes.py`)

Surface와 FaderTable을 받고 Commands의 락을 공유한다. 메서드는 모두 블로킹이며 실패 시 `ModeError(step, expected, observed)`를 던진다.

| 메서드 | 절차 | 확인 |
|---|---|---|
| `focus(strip)` | 스펙 1 `_resolve`로 뱅크를 맞춘 뒤 SELECT(0x18+strip) 누름 | SELECT LED 0.5 s |
| `enter(view, index=None)` | 아래 전환표대로 버튼 누름(필요하면 2회), 또는 홀드 메뉴 선택 | 2자리 표시 0.6 s → 오버레이 만료 대기(§3.3) |
| `page_to(n)` / `page_next()` / `page_prev()` | Cursor ◀▶(0x62/0x63) | 헤더 `Page n/N` 또는 열 이름 변화 0.6 s |
| `slot_to(n)` | Cursor ▼(0x61)로 P1→P2…P15, ▲(0x60)는 반대 방향이며 P1에서 ▲는 MIDI FX `M1`(실측) | 2자리 표시 `P<n>` 0.6 s |
| `preselect(strip, steps)` | V-Pot CC(크기 ≤63씩 분할) | 오버레이 텍스트 변화 0.3 s |
| `confirm(strip)` | V-Pot 누름(0x20+strip) 30 ms | 깜박임 멈춤·값 고정 0.6 s |
| `flip(on)` | FLIP(0x32) | FLIP LED 0.5 s, 페이더 에코 도착 0.8 s |
| `leave()` | FLIP 해제 → PAN(0x2A) | `PN` 0.6 s, FLIP LED off. **모든 명령의 finally에서 호출** |

전환표(실측):

| 목표 뷰 | 2자리 | 조작 |
|---|---|---|
| EQ Mixer | `E1` | PAN 상태에서 EQ 1회 |
| EQ Channel | `EQ` | EQ Mixer에서 EQ 1회 (토글) |
| Send Mixer n | `S<n>` | SEND 1회. **n≥2로 가는 조작은 미실측**(S1에서 Cursor ▶는 센드 1의 다음 파라미터로 감). 이 스펙은 센드 조작을 SE 채널 뷰로 통일하고 S<n>·D<n>은 센드 1 전용 보조 경로로만 쓴다 |
| Send Channel | `SE` | Send Mixer에서 SEND 1회 |
| Send Dest/Level Mixer 1 | `D1` | SEND 홀드(≥0.4 s) + V-Pot7 누름(센드 1만 실측) |
| Plug-in Mixer slot n | `P<n>`(1-9), `10`-`16` | PLUG-IN 1회, 슬롯은 Cursor ▲▼ |
| Plug-in Channel | `PL` | Plug-in Mixer에서 PLUG-IN 1회 |
| Plug-in Edit | `P<n>` 유지 | Plug-in Mixer에서 해당 스트립 V-Pot 누름(기존 플러그인이면 값 보존) |
| 편집 뷰 나가기 | `P<n>` Mixer | PLUG-IN 1회 |
| PAN | `PN` | PAN 1회 |

같은 버튼을 다시 누르면 Mixer ↔ Channel이 토글되므로 드라이버는 현재 뷰를 알고 누른다. 홀드 메뉴는 button-down 즉시 LCD 2행에 뜨고, 메뉴 항목은 누른 채로 V-Pot을 눌러 고른다. EQ 메뉴 `Freq Gain - Bypass - CStrip Fr/GnM Fr/GnC`, SEND 메뉴 `Dest Level Pos Mute CStrip CStr2 Ds/LvM Ds/LvC`. PLUG-IN은 홀드 메뉴가 없다.

### 3.2 상태 모델 추가 (`mcu/state.py`)

```python
@dataclass(frozen=True)
class View:
    kind: str = "pan"        # pan|track|eq_mixer|eq_channel|eq_menu|send_mixer|send_channel|send_destlevel|send_menu
                             # |plugin_mixer|plugin_channel|plugin_edit|midi_fx|empty_edit|unknown
    index: int | None = None # 센드 번호, 플러그인 슬롯
    page: tuple[int, int] | None = None   # (현재, 전체) — 편집 뷰 헤더 `Page 1/6`에서
    header: str = ""         # NAME 모드 1행 전체(트랙, 인서트, 플러그인 이름)
    columns: tuple[tuple[str, str], ...] = ()  # 8 × (이름 7칸, 값 7칸)
    overlay: tuple[int, str, str] | None = None  # (스트립, 전체 이름, 전체 값) — 오버레이가 떠 있을 때
    overlay_until: float = 0.0
    preselect: tuple[int, str] | None = None     # (스트립, 미리 선택 텍스트) — 깜박임 감지 시
```

`SurfaceState.view: View`를 추가한다. 리듀서 규칙:
- `AssignDigit`(CC 0x4A/0x4B)로 `assignment.display`가 바뀔 때 `kind`를 2자리 코드로 결정한다. `P<n>`은 LCD 1행이 `번호:이름` 패턴이면 `plugin_mixer`, `Ins1Pl`로 시작하면 `plugin_channel`, 그 밖이면 `plugin_edit`. 1행이 전부 `-`이고 2행이 공백이면 `empty_edit`(빈 슬롯의 편집 뷰, 플러그인 제거 직후 상태).
- 오버레이 감지: 1행에 `Parameter:`/`parameter:`가 들어 있거나(모드 전환 오버레이), 어느 스트립의 1행 열이 열 경계를 넘는 긴 텍스트로 덮였고 같은 스트립 2행이 단위 포함 값이면 `overlay`를 채우고 `overlay_until = now + 2.0`. 이후 전체 재묘사(offset 0, 길이 ≥56)가 오면 지운다.
- 깜박임: 같은 열에 같은 텍스트와 공백이 0.6~0.9초 간격으로 번갈아 쓰이면 `preselect`로 기록한다. 깜박임 자체는 값이 아니므로 열 값 읽기는 마지막 비공백 텍스트를 쓴다.
- 스펙 1의 `strips[].value_text`는 PAN/TRACK 뷰에서만 갱신한다(다른 뷰의 2행은 파라미터 값이므로 볼륨·팬으로 오해하지 않게).

### 3.3 대기 규칙

| 상황 | 대기 | 근거 |
|---|---|---|
| 모드 전환 뒤 읽기 | 2자리 표시 확인 후 **오버레이 만료(2.0 s) 뒤 첫 재묘사까지**, 상한 2.6 s | 오버레이 2.0 s 실측 |
| 값 쓰기 뒤 정확한 값 | 오버레이 도착 ≤0.6 s → 오버레이에서 파싱 | 전체 값·단위는 오버레이에만 |
| 값 쓰기 뒤 다음 쓰기 | 오버레이 만료까지 기다리지 않아도 됨(새 쓰기가 새 오버레이) | 1차 스파이크 0.4 s 간격 정상 동작 |
| 미리 선택 뒤 확인 | 오버레이 텍스트가 목표 이름이면 즉시 누름 | 깜박임은 2.0 s 뒤 시작, 타임아웃 없음(≥7 s) |
| 페이더(Flip) 뒤 | 에코 ≤0.8 s, 변화 없으면 에코 안 옴 | 스펙 1과 같음 |

## 4. MCP 인터페이스

주소는 스펙 1과 같다: `strip`(현재 뱅크 1-8) 또는 `number`(LCD `번호:` 접두사), 둘 중 하나. 결과는 스펙 1 `ToolResult`(ok, verified, action, target, before, after, elapsed_ms, note).

### 4.1 `logic_eq`

Channel EQ 8밴드. 밴드 번호와 파라미터: 1 Low Cut(freq, slope, q, on), 2 Low Shelf(freq, gain, q, on), 3-6 Peak 1-4(freq, gain, q, on), 7 High Shelf(freq, gain, q, on), 8 High Cut(freq, slope, q, on).

| action | 파라미터 | 절차 | 검증 |
|---|---|---|---|
| `get` | strip/number | `focus` → `eq_mixer`(E1)에서 해당 스트립 2행이 공백이면 `has_eq=false` 반환(삽입 없음) → 있으면 `eq_channel` 4페이지 순회 | 8밴드 × 4열 텍스트, 페이지 전환 확인 |
| `set` | strip/number, band 1-8, param, value, `allow_insert`(기본 true) | `focus` → E1로 유무 확인 → 없고 allow_insert면 채널 뷰 진입(삽입됨, note) → `page_to(ceil(band/2))` → 열 = (band 홀수? 0 : 4) + {freq 0, gain/slope 1, q 2, on 3} → §5 설정 루프 | 오버레이 값, 정착 열 값 |

`value`: freq Hz(20-20000), gain dB(-24..+24), slope 6/12/18/24/36/48, q 수치, on bool. 열거형 파라미터의 `value`는 표시 텍스트(예: `"Post Pan"`, `"On"`)로 받는다(모든 도구 공통). 결과 `after`에 `{"band":3,"freq":1040,"gain":0.0,"q":0.41,"on":true,"text":{...}}`.

### 4.2 `logic_plugin`

> **정정(2026-10-15 실기 1차, `docs/mcu-protocol.md` 스펙 2a 실측 A~O)**: 이 절과 위 `slot_to` 행의 "P<n> 믹서 뷰에서 Cursor ▲▼로 슬롯 이동"은 틀렸다(믹서 뷰 커서는 무반응). 슬롯 접근은 **Plug-in Channel 뷰(`PL`)** 에서 하며 V-Pot n이 선택 트랙의 슬롯 n이다. 그래서 2a는 **슬롯 1~8만** 지원한다(9~15 경로 미확인). 미리 선택 위치는 **ceil 모델**(표시 항목 = `(틱 위치+1)//2`, 차 있는 슬롯에서 -1 틱 = 현재 항목, +1 틱 = 다음 항목)이라 "+1 틱으로 현재 이름 드러내기"는 교체 위험이 있어 쓰지 않는다. 편집 뷰는 틱 없이 V-Pot을 눌러 열고(값 보존), 이름은 NAME 헤더 1페이지, 페이지 수는 2페이지 헤더에서 읽는다. 확정 누름 뒤 편집 뷰는 ≈2초 뒤에 뜬다. `plugin_channel` 판정은 2자리 코드 `PL`만 본다(`Ins1Pl` 1행 검사 폐기).

인서트 슬롯 1-8(`slot`, 위 정정 참고). 파라미터는 `param`에 이름(부분 일치) 또는 정수 인덱스(1부터, `params`가 돌려준 순서).

| action | 파라미터 | 절차 | 검증 |
|---|---|---|---|
| `list` | 없음(현재 뱅크) 또는 strip/number | `plugin_mixer` P1→P15를 Cursor ▼로 순회하며 8스트립 2행 읽기(뱅크 전체 15단계). 2행이 `--`이거나 공백(슬롯 없음)인지 구분해 기록. 단일 트랙이면 `plugin_channel`(Ins1~8)로 교차 확인 | 2자리 `P<n>` 전환 |
| `params` | strip/number, slot | `focus` → P<slot> → V-Pot 누름(편집 뷰) → NAME 모드 헤더에서 플러그인 전체 이름·페이지 수 → VALUE 모드로 페이지 순회해 (축약명, 값) 수집 → 번들 표가 있으면 전체 이름 병합 | 헤더 `Page n/N` |
| `get` | strip/number, slot, param | `params` 경로로 해당 페이지만 | 열 값 |
| `set` | strip/number, slot, param, value, `tolerance` | 편집 뷰 → 페이지 이동 → §5 설정 루프 | 오버레이 값 |
| `insert` | strip/number, slot, plugin, `replace`(기본 false) | 목록(§6)에서 인덱스 → P<slot>에서 현재 항목 인덱스와의 차이를 틱으로(크기 N = N/2 항목, 63씩 분할) → 오버레이 이름이 목표와 일치 → `confirm` → 편집 뷰 진입 헤더로 확인 → `leave`. 슬롯이 차 있고 replace=false면 skipped | 헤더 플러그인 이름 |
| `remove` | strip/number, slot | P<slot> → CCW 틱(-63 반복, 오버레이 `--`까지) → `confirm` → `empty_edit`/`--` 확인 → `leave` | 2행 `--` |
| `bypass` | strip/number, slot, on | P<slot>에서 SHIFT 누른 채 V-Pot 누름 → 2행 `*` 접두사 | `*`(실기 미확인, 라이브 체크에 포함) |
| `scan` | `force` | §6.2 | 항목 수, 순환 감지 |

### 4.3 `logic_send`

센드 1-8(`send`). 모든 조작은 **SE 채널 뷰**에서 한다(2센드/페이지, Cursor ◀▶ 페이지 전환 실측). 열 = (send 홀수? 0 : 4) + {dest 0, level 1, pos 2, mute 3}. 레벨 절대 설정은 SE 뷰에서 FLIP을 켜고 level 열 페이더로 한다(EQ 채널 뷰·편집 뷰에서 Flip 동작 실측, SE 뷰는 라이브 체크 1순위; 안 되면 센드 1은 D1 뷰 페이더, 2~8은 틱 루프).

| action | 파라미터 | 절차 | 검증 |
|---|---|---|---|
| `get` | strip/number | `focus` → `send_channel` 4페이지 순회 | 열 텍스트(`--`는 없음, `* 1`은 뮤트) |
| `set_dest` | strip/number, send, dest(`"Bus 3"`, `"3"`, `"--"`) | SE 뷰 dest 열 V-Pot: 목적지 목록(§6.3) 인덱스 차이만큼 틱 → 오버레이 확인 → `confirm`(미리 선택+확정은 S1 뷰에서 실측, SE 뷰 dest 열도 같은지 라이브 체크) | 2행 값 고정 |
| `set_level` | strip/number, send, db | SE 뷰 → FLIP → level 열 페이더(센드 dB 표) → 오버레이 `-6.0 dB` | 오버레이·에코 |
| `set_pos` | strip/number, send, pos(pre/post/post_pan) | SE 뷰 pos 열 틱 1씩, 텍스트 일치까지(≤3) | `Pre`/`Post`/`Post Pan` |
| `mute` | strip/number, send, on | SE 뷰 mute 열 틱 | `muted`/`active` |
| `remove` | strip/number, send | `set_dest "--"` | 2행 `--` |

### 4.4 리소스

- `logic://plugins` — 병합된 플러그인 목록: `{"logic_version", "bundled_count", "scanned_at", "items":[{"index","name","source":"bundled|scan"}]}`.
- `logic://inserts` — 마지막 `list` 결과: `{"<number>": {"1":"Channel EQ", "2": null, ...}}`.
- `logic://view` — 현재 `View`(디버깅용).
- 스펙 1 `logic://status`에 `view_kind`를 추가한다.

## 5. 값 읽기와 설정 (`logic/values.py`)

### 5.1 파싱
열 텍스트(7칸)와 오버레이 값(전체)을 한 파서로 처리한다. 반환 `Value(number: float|None, unit: str|None, text: str, kind: "number"|"enum"|"none")`.
- 숫자+단위: `20.0Hz`, `21.6 Hz`, `1040Hz`, `20000`, `-78.4 d`(잘림), `-78.4 dB`, `+0.0 dB`, `0.0 dB`, `0.71`, `12`, `36 dB/Oct`, `10.0`, `1100`, `-0.5`. 단위는 `Hz|kHz|dB|dB/Oct|ms|s|%|st|ct` + 없음. `-oo dB`/`-oodB`는 -inf.
- 열거: `On/Off`, `Pre/Post/Post Pan`, `active/muted`, `--`, 그 밖의 비숫자 텍스트.
- 스펙 1 `parse_db_text`는 그대로 두고 이 파서가 감싼다.

### 5.2 매핑 유형 (Flip 페이더 ↔ 값)
| 유형 | 식 | 실측 |
|---|---|---|
| `db_table` | 스펙 1 `fader_db.json` | 센드 레벨 12443 → +0.0 dB, 0 → -oo |
| `log` | raw = 16383·ln(v/min)/ln(max/min) | Channel EQ freq 20-20000: 8192 → 625 Hz |
| `linear` | raw = 16383·(v-min)/(max-min) | 게인 -24..+24: 0 dB → 8191 |
| `enum` | raw = 16383·i/(n-1) | 슬로프 6단계: 12 → 3276, 24 → 9829(에코), On → 16383, Off → 0 |
| `unknown` | 프로빙으로 결정 | Q는 밴드마다 범위가 달라(0.71 → 4644, 1.00 → 12602) 프로빙 필요 |

프로빙: 페이더를 1과 16383으로 보내 오버레이 최소·최대를 읽는다(2회). 단위가 Hz면 log, 둘 다 숫자면 linear, 비숫자면 enum(틱 1씩 이동해 항목 수를 센다, 상한 16). 결과는 `(플러그인 이름, 파라미터 전체 이름)` 키로 사용자 캐시에 저장한다. **raw 0은 보내지 않는다**(Logic이 무시한 사례).

### 5.3 설정 루프
```
1. cur = 열 읽기(파싱 실패면 V-Pot +1/-1 nudge로 오버레이 유도 후 복원)
2. 매핑이 있으면 Flip on → fader(raw(target)) → 오버레이 값 읽기 (Flip은 명령이 끝나는 leave()에서 해제; Duplicate 모드에서 V-Pot 틱은 그대로 동작)
   매핑이 없으면 2를 건너뜀
3. 반복 ≤6: err = target - cur; 틱 = round(err / 틱당변화) (초기 틱당변화는 ±1 틱으로 측정, 크기 ≤63)
   보내고 오버레이 값 읽기
4. |err| ≤ tolerance → verified. 6회 초과 → unverified + 마지막 값 + note
```
tolerance 기본: dB 0.1, Hz 1 %, 무단위 1 %, 열거 텍스트 일치. 틱당변화는 파라미터마다 다르다(freq 20.0 → 21.6 Hz ≈ 8 %, 슬로프 1단계, 센드 레벨 -oo → -78.4 dB). 열거형은 2단계만 쓴다(틱 1씩, 텍스트 일치).

## 6. 플러그인 목록 (`logic/plugins/`)

### 6.1 번들 `known.json`
```json
{"logic_version": "12.0.1", "generated": "2026-10-15",
 "list": [{"index": 0, "name": "--"}, {"index": 1, "name": "Parametric EQ"}, ...],
 "params": {"Channel EQ": {"pages": 6, "items": [{"index": 1, "short": "LoCutS", "name": "Low Cut Slope", "map": {"type": "enum", "values": [6,12,18,24,36,48]}}, ...]},
            "Compressor": {...}}}
```
`scripts/scan_plugins.py`(전 범위 스캔)와 `scripts/calibrate_plugin.py <이름>`(삽입 → 페이지 순회 → 파라미터마다 프로빙 → 제거)로 생성한다. 1차 수록 플러그인: Channel EQ, Compressor, Limiter, Noise Gate, Tape Delay, Stereo Delay, Space Designer, ChromaVerb, Overdrive, Distortion. 목록 이름은 `(s/s)` 같은 채널 구성 접미를 떼고 저장하고, 21자 잘림은 접두 일치로 다룬다.

### 6.2 스캔 `logic_plugin scan`
1. 인벤토리에서 빈 슬롯이 있는 보이는 스트립을 고른다(없으면 skipped, note "빈 슬롯 필요").
2. P<slot> Mixer view에서 그 스트립 V-Pot을 **-63씩** 보내 오버레이가 `--`가 될 때까지 되감는다(시작점 고정).
3. +2씩 보내고 LCD 변화를 ≤0.3 s 기다려 21자 이름을 기록한다. 변화가 3회 연속 없거나 첫 이름(`--` 다음 항목)이 다시 나오면 끝.
4. PAN으로 나간다(미리 선택 취소, 삽입 없음). 끝난 뒤 그 슬롯이 `--`인지 확인한다.
5. `~/.logic-mcp/plugins-<Logic 버전>.json`에 저장. Logic 버전은 `/Applications/Logic Pro.app/Contents/Info.plist`의 `CFBundleShortVersionString`.
예상 시간 항목당 ~0.15 s(150메시지 ≈ 9 s 실측). 캐시가 있고 `force=false`면 skipped("already").

### 6.3 센드 목적지 목록
SE 뷰 센드 1 dest 열(또는 S1 뷰)에서 같은 방식으로 1회 스캔한다(`--`, 버스 1~N, 출력…). 텍스트는 7칸(` 1`, `--`)이라 오버레이 전체 이름으로 기록한다. 캐시 키 `send_destinations`.

### 6.4 이름 매칭 (`match.py`)
정규화(소문자, 공백·하이픈 제거, 채널 구성 접미 제거) 후 정확 일치 → 접두 일치 → 부분 일치. 후보 2개 이상이면 skipped와 후보 목록. 번들과 사용자 캐시가 같은 이름을 가지면 사용자 캐시 인덱스를 쓴다(설치 플러그인에 따라 순서가 달라질 수 있음).

### 6.5 스킬 `skills/logic-plugins/SKILL.md`
레포에 두고 README에서 `~/.claude/skills/logic-plugins/`로 복사하게 안내한다. 내용: (1) 연결 뒤 `logic://plugins`를 읽어 `scanned_at`이 없거나 Logic 버전이 다르면 `logic_plugin scan`을 권한다(30~60초, 화면에서 슬롯이 깜박임, 삽입 없음). (2) `insert`가 "목록에 없음"이면 scan 후 재시도. (3) 서드파티 파라미터가 `Control #N`(0~1000)으로만 나올 때는 인덱스로 다루고 값은 0~1000 정수. (4) `params` 결과를 먼저 읽고 이름을 고를 것.

## 7. 검증 규칙, 부작용, 안전

- 모든 전환은 2자리 표시·LED로 확인하고, 실패하면 `leave()` 뒤 unverified/timeout을 돌려준다. 명령 하나의 상한은 8 s(scan 제외 90 s).
- **선택 변경**: `focus`가 SELECT를 누른다. 명령 전 SELECT LED가 켜진 스트립을 기억해 같은 뱅크면 끝나고 되돌린다(다른 뱅크면 note).
- **Channel EQ 자동 삽입**: EQ 채널 뷰 진입 시 선택 트랙에 삽입된다. `get`은 삽입하지 않고, `set`은 `allow_insert`에 따른다.
- **플러그인 창**: 편집 뷰 진입 시 Logic이 창을 열고 나올 때 닫는다. 포커스는 가져가지 않는다.
- **교체**: 차 있는 슬롯 `insert`는 `replace=true` 없이는 skipped.
- **Flip 잔류 방지**: `leave()`가 FLIP LED를 확인해 끈다. `logic_session status`가 `flip`을 보고하고, 스펙 1 `set_pan`은 flip이 켜져 있으면 먼저 끈다.
- **스캔 중 입력 금지**: 스캔은 락을 잡고 돌며, 중단되면 PAN으로 나가 미리 선택을 취소한다.
- 스펙 1 규칙 유지: 프로젝트 저장 안 함, MPK mini IV 설정 불변, 기본값 재형성 금지, UI 클릭 없음, 0x14에만 응답.

## 8. 테스트, 데이터, 설치

- 픽스처: `tests/fixtures/assign_*.log`로 스파이크 원시 로그를 옮겨 2자리 코드 → 뷰 판정, 뷰별 열 파싱, 오버레이 2.0 s, 깜박임 감지, `Page n/N` 헤더, 플러그인 목록 스텝(N/2)을 고정한다.
- 가짜 Logic(`tests/fakes.py` 확장): 뷰 전환, 홀드 메뉴, 미리 선택·확정·취소, Flip 페이더 매핑(log/linear/enum), 틱당 변화, 오버레이 타이머를 흉내 낸다.
- 단위 테스트 대상: `values.py`(파서·매핑·루프), `modes.py`(전환표·복귀 보장), `plugins/`(스캔 종료 조건, 매칭, 병합), 각 Commands 액션, 서버 스키마.
- 실기: `scripts/live_check2.py` — (1) `logic_eq set` 밴드 3 freq 1000·gain -3 → 오차 안 verified, (2) `logic_plugin insert Compressor` → `params` → `set Threshold -20 dB` → `remove`, (3) `logic_send set_dest Bus 1` → `set_level -6` → `remove`, (4) `scan` 결과에 Channel EQ 포함, (5) 끝난 뒤 `logic://status`가 PAN·flip off. 센드 dB 표는 `scripts/calibrate_send.py`로 볼륨 표와 비교해 다르면 별도 표.
- 비범위이지만 기록: 스펙 1 `docs/mcu-protocol.md`에 부록 A를 합친다.

## 9. 비범위와 알려진 제약

- 악기 슬롯(INSTRUMENT 0x2D), MIDI FX 슬롯(`M<n>`) 편집, 서라운드, EQ Frequency/Gain 뷰(`F1`~`F8`, `FG`), User 모드 1~6.
- 플러그인 이름은 LCD 21자 안에서만 안다. 같은 접두 21자를 가진 플러그인은 구분하지 못한다(skipped + 후보).
- 서드파티 플러그인이 이름·값 텍스트를 주지 않으면 `Control #N`, 0~1000만 가능하다.
- 센드 레벨 외 파라미터의 "정확한 값"은 Logic 표시 해상도(7칸, 소수 1~2자리)까지다.
- Logic 12.0.1에서 실측했다. 다른 버전의 2자리 코드·레이아웃은 재확인 대상이다.

## 부록 A. 프로토콜 실측 요약 (스펙 2 추가분)

- 노트(Note On ch1): Cursor ▲ 0x60, ▼ 0x61, ◀ 0x62, ▶ 0x63, ZOOM 0x64(꺼져 있어야 함), V-Pot 누름 0x20-0x27, F1-F8 0x36-0x3D, SHIFT 0x46, FLIP 0x32, TRACK 0x28, SEND 0x29, PAN 0x2A, PLUGIN 0x2B, EQ 0x2C, INSTRUMENT 0x2D.
- 2자리 표시(CC 0x4A/0x4B): `PN` 팬, `E1` EQ Mixer, `EQ` EQ Channel, `E_` EQ 메뉴, `S<n>` Send Mixer, `SE` Send Channel, `S_` Send 메뉴, `D<n>` Send Dest/Level Mixer, `P<n>`/`10`-`16` Plug-in Mixer·Edit, `PL` Plug-in Channel, `M<n>` MIDI FX.
- 오버레이 2.0 s. 미리 선택 깜박임: 오버레이 뒤 반주기 ≈0.75 s, 타임아웃 없음(≥7 s), 모드 전환으로 취소.
- V-Pot CC(0x10+ch): 크기 1-63, 플러그인 목록은 크기 N = N/2 항목, 파라미터는 종류별 상이.
- Flip: 페이더 → 파라미터 절대값(log/linear/enum). raw 0 무시 사례. 에코는 값이 바뀔 때만.
- EQ Channel view 열(밴드 1·2): `LoCutF LoCutS LoCutQ LCO/Of LoShF LoShGa LoShQ LSO/Of`; 밴드 3·4: `Peak1F Pea1Ga Peak1Q Pe1On/ Peak2F …`; 밴드 5·6: Peak3/4; 밴드 7·8: High Shelf/High Cut(추정, 라이브 체크에서 확인).
- Plug-in Edit NAME 모드 헤더 예: `Track 15 "15:Deluxe Classic" Ins.1 "Channel EQ (s/s)"` + `Page 1/6`. Channel EQ 1페이지: `LoCutS LoShGa Pea1Ga Pea2Ga Pea3Ga Pea4Ga HiShGa HiCutS`, 2페이지: 주파수 8개.
- Send Channel view 열(센드 있을 때): `Sen1In|<목적지>|Sen1Po|Sen1Mu` / ` 1|-oodB|Post|active`, 뮤트 시 `* 1`. 센드 없을 때 `Sen1In - - -` / `--`.
- Plug-in Mixer view: 2행 플러그인 축약 6자(`Cha EQ`, `Distrt`), 비면 `--`. 미리 선택 오버레이 `Insert <n> Plug-in` / 전체 이름.
- 플러그인 목록 순서(Logic 내부, 일부): Parametric EQ, Low Pass Filter, High Pass Filter, Low Shelving EQ, High Shelving EQ, Chorus, Flanger, Tape Delay, Echo, Stereo Delay, … Channel EQ, Tuner, Linear Phase EQ, Guitar Amp Pro, Match EQ, Delay Designer, … (전체는 scan으로).
