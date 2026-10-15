# SDD ledger — plan: docs/superpowers/plans/2026-10-15-logic-mcp-assign-2a.md
Branch: feat/assign-2a (from main fb76640). Spec: docs/superpowers/specs/2026-10-15-logic-mcp-assign-design.md
Ruling: 태스크별 리뷰 서브에이전트 생략, 최종 리뷰 1회만 — 사용자 지시(토큰 비용) — 비용: 태스크 결함이 최종 리뷰까지 늦게 발견될 수 있음. 컨트롤러가 각 보고서·테스트 결과를 직접 확인한다.
Ruling: 구현자는 Sonnet 고정(사용자 지시), 최종 리뷰는 Opus.

## Pre-flight scan
| 공유 파일/인터페이스 | 생산 | 소비/수정 | 결과 |
|---|---|---|---|
| protocol.py vpot_turn_messages, Note.CURSOR_* | T1 | T4 modes.tick | 시그니처 일치(channel, steps)->list[bytes] |
| values.py Value/parse_value/Mapping/raw_for/infer_mapping/within | T2 | T4 read_value, T5 setter, T6, T8 | 이름 일치 |
| state.py View/classify_view/OVERLAY_MARK/COL_W | T3 | T4 modes, T10 status.view_kind | 일치 |
| modes.py ModeDriver | T4 생성 | T8 read_overlay_text 추가, T9 shift_press_vpot 추가 | 추가만, 충돌 없음 |
| commands.py | T4(modes, mixer_pan) | T6(eq/plugin 지연 임포트, PluginCommands 스텁 L2148) → T8(plugin_cache 인자, 스텁 교체) → T10(status view_kind) | 순차 수정, T6 스텁→T8 본문 일관 |
| assign.py | T6 EqCommands+PluginCommands 스텁 | T8 본문, T9 insert/remove/bypass/scan | 일관 |
| plugins/match.py | T7 | T8 strip_suffix 추가 | 추가만 |
| tests/fake_assign.py | T4 | T5,T6,T8,T9,T10 | 모델 확장 없음(T4에 전부) |
| tests/test_assign_plugin.py | T8 | T9 추가 | 추가만 |
| Review Focus 1-5 | T4(1,2,5) T8(3) T6(4) T1(5) | — | 각 테스트 이름 계획에 존재 |
각 태스크 자체 일관성: 계획 작성 시 self-review 수행(LCD_SYSEX 수정, 헤더 56자 패딩, 틱 순서 수정 반영). 추가 발견 없음.

