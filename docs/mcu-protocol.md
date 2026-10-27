# MCU 프로토콜 실측 (Logic Pro 12.0.1, macOS 26.5, 2026-10-13~14)

## 프로토콜 요약

디바이스 ID 0x14. sysex 헤더 `F0 00 00 66 14`.

- 핸드셰이크: 쿼리 `00` → 응답 `01` + 시리얼 7바이트 + 챌린지 4바이트. 버전 요청 `13` → 응답 `14` + `V1.00`.
- LCD 쓰기 `12 <offset 0-111> <text>`, 2행은 56. 페이더 터치 감도 `0E <ch> <0-5>`. `72 ...`는 미해독(픽스처만).
- 버튼/LED: Note On ch1, 0x7F on / 0x00 off. REC 00-07, SOLO 08-0F, MUTE 10-17, SELECT 18-1F, V-Pot push 20-27, TRACK 28 SEND 29 PAN 2A PLUGIN 2B EQ 2C INST 2D, BANK◀ 2E BANK▶ 2F CH◀ 30 CH▶ 31(2026-10-15 트랙 22채널 프로젝트에서 실기 확인: BANK 2E/2F는 8칸 페이지 단위로 움직이고 끝에서 클램프, CH 30/31은 1칸), FLIP 32, NAME/VALUE 34, SMPTE/BEATS 35, SHIFT 46 OPTION 47 CTRL 48 ALT 49, CYCLE 56, REW 5B FFWD 5C STOP 5D PLAY 5E REC 5F, 페이더 터치 68-6F, LED SMPTE 71 BEATS 72 RUDE SOLO 73.
- 페이더: Pitch Bend ch1-8, 14비트. Logic 범위 0-14845(+6.0 dB), 0 dB = 12443, 에코는 양자화.
- V-Pot 회전 CC 10-17: 01-3F 시계, 41-7F 반시계, 하위 비트가 크기. 링 CC 30-37: bit6 중앙점, bit4-5 모드, 하위 4비트 위치.
- 타임 디스플레이 CC 40-49(자리별), 값 bit6=점. 할당 표시 CC 4A-4B. 미터 Channel Pressure `(ch<<4)|level`.
- 교차검증: REAPER `csurf_mcu.cpp`(LGPL), Apple 컨트롤 서피스 지원 가이드. 코드 복사 없음.

## 타이밍
- 버튼 누름 → LED 피드백 15~50ms. LCD "Muted" 텍스트는 LED보다 먼저 온다.
- 페이더 전송 → 에코 ~130ms. 에코값은 양자화된다(10000 → 9990).
- 설치(핸드셰이크) → 환영 애니메이션 약 50초(LCD 점 이동, 링 스윕) → 조용해지면 사용 가능.

## 동작
- 포트당 기기 1대. Extender가 포트를 점유하면 본체가 설치되지 않는다.
- OPTION+NAME/VALUE: LCD 1행 `번호:이름` 토글. NAME/VALUE: 2행 이름/값 토글.
- OPTION 누름 자체가 SEL2/SEL3/READ_OFF/UNDO LED를 깜빡인다(무해).
- 비ASCII 트랙명은 LCD에서 사라진다("오디오 1" → "1").
- 페이더 최대 14845(+6.0 dB), 0 dB = 12443, 0 = -oo dB.
- V-Pot 한 메시지의 크기 비트가 그대로 스텝 수(+5 → 팬 +5).

## 스펙 2 추가 실측(어사인먼트 모드)

- 노트(Note On ch1): Cursor ▲ 0x60, ▼ 0x61, ◀ 0x62, ▶ 0x63, ZOOM 0x64(꺼져 있어야 함), V-Pot 누름 0x20-0x27, F1-F8 0x36-0x3D, SHIFT 0x46, FLIP 0x32, TRACK 0x28, SEND 0x29, PAN 0x2A, PLUGIN 0x2B, EQ 0x2C, INSTRUMENT 0x2D.
- 2자리 표시(CC 0x4A/0x4B): `PN` 팬, `E1` EQ Mixer, `EQ` EQ Channel, `E_` EQ 메뉴, `S<n>` Send Mixer, `SE` Send Channel, `S_` Send 메뉴, `D<n>` Send Dest/Level Mixer, `P<n>`/`10`-`16` Plug-in Mixer·Edit, `PL` Plug-in Channel, `M<n>` MIDI FX.
- 오버레이 2.0 s. 미리 선택 깜박임: 오버레이 뒤 반주기 ≈0.75 s, 타임아웃 없음(≥7 s), 모드 전환으로 취소.
- V-Pot CC(0x10+ch): 크기 1-63, 플러그인 목록은 1항목 = 2틱(위치 모델은 아래 E의 ceil), 파라미터는 종류별 상이.
- Flip: 페이더 → 파라미터 절대값(log/linear/enum). raw 0 무시 사례. 에코는 값이 바뀔 때만.
- EQ Channel view 열(밴드 1·2): `LoCutF LoCutS LoCutQ LCO/Of LoShF LoShGa LoShQ LSO/Of`; 밴드 3·4: `Peak1F Pea1Ga Peak1Q Pe1On/ Peak2F …`; 밴드 5·6: Peak3/4; 밴드 7·8: High Shelf/High Cut(추정, 라이브 체크에서 확인).
- Plug-in Edit NAME 모드 헤더 예: `Track 15 "15:Deluxe Classic" Ins.1 "Channel EQ (s/s)"` + `Page 1/6`. Channel EQ 1페이지: `LoCutS LoShGa Pea1Ga Pea2Ga Pea3Ga Pea4Ga HiShGa HiCutS`, 2페이지: 주파수 8개.
- Send Channel view 열(센드 있을 때): `Sen1In|<목적지>|Sen1Po|Sen1Mu` / ` 1|-oodB|Post|active`, 뮤트 시 `* 1`. 센드 없을 때 `Sen1In - - -` / `--`.
- Plug-in Mixer view: 2행 플러그인 축약 6자(`Cha EQ`, `Distrt`), 비면 `--`. 미리 선택 오버레이 `Insert <n> Plug-in` / 전체 이름.
- 플러그인 목록 순서(Logic 내부, 일부): Parametric EQ, Low Pass Filter, High Pass Filter, Low Shelving EQ, High Shelving EQ, Chorus, Flanger, Tape Delay, Echo, Stereo Delay, … Channel EQ, Tuner, Linear Phase EQ, Guitar Amp Pro, Match EQ, Delay Designer, … (전체는 scan으로).

## 스펙 2a 실기 1차 실측(2026-10-15, Logic 12.0.1, 트랙 15 "Deluxe Classic")

계획의 "P<n> 믹서 뷰에서 Cursor ▲▼로 슬롯 이동"과 "+1 틱으로 현재 이름 드러내기"는 틀렸다. 아래가 실측이다.

