[한국어 (Korean)](CHANGELOG.ko.md) / [English](CHANGELOG.md)

# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
