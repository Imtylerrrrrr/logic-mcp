# Final review — feat/core-mcu (8ec7dfb..HEAD)

Reviewer: Opus, 2026-10-14. Inputs: review-final.diff, spec, plan header (L1–36), ledger, and the source files read in full (one pass per layer). `uv run pytest -q` → 62 passed in 10.58 s. Three findings were reproduced with short read-only Python probes (no MIDI port opened): the re-handshake bypass and the two fader-table end cases.

## Strengths

- The layering is clean and matches spec §3. `protocol.py` is pure: bytes go in and events come out. `state.py` is a pure reducer over frozen dataclasses. `Surface` is the only place that holds a lock, and `Commands` only ever sees `Surface`. Snapshots are immutable, so resources can read state without taking the command lock.
- All five Review Focus items are met. Truncated or empty sysex decodes to `Unknown`. NaN is refused, values above +6 are clamped with a note, and `"-inf"` maps to fader 0. strip/number is enforced as exactly one of the two, with guidance. `12:Aud` parses to (12, "Aud"), and a column without a prefix gives `None`. The pan reveal nudge sends one +1 and then skips.
- `handshake_reply` answers 0x14 only, and its output is byte-compared against the TX lines in the fixture. The port name is fixed. `close()` uses `delete()`.
- The tests rest on real captured fixtures rather than on fakes alone. Examples: the replay of the install animation (669/676/700/745 animating, 747.5 ready), the fixture-based MUTE/PLAY/time/fader checks, and a decode-everything sweep.
- Live verification was honest. The ledger records real defects found on hardware: the truncated `-55.0 d` text, the 7.6 s gap in the install animation, and LCD row 2 showing the last-touched parameter. Each was fixed with a ruling instead of being hidden. The calibrated table is monotonic, with 233 points.
- Idempotency is LED-based, and no toggle actions are exposed. Sync tools run through `anyio.to_thread` (verified in mcp 2.3.0 `func_metadata.py:164`), so the global `threading.Lock` really does serialize concurrent tool calls.

## Issues

### Critical

None.

### Important

**I1. A DeviceQuery that arrives after an earlier session skips the 10 s install quiet entirely.** `src/logic_mcp/mcu/state.py:127-130, 195-197`
- What's wrong: on DeviceQuery 0x14, the reducer sets `state="handshake", installing=True` but leaves `last_display_change` untouched. `tick()` promotes `handshake` to `ready` once `now - last_display_change >= INSTALL_QUIET_S`. On a first install `last_display_change == 0`, and the `> 0` guard saves it. On any later handshake, `last_display_change` is minutes old, so the next tick (≤100 ms) promotes straight back to `ready`. Later LCD writes never demote `ready`. Later handshakes happen when Logic is relaunched or a project is reopened while the MCP server keeps running, which is the normal case because the server lives as long as the Claude Code session. Reproduced: install, then ready, then a query at t=500, then tick at 500.1 → `ready`, `installing` reset.
- Why it matters: this contradicts the controller's ruling ("10 s after a handshake"). If Logic plays the welcome animation on that handshake, `wait_ready` returns immediately. Commands sent during the animation are then ignored and come back as timeout/unverified, which is exactly the failure the 10 s rule exists to prevent.
- Fix: in the DeviceQuery branch, also set `last_display_change=now`. Optionally reset `configured` too (see M10). Add a state test: ready → DeviceQuery → still `handshake` after 1 s and after 9 s → `ready` 10 s after the last LCD write. If Logic turns out not to animate on a re-query, the cost is a 10 s wait on project reopen. That cost is the one the ledger already accepted.

**I2. The low end of the fader table maps -72…-119 dB to -inf and reports it as verified.** `src/logic_mcp/logic/faders.py:13, 37-38, 50-58`
- What's wrong: `-inf` at raw 0 is replaced with `_MIN_FINITE_DB = -72.0`. The comment claims "no effect once the calibrated table is in", but the calibrated table now starts `[0,-inf],[63,-119.0],[127,-94.7],[192,-70.0]`. Its finite values go below -72, so the substituted list is non-monotonic. Measured results: `db_to_raw(-80)`, `(-100)` and `(-119)` all return `0`, which is the fader at -inf. `db_to_raw(-72)` also returns 0. `raw_to_db(1)` = -72.7 while `raw_to_db(30)` = -94.4, so dB falls as raw rises. `mixer_volume(-90)` therefore silences the track completely and returns `ok=True, verified`, with an empty note. `strips[].fader_db` is wrong for raw 1…191.
- Why it matters: the tool silently does something other than what was asked and claims it verified the result. The existing monotonic test only sweeps from -60 dB, so it cannot see this.
- Fix: substitute below the table's own minimum, e.g. `min(finite) - 1.0` (= -120). Alternatively, special-case raw 0 and interpolate only over the finite points. Extend `test_clamp_and_monotonic` to sweep -130…+6 and to assert that `raw_to_db` is monotonic over 1…14845.