- A. EQ 버튼: down 즉시 2자리 `E_`(eq_menu), up 뒤 50 ms 안에 `E1`(eq_mixer). 모드 전환 대기는 `_menu`·과도기를 지나쳐야 한다. PLUG-IN은 메뉴 없이 즉시 `P1`.
- B. Plug-in Mixer 뷰(`P1`)에서 Cursor ▲▼◀▶는 무반응(hold 0.03·0.2 s, M1 전환도 없음). 믹서 뷰로 슬롯을 바꾸는 경로는 없다.
- C. 슬롯 접근은 Plug-in Channel 뷰(`PL`, PLUGIN 두 번째 누름). 1행 `Ins1Pl … Ins8Pl`, 2행 = 선택 트랙 슬롯 1~8(빈 슬롯 `--`, 차 있으면 6자 축약: `ParEQ ` = Parametric EQ, `Cha EQ` = Channel EQ, `Comprs` = Compressor). PL에서 ◀▶도 무반응 → 슬롯 9~15 경로 미확인, **2a는 슬롯 1~8만 지원**.
- D. PL에서 V-Pot n 돌리기 = 슬롯 n 미리 선택. 오버레이 1행 `Insert n Plug-in`, 2행 전체 이름(`Parametric EQ (s/s)`), 폭 21칸, 시작 열 `min(n-1, 5)*7`(슬롯 6~8은 모두 열 35~55, 7·8은 오른쪽 정렬 + 끝 공백 1). 0.3 s 뒤 읽힘, 2.0 s 뒤 열 재묘사.
- E. 미리 선택 위치 = ceil 모델: 틱 누적 pos(0 = `--`), 표시 항목 = `(pos + 1) // 2`. 차 있는 슬롯(항목 i)의 시작 pos = 2i → **-1 틱 = 현재 항목**, **+1 틱 = 다음 항목**(누르면 교체됨). 빈 슬롯은 0에서 포화(`--`).
- F. V-Pot 누름: 미리 선택 뒤 → 삽입 후 편집 뷰(`P<slot>`). 미리 선택 없이 차 있는 슬롯 → 값이 보존된 편집 뷰(0.5 s 안). 미리 선택 없이 빈 슬롯 → 무반응.
- G. 편집 뷰 NAME 모드 헤더 `Track 15 "15:Deluxe Classic" Ins.1 "Parametric EQ (s/s) ` — 56자에서 잘려 닫는 따옴표·`Page n/N`이 없을 수 있다. 이름은 `Ins\.(\d+) "([^"]*)`로 뽑고 `(s/s)` 접미는 뗀다.
- H. 편집 뷰에서 PLUGIN → Plug-in Mixer 뷰(PL 아님). Mixer 2행의 빈 슬롯은 `--` 또는 공백(갱신 전).
- I. 제거: PL에서 V-Pot n에 -63 틱 반복(-126이면 충분) → 오버레이 `--` → 누름 → `empty_edit`(1행 전부 `-`, `P<slot>`) → PL 2행 해당 슬롯 `--`.
- J. 2자리 `PL`은 오버레이가 떠도 그대로 → `plugin_channel`은 코드 `PL`만으로 판정(슬롯 1 오버레이가 1행 `Ins1Pl`을 덮는다).
- K. 확정 누름(미리 선택 뒤) → +0.5 s에는 아직 `PL`+오버레이, **+2.0 s에 편집 뷰**(`plugin_edit`, 제거면 `empty_edit`). 대기는 오버레이 시간+여유(≈3 s).
- L. NAME 헤더의 Page: 1페이지 `… Ins.2 "Compressor (s/s)" P `(`Page 1/3`이 잘림), 2페이지 `… Ins.2 "Compre     Page 2/3 `(이름이 잘리고 Page 표시). 이름은 1페이지에서, 페이지 수는 2페이지 헤더에서 읽고, Cursor ▶에 반응이 없으면 1페이지. 트랙 이름이 짧으면 1페이지에도 `Page 1/N`이 보인다.
- M. Compressor: VALUE 1행 `CirTyp Thrs   Ratio  Attack Rel    AutRel MakeUp AutGai `, 2행 `PltDig -20.0  2.1:1  15.0ms 51.0ms On     0.0 dB -12dB  `, 2페이지 `Knee   Peak/S LimrOn LimThr Distrt Mix    SiChDe State  `, 3페이지까지. 되감기 뒤 +2·15 틱 → `Compressor (s/s)`(known.json 인덱스 15, ceil 모델 확인).
- N. 바이패스: PL에서 SHIFT down → V-Pot(slot-1) 누름 → SHIFT up → 2행 `Comprs` ↔ `*Compr`(별표 + 5자) 즉시 토글, 뷰 변화 없음.
- O. 편집 뷰에서 PLUGIN → 편집 중이던 슬롯의 `P<slot>` Mixer 뷰.


## 스펙 2a 실기 2차 실측(2026-10-15)
- P. EQ 채널 뷰 첫 진입(Channel EQ 자동 삽입): E1에서 EQ 누름 → `E_`(eq_menu)가 0.5~1.0초 지속 → +1.0초에 `EQ`(eq_channel). EQ가 이미 있으면 빠르다. 모드 버튼 단계 대기는 3.0초(`ENTER_TIMEOUT`).
- Q. EQ 채널 뷰는 마지막 페이지를 기억한다(진입 직후 직전 명령이 끝난 페이지로 열림). 1행 첫 열로 페이지 판정: `LoCutF`=1, `Peak1F`=2, `Peak3F`=3, `HiShF`=4. 마지막 페이지에서 Cursor ▶는 무반응, Cursor ◀는 이전 페이지. 밴드 7·8: `HiShF HiShGa HiShQ HSO/Of` / `HiCutF …`.
- R. 슬로프 열: 정착 열 `12`(단위 없음), 틱 직후 `18 dB/O`(단위 포함, 7자에서 잘림). 단위가 `dB/O`처럼 표에 없어도 앞 토큰이 숫자이면 number로 읽는다.
- S. 삽입 오버레이 조기 읽기: 되감기(-63×2)의 `--` 오버레이 쓰기가 늦게 도착해 다음 틱의 변화 대기를 즉시 만족시키고, 목표 틱의 오버레이가 오기 전에 `--`를 읽었다. 되감기 뒤 0.3초, 목표 틱 뒤 0.4초 조용해진 다음 읽으면 `Compressor (s/s)`가 정확했다. 틱은 마지막 LCD 쓰기 뒤 0.4초(`TICK_QUIET_S`) 조용해질 때까지 기다린다.


