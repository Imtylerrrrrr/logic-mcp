# SDD ledger — plan: docs/superpowers/plans/2026-10-16-logic-mcp-assign-2b.md
Spec: docs/superpowers/specs/2026-10-15-logic-mcp-assign-design.md (plan "스펙 보정" table overrides spec where measured facts differ)
Branch: feat/assign-2b from main 5065811 (2026-10-16). Execution: Sonnet implementers; per user's standing instruction NO per-task reviewer subagents (controller does an inline check: tests + diff stat + key points); ONE final whole-branch review on Opus.
Ruling: skip per-task reviewer dispatch — user instruction ("태스크별 리뷰 서브에이전트 금지, 토큰 비용 민감") overrides skill — cost if wrong: a task defect reaches the final review instead of being caught per task.
Ruling: plain feature branch in the main checkout instead of a git worktree — same as 2a; .venv reuse, Logic live scripts need the same tree — cost if wrong: none expected (single-writer session).

## Pre-flight scan (written from plan authoring self-review 2026-10-16 + file/interface survey)
| pair / task | shared file or interface | produces vs consumes | found |
|---|---|---|---|
| T1→T2 | ModeDriver.read_strip_outputs() -> list[str] (8 Output col texts) | T2 StripKinds.follows reads it, fills cache for all named strips | consistent (empty strip → True rule lives in T2) |
| T1,T3 | tests/fake_assign.py | T1 adds Track.kind/follows + TRACK menu; T3 adds Send model + SEND button | disjoint regions; T3 SELECT rule uses Track.follows from T1 |
| T2→T4 | Commands.strips.ensure / StripUnsupported | T4 SendCommands._channel calls ensure first, catches StripUnsupported → skipped | consistent |
| T3→T4,T5 | fake Send(dest, level, pos, muted), DEST_LIST, POS_COL, FADERS, options drop_all_vpots(T5) | T4/T5 tests | consistent; T5 adds its own fake option |
| T4→T5 | logic/sends.py _channel/_goto_page/_row/_begin/_fail, parse_send, POS_ORDER | T5 set_level/set_pos/mute | consistent |
| T4,T5→T6 | Commands.send.get/set_dest/set_level/set_pos/mute/remove signatures | tools.logic_send | consistent (send 1-8, dest str|int|None, db float|"-inf"|None) |
| T6,T9 | README.md | T6 tool-table row; T9 install step 5 + 3 constraint paragraphs | distinct regions; README rewritten 5065811 kept both anchors verbatim |
| T7→T8 | merge_bundled(bundled, name, table, generated) -> dict | scripts/calibrate_plugin.py --write | consistent |
| T8,T9 | scripts/ | T8 creates calibrate_plugin.py; T9 edits live_check2.py | disjoint |
| T1 self | track_param refuses when menu label differs → test expects no pushes | read_strip_outputs restores Volume only if `changed` | fixed at authoring |
| T4 self | set_dest remove predicate `(bus or 0) == want` (bus None for absent) | tests "already/remove" | fixed at authoring |
| T2 self | list bank loop inlined fully (no "기존 코드 그대로" placeholder) | — | fixed at authoring |
| Global | TRACK hold menu only items 0 (Volume) / 4 (Output); never 6 DisplP / 7 Setup; restore Volume | T1 code paths | T1 verifies label before push; refuses otherwise |

