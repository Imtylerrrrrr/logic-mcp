import json

import pytest
from mcp import Client

from logic_mcp.logic.commands import Commands
from logic_mcp.logic.faders import FaderTable
from logic_mcp.mcu import protocol as P
from logic_mcp.server.app import create_server
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
        assert names == {"logic_transport", "logic_track", "logic_mixer", "logic_bank", "logic_session"}
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
