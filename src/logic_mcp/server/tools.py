"""MCP 툴. 입력 검증과 Commands 호출만 한다."""
from __future__ import annotations

import math
from typing import Annotated, Literal

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from ..logic.commands import Commands, ToolResult

Strip = Annotated[int | None, Field(ge=1, le=8, description="Strip 1-8 in the current bank. Give either this or number, not both")]
Number = Annotated[int | None, Field(ge=1, description="Logic channel number shown on the LCD (absolute address). Give either this or strip, not both")]
Slot = Annotated[int | None, Field(ge=1, le=8, description="Insert slot 1-8 (the slots reachable in the Plug-in Channel view)")]


def register_tools(mcp: MCPServer, commands: Commands) -> None:
    @mcp.tool(name="logic_transport", annotations=ToolAnnotations(idempotent_hint=True),
              description="Play, stop, record, cycle, rewind, fast-forward. Verified via the LEDs and the time display.")
    def logic_transport(
        action: Literal["play", "stop", "record", "cycle_on", "cycle_off", "rewind", "fast_forward"],
    ) -> ToolResult:
        return commands.transport(action)

    @mcp.tool(name="logic_track", annotations=ToolAnnotations(idempotent_hint=True),
              description="Track mute, solo, record-arm, and select. If the track is already in that state, nothing is sent (skipped).")
    def logic_track(
        action: Literal["mute", "unmute", "solo", "unsolo", "arm", "disarm", "select"],
        strip: Strip = None,
        number: Number = None,
    ) -> ToolResult:
        return commands.track(action, strip=strip, number=number)

    @mcp.tool(name="logic_mixer", annotations=ToolAnnotations(idempotent_hint=True),
              description="Volume (dB, -inf..+6.0) and pan (-64..63). Pan works only while the V-Pot is in PAN mode.")
    def logic_mixer(
        action: Literal["set_volume", "set_pan"],
        strip: Strip = None,
        number: Number = None,
        db: Annotated[float | Literal["-inf"] | None, Field(description="set_volume: dB. The string \"-inf\" is allowed")] = None,
        pan: Annotated[int | None, Field(ge=-64, le=63, description="set_pan: -64(L)..63(R)")] = None,
    ) -> ToolResult:
        if action == "set_volume":
            if db is None:
                return ToolResult(ok=False, verified="skipped", action=action, note="set_volume에는 db가 필요. 예: -6.0, 0, \"-inf\"")
            value = -math.inf if db == "-inf" else float(db)
            return commands.mixer_volume(strip, number, value)
        if pan is None:
            return ToolResult(ok=False, verified="skipped", action=action, note="set_pan에는 pan(-64..63)이 필요")
        return commands.mixer_pan(strip, number, pan)

    @mcp.tool(name="logic_bank",
              description="Move the 8-strip bank. show navigates to the bank in which number is visible.")
    def logic_bank(
        action: Literal["left", "right", "channel_left", "channel_right", "first", "last", "show"],
        number: Number = None,
    ) -> ToolResult:
        return commands.bank(action, number=number)

    @mcp.tool(name="logic_session",
              description="status: connection state. wait_ready: wait until Logic installs the surface. configure: set number display, value mode, and Beats clock correction (once at first).")
    def logic_session(
        action: Literal["status", "wait_ready", "configure"],
        timeout_s: Annotated[float, Field(gt=0, le=120)] = 10.0,
    ) -> ToolResult:
        if action == "status":
            return ToolResult(ok=True, verified="skipped", action=action, after=commands.status())
        if action == "wait_ready":
            return commands.wait_ready(timeout_s)
        return commands.configure()

    @mcp.tool(name="logic_eq", annotations=ToolAnnotations(idempotent_hint=True),
              description="Channel EQ. get: all 8 bands (has_eq=false if there is no EQ; nothing is inserted). "
                          "set: band 1-8, param freq|gain|slope|q|on, value. Bands 1 and 8 take slope (6/12/18/24/36/48) instead of gain. "
                          "If there is no EQ, a Channel EQ is inserted only when allow_insert=true. Returns to PAN mode when done.")
    def logic_eq(
        action: Literal["get", "set"],
        strip: Strip = None,
        number: Number = None,
        band: Annotated[int | None, Field(ge=1, le=8)] = None,
        param: Literal["freq", "gain", "slope", "q", "on"] | None = None,
        value: Annotated[float | bool | None, Field(description="freq Hz, gain dB, slope 6..48, q number, on boolean")] = None,
        allow_insert: bool = True,
    ) -> ToolResult:
        if action == "get":
            return commands.eq.get(strip, number)
        if band is None or param is None or value is None:
            return ToolResult(ok=False, verified="skipped", action="eq_set", note="set에는 band, param, value가 필요")
        return commands.eq.set(strip, number, band, param, value, allow_insert)

    @mcp.tool(name="logic_plugin",
              description="Insert plug-ins. list: inventory (the whole bank if no strip/number). params: all plug-in parameters (index, short name, value). "
                          "get/set: param is a name (partial match) or an index, value is a number or option text. insert: plugin name (partial match), "
                          "replace=true is required if the slot is occupied; if the cached list position shows another plug-in (or the name is not in the list), "
                          "the insert menu is scanned by name, which can take up to ~2-3 minutes. remove. bypass(on). scan: scan the whole insert menu (60-180 s, nothing is inserted, needs an empty slot). "
                          "Aux strips (no track): only slot 1 insert/remove, via the Plug-in Mixer view. "
                          "move: remove + reinsert into an empty slot (to_slot); plug-in settings are reset. "
                          "Logic opens and closes the plug-in window when the edit view is entered. Returns to PAN mode when done. "
                          "calibrate: collect the full parameter table of the plug-in in the slot and save it to the user cache (2-20 min; values are not restored, so force=true is required).")
    def logic_plugin(
        action: Literal["list", "params", "get", "set", "insert", "remove", "bypass", "scan", "calibrate", "move"],
        strip: Strip = None,
        number: Number = None,
        slot: Slot = None,
        to_slot: Annotated[int | None, Field(ge=1, le=8, description="move: destination slot 1-8, must be empty")] = None,
        param: Annotated[str | int | None, Field(description="Parameter name (partial match) or 1-based index. Use the index exactly as given in the params result (numbers can skip on the last page)")] = None,
        value: Annotated[float | str | bool | None, Field(description="set: a number or option text (e.g. \"On\")")] = None,
        plugin: Annotated[str | None, Field(description="insert: plug-in name (partial match)")] = None,
        replace: bool = False,
        on: Annotated[bool | None, Field(description="bypass: true = bypassed")] = None,
        tolerance: Annotated[float | None, Field(gt=0, description="set: tolerance (default 0.2 for dB, 2% otherwise)")] = None,
        force: bool = False,
    ) -> ToolResult:
        name = f"plugin_{action}"
        if action == "scan":
            return commands.plugin.scan(force)
        if action == "list":
            return commands.plugin.list(strip, number)
        if slot is None:
            return ToolResult(ok=False, verified="skipped", action=name, note="slot(1-8)이 필요")
        if action == "calibrate":
            if not force:
                return ToolResult(ok=False, verified="skipped", action=name,
                                  note="calibrate는 파라미터 값을 되돌리지 않고 움직인다. 테스트 프로젝트에서 force=true로 실행")
            return commands.plugin.calibrate(strip, number, slot)
        if action == "params":
            return commands.plugin.params(strip, number, slot)
        if action == "get":
            if param is None:
                return ToolResult(ok=False, verified="skipped", action=name, note="get에는 param(이름 또는 인덱스)이 필요")
            return commands.plugin.get(strip, number, slot, param)
        if action == "set":
            if param is None or value is None:
                return ToolResult(ok=False, verified="skipped", action=name, note="set에는 param과 value가 필요")
            return commands.plugin.set(strip, number, slot, param, value, tolerance)
        if action == "insert":
            if not plugin:
                return ToolResult(ok=False, verified="skipped", action=name, note="insert에는 plugin 이름이 필요")
            return commands.plugin.insert(strip, number, slot, plugin, replace)
        if action == "remove":
            return commands.plugin.remove(strip, number, slot)
        if action == "move":
            if to_slot is None:
                return ToolResult(ok=False, verified="skipped", action=name, note="move에는 to_slot(1-8)이 필요")
            return commands.plugin.move(strip, number, slot, to_slot)
        if on is None:
            return ToolResult(ok=False, verified="skipped", action=name, note="bypass에는 on(true/false)이 필요")
        return commands.plugin.bypass(strip, number, slot, on)

    @mcp.tool(name="logic_send", annotations=ToolAnnotations(idempotent_hint=True),
              description="Sends 1-8. get: all 8 (destination bus, level dB, position, mute). set_dest: dest is a bus number (\"Bus 3\", \"3\", 3) or "
                          "\"--\" (remove). set_level: db (-inf..+6.0). set_pos: pre|post|post_pan. mute: on. remove. Creating a new bus send makes "
                          "Logic auto-create an Aux track, so the numbers of later tracks may shift. Output, Master, and Aux strips are not supported (skipped; for Aux strips this is a precaution, "
                          "since the Send Channel view is assumed not to follow them). "
                          "Returns to PAN mode when done.")
    def logic_send(
        action: Literal["get", "set_dest", "set_level", "set_pos", "mute", "remove"],
        strip: Strip = None,
        number: Number = None,
        send: Annotated[int | None, Field(ge=1, le=8, description="Send 1-8")] = None,
        dest: Annotated[str | int | None, Field(description="set_dest: \"Bus 3\", \"3\", 3, or \"--\"")] = None,
        db: Annotated[float | Literal["-inf"] | None, Field(description="set_level: dB. The string \"-inf\" is allowed")] = None,
        pos: Literal["pre", "post", "post_pan"] | None = None,
        on: Annotated[bool | None, Field(description="mute: true = muted")] = None,
    ) -> ToolResult:
        name = f"send_{action}"
        if action == "get":
            return commands.send.get(strip, number)
        if send is None:
            return ToolResult(ok=False, verified="skipped", action=name, note="send(1-8)가 필요")
        if action == "set_dest":
            if dest is None:
                return ToolResult(ok=False, verified="skipped", action=name, note="set_dest에는 dest가 필요(버스 번호 또는 \"--\")")
            return commands.send.set_dest(strip, number, send, dest)
        if action == "remove":
            return commands.send.remove(strip, number, send)
        if action == "set_level":
            if db is None:
                return ToolResult(ok=False, verified="skipped", action=name, note="set_level에는 db가 필요. 예: -6.0, 0, \"-inf\"")
            return commands.send.set_level(strip, number, send, -math.inf if db == "-inf" else float(db))
        if action == "set_pos":
            if pos is None:
                return ToolResult(ok=False, verified="skipped", action=name, note="set_pos에는 pos(pre|post|post_pan)가 필요")
            return commands.send.set_pos(strip, number, send, pos)
        if on is None:
            return ToolResult(ok=False, verified="skipped", action=name, note="mute에는 on(true/false)이 필요")
        return commands.send.mute(strip, number, send, on)
