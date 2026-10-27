[한국어 (Korean)](CHANGELOG.ko.md) / [English](CHANGELOG.md)

# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]
### Added
- `logic_plugin` `move`: moves a plug-in to an empty slot (`to_slot`) by removing it and inserting it again. MCU has no move command, so the plug-in's settings are reset. If the reinsert fails after the remove, the result is unverified and names the plug-in so you can insert it again.
- `logic_plugin` `insert` falls back to scanning the insert menu by name when the cached list position shows a different plug-in (the menu order differs between projects). A name that is not in the cached list is looked up by prefix (`note` is `name_scan:<ticks>`). Nothing is confirmed unless the overlay shows the requested name.
- Aux strips (no track) are detected from the TRACK hold menu Input column (`Bus n`). The Plug-in Channel view does not follow Aux strips (observed); the Send Channel and EQ Channel views are assumed not to follow them either (assumed, not measured). Plug-in, send, and EQ commands on Aux strips are therefore skipped instead of changing the previously selected track. Plug-in slot 1 can still be inserted into and removed from an Aux strip through the Plug-in Mixer view, and `list` reports slot 1 only for Aux strips (`aux` in the result).
- Plug-in commands check that the edit view header shows the target strip's track number (`Track <n>`), so a strip whose channel view shows another track is not changed silently, even if it was not detected as Aux.

### Changed
- Default `set` tolerances are wider: 0.2 dB (was 0.1) and 2 % for other values with a unit (was 1 %). Numeric sets now try up to 10 correction rounds (was 6). An explicit `tolerance` still wins.
- A learned LCD abbreviation is kept only if it is a subsequence of the plug-in name (ignoring spaces, `-`, `.`, `/`, `*` and case), so a reveal that showed a neighbouring menu item (`Tuner` → "Channel EQ") is no longer learned; mismatched entries already in the user cache file are dropped on load.

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
