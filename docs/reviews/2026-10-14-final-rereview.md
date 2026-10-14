# Final re-review: fix round 95dc685..04ab9db

pytest: 66 passed.

## Verdicts
- I1 ADDRESSED. state.py reduce() DeviceQuery branch now sets last_display_change=now (diff hunk @@ -119). New test test_requery_after_ready_requires_install_quiet_again covers handshake at +1 s and +9 s, ready at +10.1 s. First-install path unchanged (now > 0).
- I2 ADDRESSED. faders.py: -72 stand-in removed; _finite() used by db_to_raw/raw_to_db; -inf -> 0, below lowest finite -> lowest finite raw, above +6 -> 14845; raw_to_db 0 -> -inf, 0<raw<lowest -> lowest finite dB. test_clamp_and_monotonic sweeps -130..+6 (raw>0, non-decreasing) and raw 1..14845 (db non-decreasing). Edges are monotonic.
- I3 ADDRESSED. Strip.fader_known set in FaderPos (state.py); configure requires ready (skipped, note mentions wait_ready); returns unverified before any pitch-bend/NAME/VALUE press when strip 1 fader is unknown; failure after OPTION+NAME/VALUE or NAME/VALUE re-presses and appends "(되돌려 눌렀음)". Three new tests cover these (including no E0 message sent and NAME_VALUE pressed twice).
- I4 ADDRESSED. docs/mcu-protocol.md and spec appendix A now BANK-left 2E, BANK-right 2F, CH-left 30, CH-right 31, matching protocol.py; doc notes bank/channel movement is unverified live (docs file line ~11).

## New breakage in the fix diff
None. Happy path of configure unchanged (existing test updated only to feed a FaderPos).

## Out-of-scope observations
- In configure, if step 1 (numbers) succeeds and then the fader-unknown early return fires, numbers stay on (a successful change, not a stray toggle); a re-run skips step 1. Acceptable.
- Live Step 6 (>=9 tracks bank navigation) is still pending; README caveat not checked.
- The unverified-note about bank movement sits between bullets in mcu-protocol.md, splitting the list (cosmetic).

## Overall: all addressed (0 open)