## Tasks
Task 1: complete (commits fb76640..093ba62, 69 tests, controller-verified diff; no reviewer per ruling)
Task 2: complete (commits 093ba62..4edcd0e, 103 tests, controller-verified)
Task 3: complete (commits 4edcd0e..fcd2fb8, 110 tests, controller-verified)
Task 4: complete (commits fcd2fb8..924acc6, 121 tests, RF1/2/5 tests present, controller-verified)
Task 5: complete (commits 924acc6..a83200c, 129 tests, controller-verified)
Task 5: minor (deferred): setter.py:49 조건 `A and B and C or D`가 의도(log는 n>0일 때, linear는 항상 보정)대로 동작하지만 괄호 없이 읽기 어려움 — 최종 리뷰에서 정리 여부 판단
Task 6: complete (commits a83200c..0521a3c, 137 tests, RF4 test present, controller-verified)
Task 7: complete (commits 0521a3c..21cebaa, 142 tests, known.json 67 items verified, controller-verified)
Task 8: complete (commits 21cebaa..f7ce5d4, 150 tests, RF3 test present, DONE_WITH_CONCERNS 처리 아래)
Task 8: Ruling: fake_assign.py 깜박임이 유효한 오버레이를 덮지 않게 수정(브리프 외 파일) — 스파이크 실측 "2초 오버레이 → 그 뒤 깜박임"과 일치하므로 수용 — 틀리면 실기 params에서 read_overlay_text가 `--`를 읽음(Task 11 live_check에서 확인)
Task 8: minor (deferred): assign.py에 브리프가 넣은 미사용 임포트 re/find/within → Task 9 디스패치에서 정리 지시
Task 9: complete (commits f7ce5d4..eb18db8, 156 tests, DONE_WITH_CONCERNS 처리 아래)
Task 9: Ruling: scan_list에 "오버레이 1행에 'Plug-in' 없으면 stale" 조건 추가(브리프 외) — 목록 끝에서 오버레이 만료 후 열 재묘사를 이름으로 오인하는 결함을 막음, 실측 1행 `Insert 1 Plug-in`에 근거 — 틀리면 실기 scan이 3항목 만에 멈춤(Task 11 live_check 확인 항목)
Task 9: housekeeping: assign.py 미사용 임포트 re/within 제거(find는 insert가 사용)
Task 10: complete (commits eb18db8..245e52a, 158 tests, controller-verified; test_tool_list_and_names에 새 툴 2개 추가는 정당)
Task 10: minor (deferred): tests/test_server.py 끝부분에 임포트가 위치(브리프대로) — 최종 리뷰 수정 물결에서 상단으로 이동
Task 11: steps 1-3 complete (commit eba27bb, 158 tests); step 4 live run by controller below
Task 11 step 4: live run 1 FAILED — EQ enter가 홀드 메뉴(E_)에서 조기 종료, 플러그인 slot_to(P<n> 커서) 무반응. 탐침 3회(probe_slot{,2,3}.py) 실측 → fix-1-brief.md
Ruling: 슬롯 접근 경로를 P<n> Mixer+커서 → PL Channel 뷰 V-Pot n으로 변경(실측 B·C) — 비용: Task 8·9 재작성, fake 재모델
Ruling: 미리 선택 표시 = ceil(pos/2); 이름 드러내기는 -1 틱, _open_edit는 틱 없이 누름(실측 E·F) — 틀리면 누름 시 교체 사고 → 테스트 (a)(b)로 고정
Ruling: 슬롯 9~15는 2a 미지원(접근 경로 미확인) — 문서 명시
Fix 1: complete (commits eba27bb..a652492 after trailer rewrite, 172 tests). live run 2: eq get/gain/on, plugin list/remove verified; 4 failures → fix-2-brief.md (P~S)
Ruling: EQ 채널 뷰는 마지막 페이지를 기억(실측 Q) → _goto_page는 열 이름으로 현재 페이지 판정; enter 단계 대기 3 s(실측 P); parse_value 미등록 단위도 숫자 유지(실측 R); 틱 뒤 0.4 s 조용 대기(실측 S)
Fix 2: complete (commits a652492..655d1bc, 180 tests). live run 3: 16/17 verified (eq freq/gain/slope/on/get 밴드 1~8, plugin list/insert/params(3p)/set/get/bypass on·off/remove); 실패 1: eq set q → fix-3-brief.md (T~V: Q는 log 0.10~100, 틱 ×1.06)

Fix 3: complete — 1332fad (EQ Q log 0.10~100 매핑, 틱 보정 로그 영역을 mapping.type=="log"로 일반화, 단위 없는 값 허용 오차 2 %). 182 passed. 트레일러 Fable 5.1 확인.
  Deferred minor: Q 허용 오차 0.04@2.0 은 틱 격자(≈6 %)보다 촘촘함 — 정확 매핑 경로는 페이더로 안착하므로 틱 폴백에서만 문제. 실기 4차로 판정.
  Deferred minor: tests/fake_assign.py 가짜 Compressor 는 `Thresh`/2페이지, 실측은 `Thrs`/3페이지(docs 부록 참조). 최종 리뷰에 전달.
  Note: 구현자가 setter 변경과 신규 setter 테스트의 인과를 되돌려 확인하지 못함 → 컨트롤러가 diff 로 확인(log_domain 조건에 mapping.type=="log" 추가, 4줄). 수용.

Live run 4 (1332fad, --scan): 17/17 verified (eq set b4 q 2.0 → 2.00 'fader' 경로, 스캔 153개 75 s, 상태 PAN 복귀). 로그 scratchpad/live_check2_run4.log.
  새 결함 W: 편집 뷰 마지막 페이지 오른쪽 정렬 → params 24항목 중 13~16==17~20 중복, 이름 조회 `Mix` 모호. (실기 3·4차 동일)
  새 결함 X: 페이더 에코가 LCD 값 쓰기보다 먼저 와 probe_mapping이 이동 전 값을 lo로 읽음 → 캐시 Thrs map linear -20..0(실제 -60..0). 캐시의 params.Compressor 항목을 컨트롤러가 제거(재프로빙 유도).
  Y: live_check2 `set Thrs -20`이 기본값과 같아 'already' — -24로 바꿔 set 경로를 실제로 타게 함.