## 스펙 2a 실기 3차 실측(2026-10-15, Channel EQ 밴드 4 = Peak 2 Q, 트랙 15)
- T. Flip 페이더 raw → Q: 1→0.10, 1024→0.15, 2048→0.24, 4096→0.57, 6144→1.40, 8192→3.20, 10240→7.30, 12288→18.0, 14336→42.0, 15360→65.0, 16383→100. `ln Q`가 raw에 선형 → **log 매핑 lo=0.10, hi=100**(예측 8192→3.16, 12288→17.8, 2048→0.237이 표시와 일치). 표시는 유효숫자 3자리(`0.57`, `1.40`, `18.0`, `100`).
- U. V-Pot 틱: +1 ×8 → 0.30→0.31→0.33→0.35→0.37→0.39→0.41→0.43→0.46(틱당 ×≈1.06), -3 ×4 → 0.46→0.39→0.33→0.28→0.24. 틱도 **로그 영역에서 등간격**(틱당 ln 변화 ≈ 0.058). 선형으로 추정하면 큰 값에서 과소·작은 값에서 과대 보정되어 수렴하지 못한다.
- V. 밴드 1·8(Low/High Cut)의 Q는 미측정(기본 0.71). **가정**: 같은 범위(log 0.10~100)로 보고 같은 매핑을 쓴다.
- W. **편집 뷰 마지막 페이지는 오른쪽 정렬**(Logic Pro 12.0.1, 실기 3·4차). 파라미터 N개, 페이지 P=ceil(N/8)이면 마지막 페이지는 N-7..N을 보인다(빈 열로 채우지 않음). Compressor N=20, P=3, 축약명(페이지 1·2·3): `CirTyp Thrs Ratio Attack Rel AutRel MakeUp AutGai` / `Knee Peak/S LimrOn LimThr Distrt Mix SiChDe State` / `Distrt Mix SiChDe State Mode Freq Q Gain`. 값(VALUE, 기본): `PltDig -20.0 2.1:1 15.0ms 51.0ms On 0.0 dB -12dB` / `0.7 RMS Off 0.0 dB Off 100.0% Max Off` / `Off 100.0% Max Off LP 7040.0 1.00 0.0 dB`. 13~16과 17~20이 같은 항목이므로 페이지 기준 번호(page-1)*8+열+1을 그대로 쓰면 중복이 생긴다 → 마지막 페이지에서 직전 페이지와 위치 정렬로 겹치는 앞 k열을 버린다(결과 index 1..16, 21..24).
- X. **페이더 이동 뒤 LCD 값 쓰기가 페이더 에코보다 늦게 올 수 있다**(실기 4차). 에코나 LCD 변화 중 먼저 오는 쪽에서 대기를 끝내면 `probe_mapping`이 이동 전 값(-20.0)을 읽는다(Compressor `Thrs` 매핑이 linear -20..0으로 잘못 학습, 실제 -60..0 dB). 에코를 기다린 뒤 LCD 변화도 추가로 기다려야 한다(값이 안 바뀌면 LCD가 안 올 수 있으므로 둘째 대기는 실패해도 무방).
- Z1. **페이더 이동이 가끔 통째로 무시된다**(실기 5차, Logic Pro 12.0.1). `eq set b4 q 2.0`(6082 ms)과 반복 프로브 1라운드 `q b4 2.0`(5835 ms)이 실패했고, 성공 시(4403~4712 ms)보다 정확히 ≈1.4 s(FADER_TIMEOUT 0.8 + FEEDBACK_TIMEOUT 0.6) 길다 = 한 번의 `fader_move`에 에코도 LCD 쓰기도 없었다. 이동 전 값(0.71)을 오차로 보고 시컨트 보정해 값이 13.0으로 튀었다. 설정 29회 중 2회, 모두 Flip을 켠 직후의 첫 페이더 이동. 대응: `fader()`는 에코·LCD가 둘 다 없으면 같은 이동을 한 번 더 보내고, `set_numeric`은 값이 이동 전과 같으면 시컨트 보정을 건너뛰고 틱으로 간다.
- Z2. **FLIP 누름이 가끔 무시된다**(실기 5차). `eq set b3 gain -3`에서 LED_TIMEOUT 0.5 s 안에 FLIP LED 변화 없음. Flip을 켠 약 20회 중 1회. 같은 명령이 다른 라운드·실행에서는 정상(4·6차 17/17). 대응: `flip()`은 LED가 안 바뀌면 FLIP을 한 번 더 누른다. 재누름은 안전 문제로 제거(리뷰 C1: 늦게 온 LED와 겹치면 Flip이 꺼진 채 페이더가 트랙 볼륨을 움직일 수 있음), LED 대기 1.0 s, `fader()`는 송신 직전마다 Flip을 확인한다.
- Z3. **PL(Plug-in Channel) 뷰 안에서 SELECT 로 트랙을 바꾸면 2행이 새 트랙의 슬롯으로 바뀌지 않는다**(실기 8차, 뱅크 전체 list). 선택 스트립 열(n, n+1)에 트랙 이름 조각(`Deluxe`/`Classic`/`Master`)이 읽혔고 드러내기는 `--`. LCD 가 정확히 무엇을 보여 주는지는 미실측. 대응: `_channel()` 은 이미 PL 이고 다른 스트립이면 PAN 으로 나가 다시 들어간다(단일 트랙 명령이 밟는 검증된 경로). 비용: 뱅크 list 트랙당 PAN 전환 1회(≈0.6 s).


