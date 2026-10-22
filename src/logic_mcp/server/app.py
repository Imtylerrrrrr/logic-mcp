from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version as _pkg_version

from mcp.server import MCPServer

from ..logic.commands import Commands
from .resources import register_resources
from .tools import register_tools


INSTRUCTIONS = (
    "Operates Logic Pro through Mackie Control emulation. Startup order: logic_session wait_ready → "
    "logic_session configure (once at first; once more after Logic reinstalls the surface) → check the logic://plugins resource "
    "(if scanned_at is missing or logic_version differs, logic_plugin scan is recommended).\n"
    "Address a track with either strip (1-8 in the current bank) or number (the Logic track number shown on the LCD).\n"
    "Every result has ok, verified (verified/unverified/skipped/timeout), and note. If ok is false, note gives the reason.\n"
    "The order of operations and pitfalls for EQ, plug-ins, and sends are in the repo's skills/logic-plugins/SKILL.md. The server does not save the project."
)


def create_server(commands: Commands, *, start_surface: bool) -> MCPServer:
    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[None]:
        if start_surface:
            commands.surface.start()
        try:
            yield None
        finally:
            if start_surface:
                commands.surface.stop()

    mcp = MCPServer("logic-mcp", version=_pkg_version("logic-mcp"), instructions=INSTRUCTIONS, lifespan=lifespan)
    register_tools(mcp, commands)
    register_resources(mcp, commands)
    return mcp