Fix 4: dispatched (Sonnet) — fix-4-brief.md (W·X·Y). 완료 후 실기 5차(--scan 없이) → 최종 리뷰.
Fix 4: complete — 2115946 (W 마지막 페이지 겹침 제거 + _merge_items 전체 읽기 반영, X fader 에코 뒤 LCD 변화 추가 대기, 가짜 Compressor 실측 20항목/3페이지, live_check2 Thrs -24). 187 passed. 트레일러 확인.
  Deferred minor: N%8==0 플러그인에서 마지막 페이지 첫 열이 직전 페이지 마지막 열과 (short,text) 모두 같으면 k=1 오탐 가능 — LCD만으로 N을 알 수 없어 방어 없음. 최종 리뷰에 전달.
  Note: fake lcd_lag은 별도 `lagged` 목록(첫 판정 거짓인 wait_for에서 flush)으로 재현 — deferred는 _settle의 sleep이 flush해 옛 코드도 통과했기 때문. 수용.
  Note: fader()가 에코를 먼저 기다리므로 에코가 없는 경우 FADER_TIMEOUT 뒤 None — set_numeric은 반환값을 쓰지 않아 비용은 대기 시간만.
Live run 5: running (2115946, --scan 없음) — 기대: params 20항목, set Thrs -24 'fader'/'verified', 캐시 Thrs map -60..0.
Live run 5 (2115946): 15/17. 플러그인 전부 통과 — params 20항목(W 해결), set Thrs -24 'fader' 검증, 캐시 Thrs map linear -50..0(재프로빙, X 해결; 페이더 한 번에 -24 안착하므로 -50..0 이 실제 범위). 실패 2건은 EQ: `gain -3` "flip: FLIP LED 변화 없음"(0.5 s), `q 2.0` "V-Pot 틱에 LCD 반응 없음"(Q가 13.0 으로 남음). 두 건 모두 4차에서 통과했던 항목.
Live run 6 (2115946): 17/17 통과 → 5차 EQ 실패는 간헐적. 재현율 측정용 EQ 반복 프로브(scratchpad/probe_eq_repeat.py, 3라운드×4설정) 실행 중.
EQ 반복 프로브 1회(3라운드×4설정, 2115946): 12회 중 1회 실패 — 1라운드 `q 2.0` → 13.0, "틱 LCD 반응 없음"(5차와 동일). 실패 시 소요 ≈+1.4 s = FADER_TIMEOUT+FEEDBACK_TIMEOUT → 페이더 이동 한 번이 Logic에서 통째로 무시됨(Z1). 그 뒤 이동 전 값으로 시컨트 보정 → 폭주. FLIP 무시(Z2)는 5차 1회만.
Fix 5: dispatched (Sonnet) — fix-5-brief.md: fader() 무반응 시 1회 재전송, flip() LED 무반응 시 1회 재누름, set_numeric 시컨트 가드(이동 전 값과 같으면 보정 생략), 가짜 drop_first_fader/drop_first_flip, 테스트, 문서 Z1·Z2. 완료 후 프로브 2회(3라운드씩) + 실기 7차 → 최종 리뷰.
Fix 5: complete — 7cc4d34 (fader 무반응 1회 재전송, flip LED 무반응 1회 재누름, set_numeric 시컨트 가드 + 조건식 괄호 정리(동작 동일), 가짜 drop_first_fader/drop_first_flip/drop_all_faders, 테스트 5, 문서 Z1·Z2). 192 passed. 트레일러 확인.
  Note: 가짜에서는 실기의 13.0 폭주가 재현되지 않음(틱 6회 안에 수렴) → (c)는 회귀 방지용, 가드 검증은 (d) drop_all_faders. 실기 검증은 프로브로.
  Deferred minor: 목표 raw가 현재 페이더 위치와 같아 에코·LCD가 모두 없는 정상 경우에도 재전송 → +1.4 s. set_numeric은 'already'를 먼저 걸러 드물다. 수용.
  Deferred minor(기존 setter.py:49 가독성 항목)는 이 커밋에서 괄호 정리로 해소.