## 실기 9차 실측(2026-10-16, Logic 12.0.1, 사용자가 새로 만든 테스트 프로젝트)
- Z3 정밀. PL 안에서 SELECT 로 트랙을 바꾸면 2행의 선택 스트립 열(n, n+1)에 **새 트랙 이름**(`Deluxe Classic`, `Stereo Out`)이 약 2초 떠 있고, 나머지 열은 `--`. 새 트랙의 슬롯은 그려지지 않는다. PAN 으로 나가 SELECT → PL 재진입(수정 7)은 실제 트랙에서 정확했다(빈 트랙 → `--`, Channel EQ 트랙 → `Cha EQ`).
- Z4. **PL(플러그인 채널 뷰)·SE(센드 채널 뷰)는 출력(Stereo Out)·Master 스트립을 따라가지 않는다.** SELECT LED 는 켜지지만 2행은 직전에 선택했던 *실제 트랙*의 슬롯/센드를 그대로 보여 준다(트랙 1 `Cha EQ Comprs` → Stereo Out, Master 재진입 모두 `Cha EQ Comprs`; PL→P1→PL 재그리기도 같음). 그래서 출력 스트립을 대상으로 `plugin insert`·`eq set`·센드 설정을 하면 **엉뚱한 트랙이 바뀐다.** 믹서 뷰(P<n>, E1)는 스트립별로 정확하다(Master 는 인서트 슬롯이 없어 P<n> 2행이 빈칸, Stereo Out 은 `--`). 뱅크 `plugin list` 9차에서 Stereo Out·Master 가 직전 트랙의 `Cha EQ` 로 읽힌 원인. → 수정 8 필요(계획 2b Task 1~2).
- Z5. **TRACK 버튼**: down 즉시 2자리 `C_` + 2행 홀드 메뉴 `Volume Pan TrkFmt Input Output Auto DisplP Setup`(V-Pot n 누름으로 선택), up 뒤 `CS`(Channel Strip 뷰: 1행 이름, 2행 스트립별 값, 오버레이 `Channel Strip parameter: …`). 항목별 2행: Volume `+0.0dB`(출력·Master 포함), Pan `0`(Master 빈칸), TrkFmt(Stereo Out 만 `Srnd`), Input(오디오 트랙 ` 1`), **Output: 트랙·Aux `St Out`, Stereo Out·Master 는 빈칸** → 출력·마스터 스트립 판별 신호(Z4 대응). Auto `Read`(Master 빈칸). Setup(7)은 선택 트랙의 `CFormt CInIns COuIns` 페이지. **주의: 항목 6(DisplP)을 고르면 뱅크에서 출력·Master 스트립이 사라졌고, GLOBAL VIEW(0x33) 를 켰다 끄니 원래대로 돌아왔다**(GLOBAL VIEW 켜짐 = 모든 채널 스트립: `1:1 2:Prve 2:DeCl 4:Clck 3:StOu 6:Mast`). 홀드 메뉴 선택은 그룹 설정 "채널 스트립 파라미터"를 바꾸므로 끝에 Volume(0)으로 되돌린다.
- Z6. **Logic 재시작 뒤 Mackie Control 장치 상태가 꼬이는 사건.** 어제 정상이던 장치가 오늘 Logic 재시작 뒤 EQ·PLUGIN·SEND·PAN·TRACK 에 메시지 0건(SELECT·FLIP·V-Pot·NAME/VALUE·BANK·CHANNEL 은 정상), INSTRUMENT 가 TRACK LED, GROUP(0x4F) 이 SEND LED, SELECT 가 토글, 2자리 `G1` 고착. 새 프로젝트에서도 같았고 설정 창에는 Mackie Control 1대뿐. **해결: 컨트롤 서피스 설정 창에서 Mackie Control 삭제 → 포트 재연결 → Logic 이 기본값으로 재설치**(직후 트랙 이름 포맷이 번호 없음이라 `configure` 필요, 9차 17/17). 원인 미상. 포트를 열 때마다 `com.apple.logic.pro.cs` 에 `LogicMCP` 문자열이 2개씩 늘어나는 것도 관찰(장치는 1대 유지).
- Z7. `eq set` 에서 EQ 채널 뷰가 4페이지(`HiShF`)로 열린 뒤 Cursor ◀ 2회에 LCD 반응이 없어 unverified 1회(오디오 트랙 첫 삽입 직후). 같은 세션의 다른 6회는 정상. 재현 안 됨, 관찰만 기록.

## 센드 실측(2026-10-16, 계획 2b 준비, `probe_send.py` 스트립 2 = 소프트웨어 악기 트랙)
- S1. SEND 버튼: down 즉시 `S_`(2행 홀드 메뉴 `Dest Level Pos Mute CStrip CStr2 Ds/LvM Ds/LvC`), up 뒤 `S1`(Send Mixer: 2행 스트립별 센드 1 목적지 `--`, 오버레이 `Send 1 Parameter: Send 1 Destination`). 두 번째 누름 → `SE`(Send Channel).
- S2. SE 1행(센드 없음): `Sen1In -      -      -      Sen2In -      -      -`, 2행 `--`(dest 열만). 센드 있음: `Sen1De|<dest 번호>|Sen1Po|Sen1Mu` / `Bus 2  -oodB  PosPan active`. 1행 라벨은 `Sen1In`/`Sen1De`, 레벨 열 헤더 `1`/`Aux 1` 등으로 흔들린다 → **열 위치로만 해석**(센드 홀수 = 열 0~3, 짝수 = 열 4~7; dest, level, pos, mute).
- S3. SE 페이지: Cursor ▶ 로 `Sen3In`, `Sen5In`, `Sen7In`, `Sen9In Sen10I`(센드 9·10 존재), ◀ 로 되돌아옴. **PAN 으로 나갔다 재진입하면 마지막 페이지를 기억한다**(EQ 의 Q 와 같음) → 1행 `Sen(\d+)` 로 페이지 판정.
- S4. 목적지 미리 선택(dest 열 V-Pot): **1틱 = 1항목**(플러그인의 ceil 모델 아님). `--` 에서 +1 `1`, +2 `2`, +3 `Bus 1`, +4 `Bus 2` … (앞의 `1`, `2` 가 무엇인지 미확인). 오버레이 1행 `Send 1 Destination`, 2행 전체 텍스트. 2초 뒤 열에 미리 선택이 0.8초 켜짐/0.8초 꺼짐으로 깜박인다(시간 제한 없음). -63 되감기 → `--`. PAN 으로 나가면 취소된다(재진입 `--`).
- S5. 확정 = dest 열 V-Pot 누름 → 오버레이 `Send 1 Instantiate` → 약 2초 뒤 `Bus 2  -oodB  PosPan active`(새 센드 기본값: -∞ dB, Post Pan, active). **버스 센드를 확정하면 Logic 이 Aux 트랙(`Aux 1`)을 자동 생성해 뱅크에 끼어들고 뒤 스트립 번호가 밀린다**(Master 6 → 7). 제거 = `--` 미리 선택 → 누름 → `Send 1 Instantiate` → 약 2초 뒤 `Sen1De - - -` / `--`(Aux 는 남음).
- S6. **SE 에서 FLIP 이 동작하고 레벨 열 페이더 = 센드 레벨 절대값, dB 표는 볼륨 표와 같다**: raw 1 → `-oo dB`, 4096 → 에코 4092 `-29.2 dB`, 8192 → 8178 `-9.0 dB`, 12443 → `+0.0 dB`, 14845 → `+6.0 dB`(상한, 16383 도 +6.0, 에코 없음). 페이더 뒤 오버레이 2행에 전체 값, 정착 열은 `-29.2  `·`-9.0dB `·`+6.0 dB` 처럼 단위가 잘리기도 한다(숫자는 그대로). `calibrate_send.py` 불필요.
- S7. 레벨 틱: +6.0 에서 +1 은 무변화(상한), -3 → +5.5, -10 → +4.5(틱당 ≈0.15 dB, 위쪽 기준). 오버레이 1행은 `1  Aux 1      Sen1Mu`(이름 아님).
- S8. Pos 틱: 순환 **Pre → Post → Post Pan**(+1 방향, 끝에서 멈춤). 오버레이 `Send 1 Position` / `Pre`·`Post`·`Post Pan`, 정착 열 `Pre`·`Post`·`PosPan`(오버레이 조각으로는 `Post Pa`).
- S9. Mute 틱: +1 → `muted`(dest 열이 `*Bus 2`), -1 → `active`. 오버레이 1행 `Send 1 Mute   -`.
- S10. SE 안에서 SELECT 로 Stereo Out 을 고르면 2행에 잠깐 조각(`Aux 1`)이 뜨고 3초 뒤 **여전히 트랙 2의 센드**(Z4 와 같음). 실제 트랙으로 돌아오면 이름(`Deluxe Classic`) 조각 뒤 그 트랙 센드. 센드 명령도 PAN → SELECT → SE 재진입 경로를 쓴다.
- S11. 센드 없는 열의 level/pos/mute V-Pot 은 무반응(스파이크와 같음).

