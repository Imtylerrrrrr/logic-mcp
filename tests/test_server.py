import json

import pytest
from mcp import Client

from logic_mcp.logic.commands import Commands
from logic_mcp.logic.faders import FaderTable
from logic_mcp.logic.plugins.cache import PluginCache
from logic_mcp.mcu import protocol as P
from logic_mcp.server.app import create_server
from tests.fake_assign import PLUGIN_LIST, make_assign_logic
from tests.fakes import make_surface
from tests.test_commands import LCD_NUMBERED, echo_led


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def setup():
    surface, fake = make_surface()
    cmds = Commands(surface, FaderTable.load(), sleep=lambda s: None, logic_running=lambda: True)
    fake.feed(LCD_NUMBERED)
    fake.feed(P.button_down(P.Note.PAN))
    surface.tick()
    echo_led(fake)
    mcp = create_server(cmds, start_surface=False)
    return mcp, fake


@pytest.mark.anyio
async def test_tool_list_and_names(setup):
    mcp, fake = setup
    async with Client(mcp, raise_exceptions=True) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools.tools}
        assert names == {"logic_transport", "logic_track", "logic_mixer", "logic_bank", "logic_session", "logic_eq", "logic_plugin", "logic_send"}
        track = next(t for t in tools.tools if t.name == "logic_track")
        assert set(track.input_schema["properties"]) == {"action", "strip", "number"}
        assert "mute" in track.input_schema["properties"]["action"]["enum"]


@pytest.mark.anyio
async def test_mute_call_returns_structured_result(setup):
    mcp, fake = setup
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("logic_track", {"action": "mute", "strip": 1})
        sc = result.structured_content
        assert sc["ok"] is True and sc["verified"] == "verified"
        assert sc["after"]["mute"] is True
        assert fake.sent[0] == P.button_down(P.Note.MUTE)


@pytest.mark.anyio
async def test_session_status_and_resources(setup):
    mcp, fake = setup
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("logic_session", {"action": "status"})
        assert result.structured_content["after"]["state"] == "ready"
        res = await client.list_resources()
        uris = {str(r.uri) for r in res.resources}
        assert {"logic://status", "logic://transport", "logic://strips", "logic://lcd"} <= uris
        strips = await client.read_resource("logic://strips")
        data = json.loads(strips.contents[0].text)
        assert data["strips"][0]["number"] == 1 and len(data["strips"]) == 8
        lcd = json.loads((await client.read_resource("logic://lcd")).contents[0].text)
        assert lcd["row1"].startswith("1:1")
        tr = json.loads((await client.read_resource("logic://transport")).contents[0].text)
        assert "play" in tr and "time" in tr


@pytest.mark.anyio
async def test_mixer_db_accepts_minus_inf_string(setup):
    mcp, fake = setup
    async with Client(mcp, raise_exceptions=True) as client:
        fake.replies = lambda d: [bytes([0xE0, 0, 0])] if d[0] & 0xF0 == 0xE0 else []
        result = await client.call_tool("logic_mixer", {"action": "set_volume", "strip": 1, "db": "-inf"})
        assert result.structured_content["ok"] is True
        result = await client.call_tool("logic_mixer", {"action": "set_pan", "strip": 1})
        assert result.structured_content["ok"] is False and "pan" in result.structured_content["note"]


@pytest.fixture
def assign_setup(tmp_path):
    surface, fake, logic = make_assign_logic()
    cache = PluginCache("fake", list(PLUGIN_LIST), [], {}, {}, None, tmp_path / "plugins-fake.json")
    cmds = Commands(surface, FaderTable.load(), sleep=logic.sleep, logic_running=lambda: True, plugin_cache=cache)
    return create_server(cmds, start_surface=False), logic


@pytest.mark.anyio
async def test_spec2_tools_and_resources_listed(setup):
    mcp, fake = setup
    async with Client(mcp) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        assert {"logic_eq", "logic_plugin"} <= set(tools)
        props = set(tools["logic_plugin"].input_schema["properties"])
        assert {"action", "strip", "number", "slot", "param", "value", "plugin", "replace", "on", "tolerance", "force"} <= props
        assert set(tools["logic_eq"].input_schema["properties"]) >= {"action", "band", "param", "value", "allow_insert"}
        uris = {str(r.uri) for r in (await client.list_resources()).resources}
        assert {"logic://plugins", "logic://inserts", "logic://view"} <= uris


