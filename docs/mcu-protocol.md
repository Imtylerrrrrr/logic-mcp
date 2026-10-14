# MCU 프로토콜 실측 (Logic Pro 12.0.1, macOS 26.5, 2026-10-13~14)

## 프로토콜 요약

디바이스 ID 0x14. sysex 헤더 `F0 00 00 66 14`.

- 핸드셰이크: 쿼리 `00` → 응답 `01` + 시리얼 7바이트 + 챌린지 4바이트. 버전 요청 `13` → 응답 `14` + `V1.00`.
- LCD 쓰기 `12 <offset 0-111> <text>`, 2행은 56. 페이더 터치 감도 `0E <ch> <0-5>`. `72 ...`는 미해독(픽스처만).
- 버튼/LED: Note On ch1, 0x7F on / 0x00 off. REC 00-07, SOLO 08-0F, MUTE 10-17, SELECT 18-1F, V-Pot push 20-27, TRACK 28 SEND 29 PAN 2A PLUGIN 2B EQ 2C INST 2D, BANK◀ 2E BANK▶ 2F CH◀ 30 CH▶ 31(뱅크(8칸)와 채널(1칸) 이동은 트랙 9개 이상 프로젝트로 실기 확인 예정(2026-10-14 기준 미확인)), FLIP 32, NAME/VALUE 34, SMPTE/BEATS 35, SHIFT 46 OPTION 47 CTRL 48 ALT 49, CYCLE 56, REW 5B FFWD 5C STOP 5D PLAY 5E REC 5F, 페이더 터치 68-6F, LED SMPTE 71 BEATS 72 RUDE SOLO 73.
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