EQ 반복 프로브 2회(7cc4d34) 실행 중.
EQ 반복 프로브 2회(7cc4d34): 12/12 통과, 전부 ≈4.4 s(재시도 미발생). 수정 전 1/12 → 수정 후 0/12. 무시 현상 자체가 이번엔 안 나와 재시도 경로의 실기 효과는 미확인(가짜 테스트로만 검증). 증거 부족 상태로 기록.
Live run 7: running (7cc4d34, 전체).
Final review: dispatched (Opus) on fb76640..7cc4d34 — review-fb76640..7cc4d34.diff, 보고서 review-final-report.md. 보류 항목 5건(test_server 임포트 위치, N%8==0 겹침 오탐, fader 재전송 +1.4 s, Q 허용 오차 2 %, 슬롯 9~15 미지원) 판정 요청. 실기 7차와 병행.
Live run 7 (7cc4d34): 17/17 통과, 상태 PAN 복귀. 집계 — 1332fad: 4차 17/17 | 2115946: 5차 15/17·6차 17/17·프로브 11/12 | 7cc4d34: 7차 17/17·프로브 12/12. 간헐 실패(Z1·Z2)는 수정 후 29회 설정에서 미발생이나 재시도 경로 실기 발동은 미관측.

Final review: 결과 With fixes — Critical 1(C1 FLIP 재누름 × 늦은 LED → Flip 꺼진 채 페이더가 볼륨 이동 가능), Important 5(I1 mixer_volume Flip 가드 없음, I2 leave 중단, I3 입력 검증 부재, I4 프로빙 실패 시 복원 없음, I5 캐시 깨짐/비원자 저장), Minor 10.
Ruling: C1 은 재누름 제거 + fader 송신 직전 Flip 가드 + FLIP LED 대기 1.0 s 로 해결(재누름 유지안은 LED 지연 시 위험을 제거하지 못함) — 비용: Z2 무시 1/20 은 명령 실패(unverified)로 사용자가 재시도. 
Ruling: I1~I5 모두 수정. m1·m2·m3·m5·m7·m8·m9 수정, m10 문서화, m6 은 live_check2 에 뱅크 list 추가해 실기 8차에서 확인. m4(번들 갱신 미반영)는 2b 이월(번들 표가 2b 산출물). 보류 4(Q 허용 오차)·5(슬롯 9~15 표시) 권고는 변경 없이 수용.
Ruling: Declined-to-judge 9건 전부 범위 밖 인정(프로빙·자동 삽입은 스펙, 센드·번들표·스킬은 2b, 타이밍 상수는 실측, 비ASCII 트랙명은 스펙 1 전제).
Fix 6: brief 작성(fix-6-brief.md A~H). Sonnet 디스패치 예정 → 테스트 → 실기 8차 → 범위 한정 재리뷰 1회.
Fix 6: complete — f4dcc5d(C1·m2) ef14db7(I1·I2·m7) c401a03(I3·I4·m5·m9) 4d90793(I5) a70d74c(G·H docs/tools/live_check2). 216 passed. 트레일러 5건 확인. 작업 트리 깨끗.
  Note: A.5(a) 수정 전 실패는 flip_led_lag 단독에서 확인(트랙 2 볼륨 7168 로 변함 = C1 재현). drop_first_flip 조합은 수정 전에도 통과(무시된 누름은 지연과 겹치지 않음) → 회귀 가드.
  Note: flip_led_lag 지연 모델은 구현자가 정한 것(첫 대기 초과 뒤 도착) — 실기 지연 분포 미측정. set_numeric 실패 시 map 무효화는 원인 불문(브리프대로).