**I3. `configure` can change the user's project and leave surface toggles flipped.** `src/logic_mcp/logic/commands.py:330, 335-353`
- What's wrong, in three parts:
  - (a) The step-2 probe resends `strips[0].fader_raw`. That field defaults to `0` until Logic echoes a FaderPos for channel 0, and nothing records whether a position has been received. If configure runs before the echo arrives, the probe sends raw 0 and track 1 drops to -inf. The probe then sees `-oo dB`, counts as success, and configure reports `ok`.
  - (b) `configure` runs in `animating` as well as `ready`. The spec says Logic ignores buttons during the install animation, and the LCD and fader state are mid-redraw at that point, so (a) is most likely to fire then.
  - (c) On the failure paths, the NAME/VALUE press (step 2) or the OPTION+NAME/VALUE press (step 1) is left toggled. Example: strip 1 has no track, so the probe can never see dB text. NAME/VALUE gets pressed, the probe fails again, and configure returns `unverified` with the display mode flipped away from what the user had.
- Why it matters: configure is the one step the README tells every user to run. Changing track 1's volume, or leaving the display in the wrong mode, is exactly the kind of change the user did not ask for.
- Fix:
  - Require `ready`, and tell the user to run `wait_ready` first.
  - Add a `fader_seen: bool` (or `fader_raw: int | None`) to `Strip`, set from FaderPos. Skip the probe, or fail with a note, when strip 1 has no known position or no number/name.
  - On a failure after a toggle press, press the same button again to restore it before returning, and say so in `note`.
  - Add a test with a fake that never echoes the fader: assert that no pitch-bend message is sent.

**I4. The bank/channel note numbers disagree between code and docs, and bank navigation has not been verified live.** `docs/mcu-protocol.md:9`, spec Appendix A vs `src/logic_mcp/mcu/protocol.py:28-31`
- What's wrong: the docs and spec say `BANK◀ 2E CH◀ 2F BANK▶ 30 CH▶ 31`. The code uses `BANK_LEFT 2E, BANK_RIGHT 2F, CHANNEL_LEFT 30, CHANNEL_RIGHT 31`. The code matches the standard MCU map, which is also what REAPER `csurf_mcu` and Apple's guide use, so the code is most likely right and the doc and spec are wrong. That doc is labelled as a measured record, though, and the live check ("bank right → unverified, 3 tracks") cannot tell the two maps apart. `logic_bank`, `_show_number` and every number-addressed command outside the first bank depend on this mapping. Plan Step 6 (≥9 tracks) is still pending.
- Why it matters: if the doc is right, `logic_bank right` actually performs channel-left. Number addressing would then walk the wrong way and report "number N not found". The project rule is "mark done only after checking against the real Logic".
- Fix: correct `docs/mcu-protocol.md` and spec Appendix A to 2E/2F/30/31 (this is a spec/doc error, not a code error). Before merge, run Step 6 with a project of 9 or more tracks covering right/left/channel_right/first/last/show and a number-addressed mute. If that cannot happen before merge, say in the README that bank navigation is unverified.

### Minor