## 실기 10차 실측(2026-10-19, Logic 12.0.1, 사용자 테스트 프로젝트, 스트립 1 = 트랙 1)
- `scripts/live_check2.py 1` 29/29 ok(verified 28, 기대된 skipped 1 = `eq set b8 on False` 기본값 Off). EQ get·set 7, 플러그인 list·insert·params·get·set·bypass·replace·remove 13, 센드 get·set_dest·set_level(-6, -inf)·set_pos·mute·remove 9. 끝 상태 PAN. 단일 실행이라 재현성은 미평가.
- 계획 2b가 실기 확인 항목으로 남긴 다섯 가지가 모두 1회 통과: PAN에서 TRACK 홀드 직접 진입, Output 열로 스트립 종류 판별, 목적지 확정 뒤 깜박임 정지(`set_dest` verified), 끝 값 틱 오버레이(`set_level -inf` verified), 확정 지연 `CONFIRM_S` 3.0(`set_dest` 전체 6.6 s).
- 첫 채널 뷰 명령은 스트립 종류 첫 판별(TRACK 홀드 + Output 열 읽기)을 포함해 길다: `eq get` 10.9 s, 마지막 뱅크 `plugin list` 8.2 s. 같은 뱅크의 두 번째부터는 캐시(0 ms). `plugin list`(뱅크 전체 8트랙) 32 s.
- **Z4 가드 실기.** 마지막 뱅크 스트립 `[(9,'DeCl'),(10,'1')…(14,'5'),(17,'Au1'),(15,'SOu')]`. **Stereo Out의 LCD 약칭은 `SOu`**(`St Out`이 아님). `plugin list #15`·`send get #15` → skipped(note "출력·Master 채널 스트립…지원하지 않음"), `eq get #15` → ok verified에 note "밴드 값은 읽지 않음"(has_eq만). 양성 대조 `send get #17`(Au1) verified. 가드 뒤 PAN 복귀·`bank first` 정상. Master 스트립은 이 뱅크에 보이지 않아 미확인.
- **S5 재확인.** `Bus 1` 센드 확정으로 생긴 Aux 1(`Au1`, 번호 17)은 마지막 트랙 `5`(14) 뒤·`SOu`(15) 앞에 놓였다. 대상 스트립 1은 밀리지 않았고, `send remove`는 Aux 트랙을 지우지 않는다(프로젝트에 남음). 리뷰 M6(선택 복원 인덱스 밀림)은 이 배치에서는 발현하지 않았다.
- Z6 없음: 10/16 이후 Logic을 다시 켰지만 할당 버튼이 모두 정상(장치 재설치 불필요).
- `live_check2.py`의 출력 스트립 감지가 `St`·`Mas`로 시작하는 이름만 봐서 `SOu`를 놓쳤다 → `SOu` 추가.
- **캘리브레이션 1차(16:44~17:12, `calibrate_plugin.py` 8종 수집)에서 드러난 사실 셋**(→ `fix/calibrate-quality`로 수정):
  - 편집 뷰 VALUE 모드(1행 축약명, 2행 값)에서 틱 이름 오버레이는 **1행 해당 열부터 7칸 단위 폭(최소 14칸, 이름 뒤 공백이 1칸 이상 남는 폭)으로 전체 이름을 덧쓴다**: 13자 `Low Cut Slope`는 14칸, 14자 `Low Shelf Gain`은 21칸, 20자 `High Shelf Frequency`는 21칸. 나머지 칸은 축약명이 그대로 남고, 오른쪽 끝에서는 56칸 안에 오른쪽 정렬로 밀린다(열 8 `Auto Gain`은 46~54칸, 열 7 20자 이름은 35칸부터). 관찰 8건으로 맞춘 모형이며 15~20자 이름이 열 7·8에 올 때 7칸 경계 정렬은 미확인(가짜 Logic `narrow_name_overlay`). 21칸 창을 그대로 읽으면 이웃 축약명이 섞인다: `Low Cut Slope Pea1Ga`, `Threshold     Attack`, `AutRel Make Up`, `AutRel     Auto Gain`.
  - 빈 파라미터 칸은 1행 `-`·2행 공백이다(Adaptive Limiter 1페이지 열 7·8, Overdrive·Distortion 열 7). 항목으로 넣으면 안 된다.
  - NAME/VALUE 전환 뒤 2행 갱신이 늦게 오는 경우가 있어(아무 LCD 변화만 기다리면 부족) 첫 읽기가 축약명을 값으로 받는다 → `Rel`(ms)·`Gain`(dB)·`Q`가 enum으로 오판돼 선택지 수집 경로로 갔다(`Rel` options `20.0ms, 21.0ms, …`).