Live run 8: running (a70d74c, 새 단계: get 21 index, insert Limiter replace, list bank). 범위 한정 재리뷰: review-7cc4d34..a70d74c.diff 생성.
Re-review (Sonnet, 7cc4d34..a70d74c): C1·I1~I5·Minor 묶음 전부 ADDRESSED, 새 Critical/Important 없음.
Ruling(잔여): (1) LED가 1.0 s 뒤에 오면 Flip이 켜진 채 끝날 수 있음 — 안전한 방향(페이더 미전송), 다음 명령의 leave_safely/mixer_volume 가드가 정리 → 수용. (2) EQ on 문자열 거부 — tools.py 스키마가 float|bool 이라 문자열은 애초에 안 들어옴 → 수용. (3) set_numeric 실패 시 map 무효화는 원인 불문 — 다음 set 에서 재프로빙으로 복구되므로 수용. (4) commands.py:367 채널 0 페이더는 configure 의 값-표시 프로브로 현재 raw 를 그대로 재전송(값 불변) → Flip 가드 불필요, 수용. (5) save 중단 시 .tmp 잔류 — 다음 save 가 덮음 → 수용.
Final review loop closed at a70d74c. 남은 것: 실기 8차 결과 확인 → finishing-a-development-branch.
Live run 8 (a70d74c): 20/20 verified — 새 경로 get 21(index→Mode), insert Limiter replace=True, list bank(29 s) 포함. 단, list bank 결과가 의심: 트랙 16·18·20·24 의 "슬롯"에 트랙 이름 조각(Deluxe/Classic/Master)이 선택 스트립 열 위치(n, n+1)에 나타남 → 리뷰 m6(PL에서 SELECT 뒤 2행 갱신은 가짜의 가정)이 실기에서 틀린 것으로 추정. 캐시 abbrev 오염 없음(드러낸 이름 `--`). LCD 프로브(probe_pl_select.py)로 실측 중.
PAUSED 2026-10-15 15:49 — 사용자 요청("지금 써야해서 잠깐 멈춰줘"). Logic 접촉 전부 중단. 마지막 두 프로브(probe_pl_select.py)는 Logic 무응답(handshake timeout, state animating)으로 실패, 프로젝트 변경 없음(leave_safely 완료). 
재개 시: (1) PL 뷰에서 SELECT 뒤 2행 실측(probe_pl_select.py) → m6 결함 확정 시 fix 7(list bank: 2행 갱신 대기 또는 뱅크 list 를 트랙별 PL 재진입으로) + 실기 9차 → (2) finishing-a-development-branch 메뉴(main 머지 / PR 없음(원격 없음) / 유지) → (3) 메모리·볼트 갱신 → compact.
HEAD a70d74c, 216 passed, 작업 트리 깨끗. 최종 리뷰·재리뷰 통과(C1·I1~I5 해결). 미해결: list bank 인벤토리 오류 의심(m6).
fix-7 (2026-10-15 재개): Logic 꺼져 있어 probe_pl_select 실측 불가. Ruling: 2행 실측 없이도 맞는 방향(다른 트랙은 PAN→SELECT→PL 재진입, 단일 트랙 명령이 밟은 검증 경로)으로 _channel() 수정 — 틀릴 경우 비용은 뱅크 list 트랙당 ≈0.6 s 추가뿐. 가짜에 pl_select_stale 옵션(최소 가정: 2행이 이전 트랙을 유지) + 회귀 테스트 + live_check2 식별 안 된 슬롯 검사 + Z3 문서. BASE a70d74c. 브리프 fix-7-brief.md, 보고 fix-7-report.md. 실기 9차는 사용자가 Logic 을 열어 줄 때.
fix-7 complete: e2c4d6a — _channel() PL 재진입, 가짜 pl_select_stale + pl_track, test_list_bank_reenters_pl_per_track, live_check2 식별 안 된 슬롯 검사, Z3 문서. 217 passed. 컨트롤러 확인: 가짜 옵션 적용 상태에서 _channel 수정만 되돌리면 t[16][1] 단언에서 실패(테스트가 수정에 의존함을 확인). 리뷰 서브에이전트 없음(사용자 토큰 제약, 최종 리뷰는 a70d74c 에서 끝남; 이 diff 38줄은 컨트롤러가 직접 읽음). 실기 9차 미실시(Logic 꺼짐). 다음: finishing-a-development-branch 메뉴.
