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