- 삽입 메뉴 목록: 10/15 스캔 153개 → 10/19 스캔 142개, 위치가 다르다(Space Designer 52→51, ChromaVerb 110→105, Channel EQ 55→53, Compressor 15). 옛 목록으로 `insert`하면 위치 검증이 막는다(unverified "목록 위치 52에 'Rotor Cabinet'가 보임"). 원인 미확정(설치 AU 변화 또는 트랙 종류). `logic_plugin scan`(76 s) 뒤 재시도. 메뉴에 `Limiter`는 없고 `Adaptive Limiter`·`AUPeakLimiter`만 있어 "Limiter" 요청은 부분 일치로 Adaptive Limiter가 된다.
- 수집 시간: Channel EQ 4.4분(6페이지 41항목), Compressor 4.7분, Tape Delay 6.0분, Stereo Delay 4.7분, 1페이지 플러그인(Overdrive·Distortion) 1분.
- **재수집(17:43~18:07, 수정 뒤 8종)**: 이름 오염·`-` 칸 사라짐, `Side Chain Detection`(열 7, 20자) 깨끗. 남은 것: (a) 숫자 파라미터 10개(`Rel`·`Q`·`Gain`·`HiCutf`·`Devato`·`Fb`·`LFOInt`·`DelTim`·`LefDev`·`RigDev`)가 여전히 enum(선택지 16개 상한까지 전부 숫자) → 토글 2행 대기만으로는 부족, 직전 토글의 늦은 2행 쓰기가 다음 판정을 통과시킨다. (b) 스캔 목록에 `Rotor Cabinet`·`Fuzz Machine`이 두 번 다 빠짐(오버레이가 늦은 항목을 `text == names[-1]`로 stale 처리하고 넘어감) → Channel EQ(53)·Space Designer(51)·ChromaVerb(105) 삽입이 그 자리에서 다른 이름을 보고 unverified. (c) insert는 모르는 이름을 보면 포기한다. 셋 다 `fix/calibrate-quality` 2차로 수정. 선택지 텍스트 중 `5.9 ms`(`2405.9 ms`의 뒷부분)처럼 조각 쓰기 도중 읽힌 값도 보였다.
- **Z8. 삽입 메뉴 위치 모델과 빠지는 오버레이(18:35, `scan_diag.py` 1틱씩 60위치).** 위치 모델은 정확히 항목당 2위치(ceil): (1,2) Parametric EQ … (29,30) Compressor, (47,48) Distortion, (49,50) Overdrive. 그러나 (25,26,**27**) Phaser, (28) Microphaser: 27번 위치의 오버레이 쓰기가 오지 않았다(0.95 s 뒤에도 Phaser, tick()은 True; 28번에서 즉시 Microphaser). **Logic은 틱 하나의 오버레이 쓰기를 가끔 통째로 빠뜨리며** 어느 항목인지는 매번 다르다(스캔 3회 153·142·149개). 그래서 2틱 전진 스캔은 항목을 잃고 재읽기로도 회복되지 않는다 → 스캔을 1틱 전진으로(같은 이름 연속은 정상, 두 번째 위치에서 회수). 같은 항목의 두 번째 위치에서 tick()이 False(재묘사 없음)인 것은 정상.
- **1틱 스캔 실기(18:51, Z10 모달을 닫은 뒤 재연결)**: 163개를 143 s에 수집. 1~31번이 1틱 진단(위)과 정확히 일치하고, 이전 스캔들이 잃었던 Rotor Cabinet(55)·Fuzz Machine(80)·Compressor(15)·Ensemble(21)이 모두 들어왔다. 중복 없음. 이전 2틱 스캔 153·142·149개는 모두 누락이 있던 결과였다. Channel EQ 58, Space Designer 56, ChromaVerb 117, Adaptive Limiter 45, Noise Gate 35.
- **4차 수집(18:54~19:35, 수정 2·3차 반영, 8종)**: ChromaVerb(9페이지 59항목, 20분)·Channel EQ(41항목 전부 이름)·Compressor·Noise Gate·Tape Delay·Stereo Delay 수집 성공, **상한 숫자 선택지 enum 0건**(`Rel`·`Q`·`HiCutf` 등 전부 linear/log) → 수정 2차 A 실기 확인. 번들 9종 179 파라미터. map 없는 항목(Channel EQ Q 4개, ChromaVerb 11개 등)은 프로빙 실패분이며 쓸 때 다시 프로빙한다.
- **Space Designer**: 삽입은 됐지만 `calibrate`가 `page_to: 기대 page 1, 관측 16회 안에 못 감`으로 unverified → 편집 뷰 페이지 이동이 다른 플러그인과 다르다(페이지 수가 16을 넘거나 헤더 형식이 다를 가능성). 미수집, 원인 조사 필요.
- **Z9. V-Pot 63틱 메시지 유실.** Adaptive Limiter(목록 45) 삽입에서 `--`부터 90틱(63+27) 보낸 뒤 오버레이가 `Microphaser`(14번) → 정확히 한 메시지(63틱 = 31.5항목)만큼 못 갔다. insert의 근처 탐색 3회로도 복구되지 않아 unverified(안전하게 삽입 안 함). 같은 세션의 다른 7회 삽입(위치 8·10·15·35·56·58·117)은 정상. 2차 표(Gain map 없음) 유지.
- **Z10. Logic 모달 대화상자가 MIDI 수신을 멈춤.** 18:40 `no_logic`(Logic 실행 중, 포트 있음, 수신 0건, 30 s 대기 실패). 원인은 이어폰을 뽑아 Logic이 띄운 "마지막에 선택한 오디오 인터페이스를 사용할 수 없습니다" 알림(MacBook Pro 스피커로 대체). 이 모달이 떠 있는 동안 Logic은 컨트롤 서피스에 아무것도 보내지 않는다. 사용자가 확인을 누르자 즉시 재연결(장치 재설치 불필요). 진단 순서: `logic_running`인데 수신 0 → ① Logic 창의 모달 먼저 확인 → ② 그래도 안 되면 Z6(장치 삭제·재설치). `wait_ready` 실패 노트에 ①을 넣었다.
- **Space Designer 편집 뷰 실측(20:50경, testForMcp_1의 `Deluxe Classic` 트랙)**: 23페이지. 편집 뷰를 열면 1페이지가 아니라 15번 파라미터(`VoDTim`)부터, 페이지 경계도 아닌 위치에서 시작하고 ▶ 한 번에 다음 경계(`Page 3/23`)로 간다. 1페이지 NAME 헤더는 트랙 이름까지 들어가 `Track 1 "1:Deluxe Classic" Ins.1 "Space Designer (s/s)" `로 Page 토큰이 잘리고, 2페이지부터 `... "Space De    Page 2/23 `. 18:54 실패는 `page_to`의 고정 16회 한도로 판단(그때의 출발 페이지는 기록이 없어 미확인) → 한도를 총 페이지+1회로 바꾸고 실패 메시지에 출발·횟수·현재·총 페이지를 넣었다. 진단 뒤 `remove`가 unverified 1회(바로 다음 호출은 verified) — 관찰만 기록.
- **Adaptive Limiter 재수집(20:48)**: 삽입(목록 45)·수집·제거 정상. Gain `linear 0~12`·Remove DC `enum Off/On`이 채워졌고 나머지 3항목은 2차 표와 같다(5항목).
- **Z11. 프로젝트가 닫힌 Logic의 서피스 상태.** Space Designer 수집(21:12 삽입 verified) 도중 열려 있던 프로젝트(testForMcp_1)가 닫혔다(프로세스는 살아 있음. 21:19 Quartz 창 목록 "Logic Pro 창 0개"는 측정 오류였다 — 소유자 이름이 `Logic\xa0Pro`(NBSP)라 일반 공백 비교에 안 잡힘. 닫힘 자체는 다음 날 Logic '시작' 대화상자 캡처로 확인). 이때 LCD는 1행 ` -`뿐·2행 공백, 2자리 표시 `@@`, LED 없음. `wait_ready`는 ready로 통과하지만 `plugin list`는 `leave: 기대 pan, 관측 unknown`으로 실패하고, 편집 뷰의 NAME/VALUE는 2행 변화가 없어 `name_value` ModeError(calibrate unverified, 21:17), `remove`도 unverified. 진단 순서에 추가: ready인데 LCD가 ` -`뿐이면 프로젝트 닫힘 → 프로젝트를 열어야 한다. 삽입한 Space Designer는 제거하지 못했다(사용자가 저장하지 않았으면 남지 않음).
- **Z11-b(정정). 2026-10-20 00:04 '시작' 대화상자 상태에서 본 "이름은 있는데 PAN·Volume 2행이 공백, Output 열 `Ch Out`"은 닫힌 프로젝트의 서피스 상태가 아니라 Z12의 NAME 표시 상태였다(16:00 프로젝트를 연 뒤에도 같았고 NAME/VALUE 1회로 풀림). 닫힌 프로젝트의 진짜 표시는 Z11(` -`) 또는, Logic을 새로 켠 직후면 LCD 전체 공백·스트립 없음(16:00 관측).