## Progress
Task 1: dispatched (BASE 5065811, implementer sonnet)
Task 1: complete (commits 5065811..8a02bdc, inline check ok: label-guard before push, Volume restore only when changed, leave(keep_select=True) in finally; 220 tests)
Task 2: dispatched (BASE 8a02bdc, implementer sonnet)
Task 2: complete (commits 8a02bdc..3a2f6bf, inline check ok: ensure at EQ get + PluginCommands._channel, 7 except StripUnsupported, list after.unsupported; 2 existing tests warm cache before no-push marker [implementer deviation, accepted — assertions intact]; 225 tests)
Task 3: dispatched (BASE 3a2f6bf, implementer sonnet)
Task 3: complete (commits 3a2f6bf..e2b9480, inline check ok: Send/DEST_LIST/POS_COL/POS_FULL/SEND_MENU/FADERS/LEVEL_FLOOR, se_track follows-rule, per-track se_page memory; fake_assign.py 705→860 lines noted; 228 tests)
Task 4: dispatched (BASE e2b9480, implementer sonnet)
Task 4: complete (commits e2b9480..89f2f06, inline check ok: ensure before view, DEST_PREFIX adjust ≤4, mismatch → unverified without press, finally leave_safely; tests warm strips cache before push count [accepted, same as Task 2]; implementer dropped unused imports math/set_numeric/Mapping → Task 5 must add them; 240 tests)
Task 5: dispatched (BASE 89f2f06, implementer sonnet)
Task 5: complete (commits 89f2f06..25ace46, inline check ok: absent-send skipped note, clamp note, -inf via flip+fader raw 1, set_numeric db_table, set_pos ≤2 rounds, Flip-off-after-failure test asserts flip False + view pan; 245 tests)
Ruling: batch Task 6 (logic_send tool) and Task 7 (cache m4) into ONE implementer dispatch, two separate commits — both small, disjoint files (tools.py/test_server.py/README vs plugins/cache.py/test_plugins.py), saves one subagent context — cost if wrong: a defect in one task is harder to isolate in review (mitigated by separate commits)
Task 6+7: dispatched (BASE 25ace46, implementer sonnet)
Task 6: complete (commits 25ace46..7949f6d, inline check ok: logic_send action Literal 6, send ge1 le8, dest str|int|None, db -inf string, pos Literal, README row, name set; 246 tests)
Task 7: complete (commits 7949f6d..dbce788, inline check ok: bundled_* fields w/ defaults, load deepcopy, save diff-only + bundled_generated, merge_bundled tmp+os.replace; 248 tests)
Task 8: dispatched (BASE dbce788, implementer sonnet)
Task 8: complete (commits dbce788..3b83a84, inline check ok: calibrate at assign.py:717, MAX_OPTIONS 16, _NUM_RE unit class widened + ':1' unit, script syntax ok and uses cache.param_table (exists) + merge_bundled; script not run (needs Logic) — live run 10 is 계획 밖; 251 tests)
Task 9: dispatched (BASE 3b83a84, implementer sonnet)
Task 9: complete (commits 3b83a84..d8206d1, inline check ok: README item 5 + 3 paragraphs, spec §4.3/§6.3/§7/§8 notes, SKILL.md frontmatter, live_check2 send steps; 251 tests)
Final review: dispatched (opus, package review-5065811..d8206d1.diff, report → final-review.md)
Final review (opus): With fixes — Critical 1 (C1 fail-open strip classifier when Output push dropped), Important 3 (I1 remove non-bus send false already; I2 confirm-press drop + preselect blink false verified; I3 calibrate stores settled row-1 fragment as name when tick had no effect), Minor 9 (M1..M9). Report: final-review.md
Ruling: C1 fix = verify view.kind=="track" and no dB-unit text in CS row 2 after the Output push, else ModeError (no cache) — fail-closed is the whole point of 수정 8 — cost if wrong: an occasional spurious unverified on real Logic
Ruling: adopt M7 inside the C1 fix — hold TRACK directly from PAN (measured Z5 path) instead of enter("track") then hold; restore Volume via leave→hold from PAN→Volume→leave — removes the unmeasured hold-from-CS path at the cost of one extra PAN press (~0.5 s) — cost if wrong: Logic's hold-from-PAN behaving differently after a CS param change (observe in 실기 10차)
Ruling: I1 fix = presence-based remove/already/after judgement (want==0 → not present; want>0 → bus==want and present) — spec says remove sets `--`
Ruling: I2 fix = (a) after confirm require pos not None (new) / level+pos blank (remove) AND (b) two reads ≥0.9 s apart agree; fake gets a dropped-push path (refuse VPOT_PUSH+col keeps preselect blinking) for a regression test — cost if wrong: ~1 s slower confirm
Ruling: I3 fix = accept a name only from a tick that changed the LCD (tick() True); otherwise try the opposite direction once; else name=None; drop a name equal to the settled row-1 fragment; fake gets an option that suppresses the overlay on a no-change tick — cost if wrong: fewer names collected in known.json (acceptable; names are optional)
Ruling: minors M1 (exception-path Flip-off test), M3 (indent=2), M4 (no cache when number is None), M8 (-inf already shortcut), M9 (script warning + Enter unless --yes) go into the fix wave — all small and local
Ruling: minors M2 (user entries masking bundle updates), M5 (fake PL write path not mimicking Z4), M6 (select restore after Aux insertion) deferred to 실기 10차 / later — behavioural redesign or fake fidelity, not merge-blocking
Final fix wave: dispatched (opus, FIX_BASE d8206d1)
Final fix wave: done (commits d8206d1..e5f2706: d71f864 C1+M4+M7, 86da14f I1+I2+M8, 76db898 I3, e5f2706 M1+M3+M9; 263 tests; test_server -inf expectation changed to already per M8; I2 implemented as 3 reads 0/0.45/0.9 s — stricter than ruling, accepted)
Scoped re-review: dispatched (sonnet, package review-d8206d1..e5f2706.diff)
Scoped re-review (sonnet): all 9 findings ADDRESSED, no new Critical/Important breakage; minor doubts: Volume-restore ModeError in finally masks the original error message; +0.9 s per set_dest/remove; blink timing unverified on real Logic → 실기 10차. Plan 2b complete: 5065811..e5f2706 (13 commits), 263 tests.
