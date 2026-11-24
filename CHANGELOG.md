[한국어 (Korean)](CHANGELOG.ko.md) / [English](CHANGELOG.md)

# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]
### Added
- Bundled parameter tables for all 67 plug-ins in the Logic 12.0.1 insert menu (was 10): every entry of the menu as it appears over MCU now has a table, 1,064 parameters in total. Space Designer and EVOC 20 Filterbank have the largest tables (178 and 61 parameters).
- `SECURITY.md` (how to report a vulnerability, what the server touches), a Dependabot configuration for the Python dependencies and the GitHub Actions, and a manual `publish` workflow that uploads to PyPI with trusted publishing. The README Cautions section now states what the server touches and how to remove it.
- `scripts/calibrate_batch.sh [strip] "Name" ...` runs `calibrate_plugin.py --write --yes` for several plug-ins in a row, skips names already in the bundle, and writes one log per plug-in to `~/.logic-mcp/calib-logs/`.

### Changed
- Numeric `set` now settles on the nearer step and returns ok when the target lies between two control-surface steps. It used to spend 10 rounds bouncing between them and fail, e.g. Compressor Release 300 between 290 and 310. `note` names both steps.
- Internal refactor, no behaviour change: the Aux Plug-in Mixer path moved to `plugin_mixer.py`, `calibrate`/`scan` to `plugins/calibrate.py`, and the shared set logic (numeric-vs-option decision, `#n`/option selection, result verdict) to `setter.py`, used by both `logic_plugin set` and `logic_eq set`.

### Fixed
- `logic_plugin` `get`/`set` could act on the same column of another page when Logic handled a Cursor ◀/▶ press seconds late (up to 3.8 s measured): a Compressor Release change went to Distortion on the next page. The page-count probe now waits 3 s longer for an unanswered press and fails instead of assuming one page when the table has more, a page move is counted only when the page token or the value row changes, and before every fader move or V-Pot tick the short names on the LCD are compared with the table for the expected page. On a mismatch nothing is sent and the note starts with `guard:`. Instances laid out differently from the bundled table are refused for the same reason: on stereo instances 15 of 66 plug-ins show their parameter set twice or have separate left/right parameters (PlatinumVerb `Dry`/`Wet`, for example). Such parameters used to be written to whatever sat at the table's position. See `docs/troubleshooting.md` item 7.
- Values in the last LCD column were misread while their overlay was showing. The overlay is right-aligned there and spills into column 7 when it is longer than 6 characters, so `-24.0 dB` was read as `4.0 dB`. A `set` could report `verified` on the wrong value (Compressor side-chain `Gain` 3 ended at 23 dB) and calibration learned wrong ranges for such parameters. The spilled text is now read whole. The bundled ranges of last-column parameters were re-measured on Logic 12.0.1: 14 wrong ranges corrected (Compressor `Gain` 0–4 → −24–24 dB, several frequencies `20–0` → 20–20000 Hz, Tape Delay `Delay Time` 0.3–9.9 → 0.3–4999.9 ms) and 16 missing ones filled in, across 16 plug-ins.
- Opening a plug-in right after working on a later page of a longer one failed with `empty_edit` although the slot was filled (Chorus after Compressor page 3). Logic opens the edit view at the previous page position, and a shorter plug-in shows the empty-slot screen there. The server now presses Cursor ◀ once to land on the plug-in's last page.
- Legacy plug-ins that draw one parameter across two LCD columns (Silver Compressor `Threshold`, Parametric EQ `Frequency`, 14 plug-ins in all) are read as one parameter: the name and the value are joined when they fill their column. Previously the second column became a ghost parameter (`ld`, `cy`) and the name was cut. The 14 bundled tables were recollected. Known limitation: a two-column *value* is still read one column wide when a parameter is set or probed, so the `Frequency` of Parametric EQ, Exciter, Low Pass Filter and High Pass Filter has no range map and cannot be set numerically yet.
- Ratio values such as `2.0  :1` (two spaces before the unit) are read as numbers, so Silver Compressor Ratio can be set.
- A numeric `set` whose target is outside the calibrated range (GoldVerb Room Size 1500 with a 10–200 m map) is skipped with the range in the note instead of moving the fader to the end and reporting no LCD response.
- `logic_plugin set` accepts 0/1 for a parameter whose options are exactly Off/On (previously "1" never matched).
- When an option text is not found within 16 steps, the parameter is stepped back to where it started and the note says so (previously it was left wherever the search stopped).
- `logic_plugin` `insert` accepts a plug-in whose cached list name was cut to the 21-character overlay (`EVOC 20 TrackOscillat`) when the edit view header shows the full name, and reports the full name. Previously the insert was reported unverified although the plug-in was in the slot.

