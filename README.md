# logic-mcp

[한국어 (Korean)](README.ko.md)

An MCP server that lets Claude Code operate Logic Pro. It emulates the Mackie Control (MCU) protocol, which Logic officially supports, over a CoreMIDI virtual port, and verifies every command against the LED, fader and LCD feedback that Logic sends back to the surface. It does not click on the screen or use accessibility APIs. Only MIDI goes back and forth.

## Quick start

1. Add the server to Claude Code (other clients: see [Installation](#installation-macos-logic-pro-1112)).

   ```
   claude mcp add logic -- uvx --python 3.12 --from git+https://github.com/Imtylerrrrrr/logic-mcp logic-mcp
   ```

2. Open a project in Logic. Use a throwaway copy the first time: changes go straight into the open project, and the server never saves it.
3. Tell Claude "set up the Logic connection" once (it runs `logic_session configure`), then ask for what you want.

## What to ask

You don't need to know the plug-in names. Describe the sound:

- *"I recorded myself singing on track 1. Make it sound like a finished pop vocal."*
- *"Put that obvious autotune on the vocal. The song is in D major."*
- *"The guitar sounds boxed in. Make it wide and clean."*

If you know the terms, be as specific as you like:

- *"Track 2: gate, light compression, an amp, a touch of delay, and a big reverb on a bus."*
- *"Set track 1 Channel EQ band 3 to 1 kHz, +3 dB."*

## What to expect

- A big request turns into a dozen small steps, each a few seconds: Claude moves a fader or knob on a virtual control surface, then waits for Logic's own display to show the new value before it moves on. A whole tone takes a few minutes.
- Every answer carries `verified`, `skipped` (already in that state) or `unverified` (sent, but Logic did not confirm). An `unverified` reply says why.
- Tracks are the 8 in the current bank of the virtual surface. "Track 3" means the third strip; "track number 12" means Logic's own number in the track header. Claude moves the bank when it has to.

## What it can do

- Transport: play, stop, record, cycle, rewind, fast-forward
- Tracks: select, mute, solo, record-arm
- Mixer: volume (dB, -∞ to +6.0), pan (-64 to 63), 8-strip bank navigation
- Channel EQ: read and write frequency, gain, Q, slope and on/off for all 8 bands
- Insert plugins: list, insert, remove and bypass for slots 1-8, read and write parameters, scan the insert menu
- Sends: read, write and remove destination (bus), level (dB), position (Pre/Post/Post Pan) and mute for sends 1-8

How it works: the server opens a virtual MIDI port named "LogicMCP", and Logic installs it automatically as a Mackie Control. The server sends button, V-Pot and fader messages, and reconstructs state from the LCD (2×56 characters), LEDs and fader positions that Logic sends back. Every tool result is tagged with one of `verified` (confirmed by feedback), `skipped` (already in that state, nothing sent), `unverified` (sent but could not be confirmed) or `timeout` (no response). It never claims success on a guess.

## Requirements

- macOS, Logic Pro 11 or 12 (measured on 12.0.1)
- Python 3.12 (python-rtmidi ships macOS wheels up to 3.12; 3.13 and later need a source build with the Xcode Command Line Tools), [uv](https://docs.astral.sh/uv/)
- An MCP client (Claude Code, Claude Desktop, etc.)

## Installation (macOS, Logic Pro 11/12)

### A. Claude Code

```
claude mcp add logic -- uvx --python 3.12 --from git+https://github.com/Imtylerrrrrr/logic-mcp logic-mcp
```

Optional (Claude Code only): copy the skill that covers the order of operations and the pitfalls of the EQ, plugin and send commands.

```
git clone https://github.com/Imtylerrrrrr/logic-mcp.git && cp -R logic-mcp/skills/logic-plugins ~/.claude/skills/
```

### B. Claude Desktop

Add this to `~/Library/Application Support/Claude/claude_desktop_config.json`. Use the absolute path from `which uvx` for `command` (apps launched from Finder have a short PATH).

```json
{"mcpServers": {"logic": {"command": "/Users/<user>/.local/bin/uvx",
  "args": ["--python", "3.12", "--from", "git+https://github.com/Imtylerrrrrr/logic-mcp", "logic-mcp"]}}}
```

(`<user>` is your macOS user name.)

### C. Development

1. Clone and install dependencies: `git clone https://github.com/Imtylerrrrrr/logic-mcp.git && cd logic-mcp && uv sync`
2. Add a `.mcp.json` to your Claude Code project (change the path in `.mcp.json.example` to where you cloned the repo)

### Common

When you open a project in Logic, the "LogicMCP" port is installed automatically as a Mackie Control. Call `logic_session configure` once the first time (track number display, value display mode, Beats clock).

## Tools

| Tool | Description |
|---|---|
| `logic_transport` | Play, stop, record, cycle, rewind, fast-forward |
| `logic_track` | Select, mute, solo, record-arm tracks |
| `logic_mixer` | Volume (dB), pan |
| `logic_bank` | Move banks and channels, find the bank that shows a given track number |
| `logic_session` | Connection status, wait for surface installation, configure |
| `logic_eq` | Read and write frequency, gain, Q, slope and on/off for all 8 Channel EQ bands |
| `logic_plugin` | List, insert, remove and bypass for insert slots 1-8, read and write parameters, plugin scan, parameter table collection (calibrate, requires force) |
| `logic_send` | Read and write destination (bus), level, position and mute for sends 1-8 |

Resources: `logic://status`, `logic://transport`, `logic://strips`, `logic://lcd`, `logic://plugins`, `logic://inserts`, `logic://view`.

Calling a tool directly looks like this. A track is addressed by either `strip` (1-8 in the current bank) or `number` (the Logic track number shown on the LCD).

```json
logic_mixer {"action": "set_volume", "strip": 3, "db": -6.0}
→ {"ok": true, "verified": "verified", "action": "set_volume",
   "target": {...}, "before": {...}, "after": {...}, "elapsed_ms": 176, "note": ""}
```

If `ok` is false, or `verified` is `unverified` or `timeout`, `note` holds the reason (Flip is on, no LCD change, etc.).

Only insert slots 1-8 and sends 1-8 are supported. The output (Stereo Out) and Master strips do not accept EQ channel, plugin or send commands (Logic's channel view does not follow those strips; see Z4 in [docs/mcu-protocol.md](docs/mcu-protocol.md) (Korean)).

The plugin list consists of the bundle (built into Logic 12.0.1) plus `logic_plugin scan` (user cache `~/.logic-mcp/plugins-<version>.json`). The bundled parameter tables are built with `uv run python scripts/calibrate_plugin.py "<plugin>" [strip] --write` (in a test project).

Side effects: EQ, plugin and send commands change Logic's track selection; if a track has no Channel EQ, the EQ command inserts one automatically; and a plugin window may open. Creating a new bus send makes Logic automatically create an Aux track, which shifts the numbers of the tracks after it.

## Status

| Feature | Verified on real Logic 12.0.1 |
|---|---|
| Transport, tracks, mixer, banks | Done |
| Channel EQ, insert plugins | Done (live round 9, 17/17) |
| Output and Master strip guard | Done (live round 10, skipped on the Stereo Out strip) |
| Sends (`logic_send`) | Done (live round 10, 9/9) |
| Bundled plugin parameter tables | 67 plugins, every entry of the Logic 12.0.1 insert menu as seen over MCU (collected live 10/19-11/11, two-column tables recollected 11/11; 1,040 parameters, 96 without a map). Parameters without a map are probed when written. Most map-less parameters are action parameters, minimum values such as Mute, and unit changes (Space Designer 22, ChromaVerb 11) |
| Calibration and scan correction (10/19) | Done (the 163 one-tick scan results matched the diagnosis, 0 enum misjudgments in the re-collected tables; search near the insert is unverified) |

## Cautions

- Changes are applied directly to your Logic project. Try it first on a test project you can throw away. The server does not save the project.
- If assignment buttons such as EQ and Plugin stop responding after you restart Logic, follow 1-4 of [Troubleshooting](docs/troubleshooting.md) (delete and reconnect the Mackie Control device).
- Creating a new bus send makes Logic create an Aux track and shifts the numbers of the tracks behind it. Afterwards, check the numbers again with `logic_bank show` or `plugin list`.
- `logic_plugin calibrate` and `scripts/calibrate_plugin.py` insert a plugin into the open project, move its values, and do not put them back. Use them only in a test project and do not save.
- It does not touch any other control surface you already use. This server opens only its own port, "LogicMCP".
- What the server touches: it talks to the MCP client over stdio and makes no network connections, and it asks for no macOS privacy permissions (Accessibility, Screen Recording, Automation). It writes only to `~/.logic-mcp/` (the plug-in cache), reads Logic's `Info.plist` for the version, and runs one external command, `pgrep`, to see whether Logic is running. It has three dependencies: `mcp`, `python-rtmidi`, `pydantic`.
- To remove it: run `claude mcp remove logic` (or delete the entry from the Claude Desktop config), delete the Mackie Control device that uses the LogicMCP port in Logic Pro > Settings > Control Surfaces > Setup…, and delete `~/.logic-mcp/`.

If something goes wrong, work through [docs/troubleshooting.md](docs/troubleshooting.md) from top to bottom. To report a security problem, see [SECURITY.md](SECURITY.md).

## Development

- Unit tests: `uv run pytest` (no real Logic needed, 295 tests against a fake Logic model)
- Check Python 3.12: `uv run --isolated -p 3.12 pytest -q`
- stdio smoke test (starts the server and only exchanges initialize, no Logic needed): `uv run python scripts/smoke_stdio.py`
- Build the distribution files: `uv build`
- Live verification (with a test project open in Logic): `uv run python scripts/live_check.py` (transport, tracks, mixer), `uv run python scripts/live_check2.py [strip] [--scan]` (EQ, plugins, sends)
- `scripts/calibrate_plugin.py "<plugin>" [strip] [--write] [--yes]` collects plugin parameter tables (with `--write`, merges them into the bundled `known.json`)
- `scripts/capture.py` captures MCU traffic, `scripts/calibrate_fader.py` generates the fader dB table
- Docs: design `docs/superpowers/specs/`, implementation plans `docs/superpowers/plans/`, measured protocol notes `docs/mcu-protocol.md`, progress log `docs/progress.md`, reviews `docs/reviews/`

Internal engineering notes (protocol measurements, progress log, specs, plans, reviews) are kept in Korean.

## License

[MIT](LICENSE). Logic Pro is a trademark of Apple Inc. and Mackie Control is a trademark of LOUD Technologies. This project is not affiliated with either company.