@pytest.mark.anyio
async def test_spec2_calls_via_client(assign_setup):
    mcp, logic = assign_setup
    async with Client(mcp) as client:
        r = await client.call_tool("logic_eq", {"action": "get", "strip": 2})
        assert r.structured_content["after"] == {"has_eq": False, "bands": {}}
        r = await client.call_tool("logic_eq", {"action": "set", "strip": 2})
        assert r.structured_content["verified"] == "skipped" and "band" in r.structured_content["note"]
        r = await client.call_tool("logic_eq", {"action": "set", "strip": 2, "band": 3, "param": "gain", "value": -3})
        assert r.structured_content["verified"] == "verified" and logic.tracks[1].eq[2][1].value == -3.0
        r = await client.call_tool("logic_plugin", {"action": "insert", "strip": 2, "slot": 2, "plugin": "Compressor"})
        assert r.structured_content["verified"] == "verified" and logic.tracks[1].inserts[2] == "Compressor"
        r = await client.call_tool("logic_plugin", {"action": "set", "strip": 2, "slot": 2, "param": "Thrs", "value": -30})
        assert r.structured_content["verified"] == "verified"
        r = await client.call_tool("logic_plugin", {"action": "params", "strip": 2})
        assert r.structured_content["verified"] == "skipped" and "slot" in r.structured_content["note"]
        r = await client.call_tool("logic_plugin", {"action": "list"})
        assert r.structured_content["after"]["tracks"]["16"]["2"]["name"] == "Compressor"
        view = json.loads((await client.read_resource("logic://view")).contents[0].text)
        assert view["kind"] == "pan" and view["flip"] is False
        plugins = json.loads((await client.read_resource("logic://plugins")).contents[0].text)
        assert plugins["items"][6] == {"index": 6, "name": "Compressor"} and plugins["source"] == "bundled"
        inserts = json.loads((await client.read_resource("logic://inserts")).contents[0].text)
        assert inserts["16"]["2"]["text"] == "Comprs"
        status = await client.call_tool("logic_session", {"action": "status"})
        assert status.structured_content["after"]["view_kind"] == "pan"


@pytest.mark.anyio
async def test_send_tool_via_client(assign_setup):
    mcp, logic = assign_setup
    async with Client(mcp) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        assert set(tools["logic_send"].input_schema["properties"]) >= {"action", "strip", "number", "send", "dest", "db", "pos", "on"}
        r = await client.call_tool("logic_send", {"action": "set_dest", "strip": 2, "send": 1, "dest": "Bus 1"})
        assert r.structured_content["verified"] == "verified" and logic.tracks[1].sends[1].dest == "Bus 1"
        r = await client.call_tool("logic_send", {"action": "set_level", "strip": 2, "send": 1, "db": "-inf"})
        assert r.structured_content["verified"] == "skipped" and r.structured_content["note"] == "already"   # 새 센드는 -∞(S5, 리뷰 M8)
        r = await client.call_tool("logic_send", {"action": "set_level", "strip": 2, "send": 1, "db": -6})
        assert r.structured_content["verified"] == "verified"
        r = await client.call_tool("logic_send", {"action": "get", "strip": 2})
        assert r.structured_content["after"]["sends"]["1"]["bus"] == 1 and r.structured_content["after"]["sends"]["1"]["level_db"] == -6.0
        r = await client.call_tool("logic_send", {"action": "mute", "strip": 2})
        assert r.structured_content["verified"] == "skipped" and "send" in r.structured_content["note"]
        r = await client.call_tool("logic_send", {"action": "set_pos", "strip": 2, "send": 1})
        assert r.structured_content["verified"] == "skipped" and "pos" in r.structured_content["note"]
        r = await client.call_tool("logic_send", {"action": "remove", "strip": 2, "send": 1})
        assert r.structured_content["verified"] == "verified" and logic.tracks[1].sends[1] is None


@pytest.mark.anyio
async def test_plugin_move_requires_to_slot(setup):
    mcp, fake = setup
    async with Client(mcp, raise_exceptions=True) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        assert "to_slot" in tools["logic_plugin"].input_schema["properties"]
        result = await client.call_tool("logic_plugin", {"action": "move", "strip": 1, "slot": 2})
        sc = result.structured_content
        assert sc["ok"] is False and sc["verified"] == "skipped" and sc["note"] == "move에는 to_slot(1-8)이 필요"


@pytest.mark.anyio
async def test_plugin_calibrate_requires_force(setup, monkeypatch):
    from logic_mcp.logic.commands import ToolResult
    from logic_mcp.logic.plugin import PluginCommands

    called = []

    def fake_calibrate(self, strip, number, slot):
        called.append((strip, number, slot))
        return ToolResult(ok=True, verified="verified", action="plugin_calibrate", note=f"{strip}/{number}/{slot}")

    monkeypatch.setattr(PluginCommands, "calibrate", fake_calibrate)
    mcp, fake = setup
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("logic_plugin", {"action": "calibrate", "strip": 1, "slot": 2})
        sc = result.structured_content
        assert sc["ok"] is False and sc["verified"] == "skipped"
        assert "force=true" in sc["note"]
        assert called == []


@pytest.mark.anyio
async def test_plugin_calibrate_with_force_calls_command(setup, monkeypatch):
    from logic_mcp.logic.commands import ToolResult
    from logic_mcp.logic.plugin import PluginCommands

    monkeypatch.setattr(
        PluginCommands, "calibrate",
        lambda self, strip, number, slot: ToolResult(ok=True, verified="verified", action="plugin_calibrate", note=f"{strip}/{number}/{slot}"))
    mcp, fake = setup
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("logic_plugin", {"action": "calibrate", "strip": 1, "slot": 2, "force": True})
        sc = result.structured_content
        assert sc["ok"] is True and sc["note"] == "1/None/2"


@pytest.mark.anyio
async def test_server_instructions_reach_client(setup):
    mcp, fake = setup
    async with Client(mcp, raise_exceptions=True) as client:
        assert client.instructions is not None
        assert "wait_ready" in client.instructions