## [0.1.2] - 2026-11-02
### Added
- `logic_plugin` `move`: moves a plug-in to an empty slot (`to_slot`) by removing it and inserting it again. MCU has no move command, so the plug-in's settings are reset. If the reinsert fails after the remove, the result is unverified and names the plug-in so you can insert it again.
- `logic_plugin` `insert` falls back to scanning the insert menu by name when the cached list position shows a different plug-in (the menu order differs between projects). A name that is not in the cached list is looked up by prefix (`note` is `name_scan:<ticks>`). Nothing is confirmed unless the overlay shows the requested name.
- Aux strips (no track) are detected from the TRACK hold menu Input column (`Bus n`). The Plug-in Channel view does not follow Aux strips (observed); the Send Channel and EQ Channel views are assumed not to follow them either (assumed, not measured). Plug-in, send, and EQ commands on Aux strips are therefore skipped instead of changing the previously selected track. Plug-in slot 1 can still be inserted into and removed from an Aux strip through the Plug-in Mixer view, and `list` reports slot 1 only for Aux strips (`aux` in the result).
- Plug-in commands check that the edit view header shows the target strip's track number (`Track <n>`), so a strip whose channel view shows another track is not changed silently, even if it was not detected as Aux.
- `logic_plugin` `set` accepts `"#n"` for an option parameter to pick the n-th option (1-based): it turns to the first option, then n-1 steps forward. An option text that several options share in the 6-character LCD cell is skipped and the note lists their numbers. Without a calibrated option table, `#n` still moves but the result is unverified and only reports the text it landed on. `#n` on a numeric parameter is skipped. A unique option name moves only the difference from the current option when that option is unique in the table (no rewind; `already` still works).

### Changed
- Default `set` tolerances are wider: 0.2 dB (was 0.1) and 2 % for other values with a unit (was 1 %). Numeric sets now try up to 10 correction rounds (was 6). An explicit `tolerance` still wins.
- A learned LCD abbreviation is kept only if it is a subsequence of the plug-in name (ignoring spaces, `-`, `.`, `/`, `*` and case), so a reveal that showed a neighbouring menu item (`Tuner` → "Channel EQ") is no longer learned; mismatched entries already in the user cache file are dropped on load.

### Fixed
- Range probing accepts a unit cut off by the 6-character LCD cell (Compressor Release `5.0 ms` … `5000.0`) and infers a log mapping when both ends are positive and more than 100× apart, so Compressor Release can be set.
- `calibrate` collects option lists with fixed tick counts instead of stopping when the text repeats, so options that share an abbreviated text are all kept in order. Identical texts at the very end of a list are still merged into one. Each option parameter now takes about 30 s longer to calibrate.
- Selecting an option by name waits out Logic's value overlay (about 2 s after each step) before reading. Previously it could read the overlay text (`Vintage` over `VinOpt`), take it for the end of the list, and miss the option.
- The bundled tables for Compressor, Noise Gate and Stereo Delay were recollected: Release and the Stereo Delay times have correct maps again (the old ones were calibrated wrongly), and Compressor Circuit Type lists all 7 options.

## [0.1.1] - 2026-10-22
### Changed
- English is now the base language: README, troubleshooting guide, changelog, the `logic-plugins` skill, MCP tool descriptions and server instructions are in English. Korean versions live in `*.ko.md` files, cross-linked at the top.
- Quick start examples in the README are in English.

## [0.1.0] - 2026-10-22

### Added
- 8 tools: transport, track, mixer, bank (`logic_transport`, `logic_track`, `logic_mixer`, `logic_bank`, `logic_session`)
- Channel EQ (`logic_eq`): read and write frequency, gain, Q, slope, and on/off for 8 bands
- Insert plug-ins (`logic_plugin`): list, insert, remove, bypass, read and write parameters, scan, calibrate
- Sends (`logic_send`): read and write destination, level, position, and mute; remove
- Bundled parameter tables: 10 plug-ins, 357 parameters (measured on Logic Pro 12.0.1)
- Server instructions (clients receive the startup sequence)
- Troubleshooting guide `docs/troubleshooting.md`
- Python 3.12 support, stdio smoke script `scripts/smoke_stdio.py`, test workflow

## Release procedure (notes)

`uv build` → `gh release create v0.1.0 dist/*`. PyPI is not used (do not run `uv publish`).