- **Z12. NAME 표시 상태가 Logic에 남고 `configure`가 못 가려냄(2026-10-20 16:00~16:08).** 어제 21:12 수집이 NAME 모드에서 중단된 뒤 Logic은 프로젝트 닫기·재실행을 거쳐도 NAME 상태를 유지했다. PAN 뷰에서 NAME/VALUE는 2상태 토글(4회 눌러 확인): VALUE는 2행에 스트립별 팬 값(`-64    0      0 …`), NAME은 2행 전부 공백. NAME 상태에서는 TRACK 홀드 → Output 열이 값(`St Out`)이 아니라 파라미터 이름(`Ch Out`)이고, `plugin list`가 `track_param: 기대 Volume 열(dB 값), 관측 2행 ['', …] — Volume 복원 확인 안 됨`으로 실패한다. 옛 `configure` 프로브(페이더 1 재전송 → dB 텍스트)는 두 상태 모두 1열에 `+0.0 dB`가 약 1.5~2.5초 과도 표시돼 NAME 상태에서도 `already`를 돌려줬다(2회 관측). 수정(ada239a): 이름 있는 스트립이 있으면 0.5초 정착 뒤 2행 값 유무로 판정하고, 공백이면 NAME/VALUE를 눌러 값이 보이기를 기다린다(안 보이면 되돌려 누르고 unverified). 진단 순서: ready인데 `plugin list`가 Volume 복원 확인 안 됨 → `configure`를 다시 실행(NAME 상태면 고친다). 미검증: VALUE 상태인데 이름 있는 스트립 전부 2행이 공백인 뱅크(불필요한 토글 → unverified로 끝남).
- **Z13. 커서 누름이 가끔 1회 무시됨(2026-10-20 16:03).** Space Designer 수집이 `page_to: 기대 page 5, 관측 페이지 4에서 커서 반응 없음`으로 중단. 같은 순서를 그대로 밟은 재현 2회(1→23 걷기 22회 + 수집 순서 23페이지 46회 토글)는 모두 통과했고 ▶ 응답은 매번 약 35 ms(settle 포함 단계당 150~170 ms). 수정(4df8bf8): `page_to`가 무응답이면 같은 방향으로 1회 더 누른다(NAME 모드는 헤더 `Page n/N`으로 현재 페이지를 다시 읽으므로 첫 누름이 실제로 처리됐어도 루프가 바로잡는다).
- **편집 뷰 헤더 실측 추가(2026-10-20, Space Designer)**: V-Pot으로 열면 1행은 `Track 1 "1:Deluxe Classic" Ins.1 "Space Designer (s/s)" `처럼 전체 이름이고 `Page n/N` 토큰이 없다(view.page None). 커서를 한 번 누르면 `… "Space De    Page 5/23 `로 토큰이 보인다. 열리는 페이지는 임의(어제 2페이지, 오늘 4페이지). 마지막 페이지(23/23)에서 ▶는 페이지를 안 바꾸고 약 640 ms 뒤 토큰 없는 헤더만 다시 그린다 → `probe_pages`가 ▶로 토큰을 못 보면 ◀를 1회 더 눌러 보고, 둘 다 LCD가 안 바뀔 때만 1페이지로 본다(c14dce1, 마지막 페이지 경로는 실기 미검증).
- **Z14. Space Designer 7페이지의 동작 파라미터와 NAME/VALUE 사망(2026-10-20 16:20~16:45).** Space Designer 편집 뷰 7페이지는 `Load R`(Load Response)·`CreatR`·`DecodR`·`Rest..`·`Env Md`·`EQ`·`Lo Sh`·`Lo Mid`. 앞 4개는 값이 아니라 동작이라 calibrate의 선택지 수집(V-Pot 틱)이 이를 실행한다: 16:20 수집(3차)이 7페이지에 이르자 Logic에 '열기' 파일 대화상자가 떴고(Load Response), 그 순간의 NAME/VALUE 누름이 `name_value: 기대 LCD 2행 변화, 관측 없음`으로 실패(16:26:57), 서피스는 ` -`/`@@`(Z11 신호). 사용자가 대화상자를 닫은 뒤부터 NAME/VALUE 버튼이 어느 뷰에서도 반응하지 않는다(PAN 4회·편집 뷰 2회, 1행·2행 모두 무변화). 커서·V-Pot 누름·TRACK 홀드·SELECT는 정상. NAME/VALUE up·모든 버튼(0x00~0x5F) up 전송으로도 안 풀림. 또 편집 뷰가 7페이지(마지막 틱한 파라미터 자리)에서 열리고 `DecodR` 값 칸에 `DecodR`가 보였으며, 그 상태에서 ◀는 6이 아니라 1페이지로 갔다. Z6과 같은 부류의 장치 상태 손상. Logic 재실행(16:5x, 프로젝트 다시 염)으로는 안 풀렸다(NAME/VALUE 여전히 무응답, 다른 버튼은 정상) → Z6 절차로 복구(19:45~19:50): 사용자가 설정 창을 열자 **Mackie Control 항목이 2대**였다(MPK mini IV 외; Z6 때는 1대. 언제 둘이 됐는지는 모름). 둘 다 삭제 → 포트 재연결 → Logic이 1대 재설치(`configure: changed: numbers`) → NAME/VALUE가 PAN 뷰에서 2회 모두 토글(2행 값↔공백). 2대 중복이 원인인지는 확인 안 됨. 교훈: 동작 파라미터는 틱·푸시하면 안 된다 → Space Designer 수집은 7페이지 0~3열 틱을 막은 스크래치 스크립트로 하고 map은 비워 둔다(번들 표에 반영).
- **Z15. Flip 페이더 값 오버레이가 옆 열을 덮는다(2026-10-20 20:12~20:25, Space Designer).** 편집 뷰 VALUE 모드에서 Flip 페이더로 c열을 움직이면 Logic은 2행 c열 자리에 값 오버레이 **14칸**(값 왼쪽 정렬 + 공백, 예 `Mute          `·`0.0 dB        `)을 써서 c+1열 값 칸이 공백이 된다(c+2열부터 그대로). 마지막 페이더 이동 뒤 약 2.0초에 2행을 다시 그려 사라진다. 그 사이 NAME/VALUE를 누르면 약 40 ms 뒤 나머지 열은 축약명으로 바뀌지만 오버레이 14칸은 남고, 누른 지 약 1.9초 뒤 전체가 다시 그려진다(실측 `'0.0 dB        999 ms …'` → `'0.0 dB        Predly Length …'` → 1895 ms `'OutDry OutWet Predly …'`). 결과: calibrate가 c열 프로빙 직후 c+1열로 가면 `_goto_param`의 "축약명이 아님" 대기가 공백에도 참이 되어 값 칸을 공백으로 읽고(선택지 수집·프로빙 모두 건너뜀 → map None), 다음 페이지의 c·c+1열이면 이전 페이지의 오버레이 값을 읽는다(2페이지 `Volume Attack Time`을 1페이지 1열의 `0.0 dB`로). 7차 수집(19:49~20:12, 23분, 178개·23페이지, NAME/VALUE 404회·page_to 202회 무재시도)은 이것 때문에 map None이 77개(43 %, ChromaVerb 19 %). 재프로빙 2회(항목마다 Flip을 꺼도)에서 같은 항목(2·10·12번)이 똑같이 공백·이전 값 → 타이밍 우연 아님. 같은 창에서 발견한 둘: `read_value`의 21칸 창이 5열 이상에서 이웃 열과 섞여 `'1.00   High'`를 숫자 1.00·단위 `High`로 파싱(`_NUM_RE`의 `\s*`); `Length`는 페이더 1 → `91.4 s`, 16383 → `183 ms`로 단위가 바뀌는데 `infer_mapping`이 단위를 안 봐 linear(91.4, 183)을 만든다. 또 7페이지의 동작 4종(`Load R`·`CreatR`·`DecodR`·`Rest..`)이 **18페이지 1~4열에도** 한 번 더 있다(열 이름 기준 틱 차단 16회). 수정: 프로빙 뒤 `settle_overlay`, `_NUM_RE` 공백 1칸, 단위 불일치 → None(`fix/fader-overlay`).
- **Z16. 프로빙 직후 커서 응답 지연과 헤더 토큰 2초(2026-10-20 20:38~20:42).** 8차 수집(20:35, Z15 수정 적용)이 25번째 항목에서 `page_to: 기대 page 4, 관측 페이지 3에서 커서 반응 없음`으로 중단(재시도 포함 1.2초 안 두 번 무응답). 16:03의 4→5 실패와 함께 둘 다 **8열 엔벌로프 파라미터(`FirAY1`·`FirDY2`)를 Flip 페이더로 프로빙한 직후**였고, 7차(재시도 0/202)는 그 두 항목을 공백으로 읽어 프로빙하지 않았다. 같은 순서 재현(3페이지 8열·7열 프로빙 → NAME → ▶)은 33 ms에 응답 → 간헐적. 원인 미확인(추정: 값 변경 뒤 IR 재계산). 같은 재현에서: 프로빙 뒤 NAME 모드 헤더는 토큰 없는 `"Space Designer (s/s)"`이고, ▶ 뒤 2행(33 ms)·`Page 4/23`(39 ms)이 바뀐 다음 **약 2.07초 뒤 헤더가 다시 토큰 없는 형태**로 돌아간다 — 즉 NAME 모드에서 현재 페이지는 커서 누름 뒤 2초 동안만 읽을 수 있고 그 밖에는 드라이버 힌트뿐. 수정: `page_to`는 무응답이면 재누름 전에 `CURSOR_LATE_S`(3초)를 더 기다린다(바로 재누르면 두 페이지가 넘어간다). 10차 수집(21:02~21:19)은 page_to 202회에 재시도 0(1회 실행 = 예시일 뿐).
- **Z17. 설정 창 캡처로 본 장치 상태: 서라운드 파라미터 `중앙`·표시 모드 `이름`(2026-10-20 20:56~21:05).** 9차 수집(20:50, Z16 수정 적용)이 7→8페이지에서 또 `커서 반응 없음`(앞선 6→7은 3.8초 만에 응답)으로 중단된 뒤, 진단이 `_open_edit` → `read_strip_outputs`의 `track_param: 기대 Volume 열(dB 값), 관측 2행 ['', …]`로 실패하고 PAN 뷰 2행이 전부 `-`, TRACK Output 열이 `Ch Out`이었다. 그런데 `configure`는 `changed: value_mode`를 돌려줬다 — `-`도 값 텍스트로 세어 NAME 상태를 못 가린 것. 사용자가 열어 둔 **컨트롤 서피스 설정 창을 `screencapture -l`로 찍으니**(읽기 전용) CS 그룹 상태가 그대로 보였다: `플립 모드: 끔`, **`표시 모드: 이름`**, `채널 스트립 파라미터: 볼륨`, **`서라운드 파라미터: 중앙`**, `플러그인 윈도우 열기/닫기: ✓`, `포커스된 보기 따르기: ✓`, 인서트 유형 오디오·슬롯 1. 즉 PAN 뷰가 Pan이 아니라 Center 레벨을 보여 `-`였다(스테레오 트랙엔 없음). 어떻게 `중앙`이 됐는지는 미확인(`leave`는 PAN 홀드 항목을 누르지 않는다). PAN 홀드 메뉴는 `Angle  Divers LFE    Spread        CStrip Ang/Dv X/Y`(0~7열; 떼도 메뉴가 남는다). 복구: PAN 홀드 + V-Pot 0(Angle=스테레오 Pan) → 2행 공백(NAME) → NAME/VALUE → `-64    0      0      +63 …` → TRACK Output `St Out`. 교훈: ① `configure`의 값 표시 판정은 `-`를 값으로 보면 안 되고(또는 TRACK Output `Ch Out`/`St Out`로 판정), PAN 파라미터가 Pan이 아닐 때도 복구해야 한다(스펙 3 전 수정 후보). ② 설정 창이 열려 있으면 캡처로 장치 상태를 직접 읽을 수 있다. ③ `플러그인 윈도우 열기/닫기` 체크는 편집 뷰를 열 때마다 플러그인 창을 띄운다 — Space Designer GUI(IR 표시) 갱신이 Z16 지연과 관련 있을 수 있다(추정, 미검증).
 → **configure 수정(10/20 밤)**: 2행 팬 값 파싱 기준으로 판정하고 `-`면 PAN 홀드 항목 0으로 복구한다(실기 비회귀만 확인).