- **M1 Thread-model deviation from spec §3.** `src/logic_mcp/mcu/surface.py:56-63`. The spec calls for the callback to only enqueue, with a separate reducer thread. The implementation decodes and reduces on the CoreMIDI thread under the RLock, and sends the handshake reply from that thread too. That is acceptable: reduce is cheap, `send_message` holds the GIL, and messages interleave at message granularity. Record it in spec §3 so the next reader does not "fix" it the other way.
- **M2 Wrong timeout vs unverified classification.** `commands.py:155`. Any RX after t0 counts as "feedback came", including meters and time digits during playback. As a result `timeout` is almost never reported while Logic is alive. Compare the relevant LED or strip view instead, as `mixer_volume` already does at L243.
- **M3 Tool annotations differ from spec §4.** `tools.py:18,25,34,52,60`. `destructive_hint` is never set, and the MCP default is true, while the spec says false. `logic_transport` claims `idempotent_hint=True` even though it includes rewind/fast_forward. `read_only_hint` for `logic_session status` cannot be expressed per action, which is a spec issue: either split the tool or drop that line from the spec.
- **M4 FLIP is not checked.** `commands.py:257` (pan) and `221` (volume). With FLIP on, the fader and V-Pot swap roles. The pan reveal nudge would then move the volume, and set_volume would move the pan while still verifying through the echo. The spec says nothing on this. Refuse when `assignment.flip` is set.
- **M5 `db` is not rounded to 0.1** as spec §4 requires. One line: `round(db, 1)` in `mixer_volume`.
- **M6 The scripts leave the user's project changed.** `scripts/live_check.py:21-24` ends track 1 at 0 dB and pan 0 instead of its original values, and ends with cycle off. `scripts/calibrate_fader.py:28-29` restores the fader outside `finally`, so a Ctrl-C mid-sweep leaves the fader wherever it was. It also relies on `fader_raw`, which may be unknown (see I3a), and `OUT` is relative to the current directory. Capture the before-values and restore them in `finally`. Add a "stop playback first" line to the docstring.
- **M7 Stale detection.** `state.py:198`: if Logic quits while the PLAY LED is on, `stale` never becomes true. `logic_running` covers this. Either clear `transport.play` on stale or document it.
- **M8 SMPTE time is not parsed.** `TimeDisplay.parsed()` returns None for SMPTE, while spec §4 asks for hh/mm/ss/ff. configure forces Beats, so the impact is low.
- **M9 Schema rejection bypasses ToolResult.** With strip 0 or 9 over MCP, pydantic rejects the call at the schema level (`ge=1, le=8`). The client gets a validation error rather than a ToolResult with guidance, so the Commands-level guidance in `_resolve` can only be reached from Python. That is acceptable, but it is a small deviation from "every tool returns ToolResult".
- **M10 `configured` never resets.** `Commands.configured` stays true across re-handshakes and new projects, so `status.configured` can be stale.
- **M11 Private access.** `resources.py:26` calls `commands._strip_view`. Make it public, e.g. `strip_view`.
- **M12 Slow test suite.** 10.6 s (see the triage below).
- **M13 rewind/fast_forward not checked live.** These actions were never tried on hardware. The live check should confirm that a 30 ms press does not latch a continuous shuttle in Logic, which would keep the playhead moving until stop.
- **M14 Pan extreme unreachable.** Going from +63 to -64 needs 127 steps, but only two ±63 messages are allowed (spec §6), so that one case ends `unverified`. This is a spec limitation; note it or allow three messages.

## Deferred-minor triage

| Ledger line | Ruling |
|---|---|
| Task 10: minor (deferred): test suite 8.7 s (now 10.6 s), real-time timeout waits | **Not required before merge.** It does not affect correctness. A cheap follow-up is to make `LED_TIMEOUT`/`BANK_TIMEOUT` instance attributes, or module constants that tests monkeypatch, so the timeout-path tests run with ~0.05 s. |

No other `minor (deferred)` lines exist in the ledger.

## Declined to judge

- rtmidi `MidiOut` thread-safety across the CoreMIDI callback and tool threads: python-rtmidi holds the GIL during `send_message`, there is no evidence of a problem, and the spec is silent.
- Note-on velocity 0x01 (MCU "flash") is treated as on: the spec defines on/off only, and nothing shows Logic flashing these LEDs.
- After a rebind, continuous LCD/ring changes during automated playback could delay `ready`: the spec defines ready purely as display-quiet, and this affects startup only.
- The virtual port vanishing mid-command: we own the port, so only a CoreMIDI server restart could remove it. This is outside the spec, and the resulting timeouts would surface it anyway.
- Name addressing, Send/EQ/Plug-in modes and Flip control: explicitly scoped to spec 2/3.
- What meter values mean in dB: a spec §8 non-goal.
- Reducer cost on the meter hot path: negligible (one tuple rebuild per message), with no measured problem.
- Security: stdio only, no network surface, and `pgrep` runs with fixed arguments. Nothing further to assess.
- Fixture and `uv.lock` contents: excluded from the review package by the caller.

## Recommendations

1. Fix I1–I3. Each is small (≤30 lines) and needs one or two new tests. Order: I2 (2 lines), then I1 (1 line), then I3.
2. Correct the doc and spec bank map (I4), then run plan Step 6 on a project with 9 or more tracks before merging. Include rewind/fast_forward in the same session (M13).
3. Take M3 (destructive_hint=False), M4 (refuse on FLIP) and M5 (rounding) in the same pass. They are one-liners.
4. Leave M1, M8, M9 and M12 as post-merge follow-ups, and update spec §3 to describe the threading as built.

## Assessment

**Ready to merge: With fixes.** The architecture, the protocol work and the fixture-based tests are solid, and the core commands were verified on real hardware. Before this becomes the daily driver, three things must change: re-handshakes currently skip the install guard (I1), the -72…-119 dB band silently goes to -inf (I2), and configure can change the user's project (I3). The bank map also needs one live check (I4).
