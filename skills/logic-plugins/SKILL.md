---
name: logic-plugins
description: Order of operations and pitfalls when using Logic Pro MCP (logic-mcp) for Channel EQ, insert plug-ins, and sends. Read before using logic_eq, logic_plugin, or logic_send.
---

[한국어 (Korean)](SKILL.ko.md) / [English](SKILL.md)

# Operating Logic Pro plug-ins, EQ, and sends (logic-mcp)

## Getting started
1. `logic_session wait_ready` → `logic_session configure` (once at first; once more after Logic reinstalls the surface).
2. Read the `logic://plugins` resource. If `scanned_at` is missing or `logic_version` differs, suggest `logic_plugin scan` (60-180 s, needs one empty slot; the slot on screen flickers but nothing is inserted).

## Plug-ins
- If `insert` says "not in the list", run `scan` and try again. A filled slot is replaced only with `replace=true`.
- Read `params` first, then `get`/`set` by `short` (abbreviated name) or `index`. The last page may skip indexes, so use the index that params gave you as is.
- If a third-party plug-in gives only unnamed `Control #N` (0-1000), address it by index; values are integers 0-1000.
- Insert slots are 1-8 only.

## EQ
- `logic_eq get` does not insert anything. `set` inserts a Channel EQ if there is none, depending on `allow_insert` (default true). Bands 1 and 8 take slope (6/12/18/24/36/48) instead of gain.

## Sends
- The dest of `logic_send set_dest` is a bus number ("Bus 3", "3", 3) or "--" (remove). Creating a new bus send makes Logic auto-create an Aux track, so **the numbers of later tracks shift** → re-read `logic://strips` before addressing tracks by number again.
- Level is in dB (-inf..+6.0), position is pre|post|post_pan, mute is on. Level, position, and mute on a number with no send are skipped.

## Not supported
- Output (Stereo Out) and Master strips: EQ channel, plug-in, and send commands are `skipped` (Logic's channel view does not follow those strips, so the wrong track would be changed). `eq get` only reports whether an EQ exists.
- Insert slots 9-15, instrument and MIDI FX slots, surround, and send destinations that are not buses.

## Safety
- Every command returns to PAN mode with Flip off when it finishes. If the result is not `verified`, do not trust it; read the `note`.
- The spec 1 tools (`logic_track` mute/solo/select, `logic_transport`, `logic_bank`) are safe even during the assignment view. `logic_mixer` set_volume and set_pan return to PAN by themselves before running.
- If, after Logic is relaunched, every EQ, plug-in, and send command is `unverified` ("button not responding"), tell the user to **delete the Mackie Control device** in Logic Pro > Settings > Control Surfaces > Setup… (Logic Pro → 설정 → 컨트롤 서피스 → 설정…) and reconnect (do not touch other devices such as the MPK, and do not press "Rebuild Defaults" (기본값 재형성)).
