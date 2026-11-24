[한국어 (Korean)](troubleshooting.ko.md) / [English](troubleshooting.md)

# 문제 해결

위에서 아래 순서로 확인하라. 각 항목의 근거는 `docs/mcu-protocol.md`의 Z 항목(실기 측정)이다. 적힌 것 밖의 원인은 확인된 바 없다.

## 1. `logic_session wait_ready`가 `no_logic` 또는 timeout

1. Logic Pro가 실행 중인가.
2. 프로젝트가 열려 있는가. 프로젝트가 닫혀 있으면(Logic '시작' 대화상자 상태) LCD 1행이 ` -`뿐이고(Logic을 새로 켠 직후면 LCD 전체 공백·스트립 없음) 서피스 명령이 실패한다. 프로젝트를 연다(Z11·Z11-b).
3. Logic 창에 모달 알림이 떠 있는가. 모달이 떠 있는 동안 Logic은 컨트롤 서피스에 아무것도 보내지 않는다. 예: 이어폰을 뽑으면 "마지막에 선택한 오디오 인터페이스를 사용할 수 없습니다"가 뜨고, 확인을 누르면 즉시 재연결된다(Z10).
4. Logic > 설정 > 컨트롤 서피스 > 설정에서 Mackie Control 항목이 없거나 2개인가(Z6·Z14). Mackie Control 항목만 삭제 → 서버를 다시 시작(포트 재연결) → Logic이 1개를 기본값으로 재설치 → `logic_session configure`. 다른 장치 항목은 건드리지 말고, "기본값 재형성"은 누르지 않는다.

## 2. `configure`가 unverified

NAME 표시 상태가 남은 경우(Z12)와 PAN 2행이 `-`인 경우(Z17, 서라운드 파라미터가 `중앙`이던 상태)는 `configure`가 자동으로 복구한다. 그래도 안 되면 위 1-4.

## 3. EQ·PLUGIN·SEND 버튼이 반응하지 않음

Logic 재시작 뒤 이 버튼들(과 PAN·TRACK)에 메시지가 없을 수 있다(Z6). 위 1-4와 같은 절차(Mackie Control 삭제 → 재연결 → `configure`).

## 4. 편집 뷰에 들어갈 때마다 플러그인 창이 열림

컨트롤 서피스 설정 창 CS 그룹의 `플러그인 윈도우 열기/닫기` 체크가 켜져 있으면 편집 뷰를 열 때마다 플러그인 창이 뜬다(Z17에서 캡처로 확인한 항목). 이 체크를 끄면 어떻게 동작하는지는 아직 측정하지 않았다.

## 5. `page_to … 커서 반응 없음`

플러그인 파라미터를 프로빙한 직후 커서 응답이 늦어질 수 있다(간헐적, 원인 미확인, Z16). 서버는 무응답이면 3초 더 기다린 뒤 한 번 다시 누른다. 그래도 실패하면 같은 명령을 다시 실행한다.

## 6. 연속 `set` 직후 값이 빈 칸이거나 이전 값

편집 뷰에서 페이더로 값을 움직이면 Logic이 값 오버레이를 약 2초 동안 남긴다(Z15). 2초 뒤 다시 읽는다. `set` 경로에는 아직 자동 대기가 없다.

## 7. `logic_plugin` `get`/`set`이 `guard: …`로 실패

서버는 페이더·V-Pot을 보내기 직전마다 LCD의 파라미터 이름을 표의 그 페이지와 비교하고, 다르면 보내지 않는다. note가 `guard:`로 시작하고 기대한 이름과 본 이름이 들어 있다. 알려진 원인 둘:

- Logic이 Cursor 누름을 늦게 처리해 화면이 다른 페이지에 있다. 같은 명령을 다시 실행한다.
- 인스턴스의 배치가 번들 표와 다르다. 번들 표에는 플러그인마다 배치가 하나뿐이다. Logic 12.0.1에서 확인한 66종 가운데 15종은 스테레오(`s/s`) 인스턴스에서 다르다: 13종은 파라미터 묶음이 두 번 나오고(DeEsser, Expander, PlatinumVerb, Parametric EQ, Low/High Pass Filter, Low/High Shelving EQ, Fat EQ, DJ EQ, High/Low Cut, Guitar Amp Pro) 2종은 좌·우 파라미터가 따로 있다(Modulation Delay, Scanner Vibrato). 모노(`m/m`) 인스턴스에서는 이 15종이 표와 같고, 확인한 67종 가운데 대신 2종이 다르다. 이 둘은 표가 스테레오 배치이기 때문이다: Space Designer(모노 89개, 표 178개)와 Level Meter. 이름이 표와 같은 페이지는 동작하고, 나머지는 엉뚱한 파라미터에 쓰는 대신 거부한다. 형식별 표는 아직 지원하지 않는다(Z24, Z25).