## 스펙 4 실측(2026-10-27)
- **Z19. TRACK 홀드 메뉴 Input 열로 Aux 판별.** 항목 3(`Input`)을 고르면 CS 뷰 2행이 `['1', '1', 'Bus 1', 'Bus 2', '', '', '', '']`(오디오 트랙 `1`, Aux `Bus 1`·`Bus 2`, 출력·Master 빈칸). 그 뒤 Volume(0)으로 복원했고, Output(4) 열은 트랙·Aux 모두 `St Out`, 출력·Master 빈칸(Z5와 같음). → 판정: Output 빈칸 = 출력·Master, Input이 `Bus`로 시작 = Aux, 그 밖 = 트랙(Input이 빈 소프트웨어 악기 트랙도 Output이 있으므로 트랙). Aux는 PL 채널 뷰가 따라가지 않는다(실전 F2: PL 2행이 선택 전 트랙의 슬롯). SE·EQ 채널 뷰도 따라가지 않는다는 것은 **가정(미측정)**이다(10차 `send get #17`(Au1)은 verified였지만 무엇을 읽었는지는 확인 안 함). 그래서 채널 뷰 명령(플러그인·센드·EQ)을 막고, 플러그인 슬롯 1만 Plug-in Mixer 뷰(V-Pot n = 스트립 n의 슬롯 1)로 삽입·제거한다(`StripAux`, 스펙 4). 홀드 메뉴는 Input → Output 두 번 + Volume 복원 한 번(`read_strip_kinds`). Output 누름이 드롭되면 2행에 Input 열이 남으므로 두 열이 같으면 판별 실패로 본다.
