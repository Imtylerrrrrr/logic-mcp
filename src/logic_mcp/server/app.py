from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server import MCPServer

from ..logic.commands import Commands
from .resources import register_resources
from .tools import register_tools


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

    mcp = MCPServer("logic-mcp", lifespan=lifespan)
    register_tools(mcp, commands)
    register_resources(mcp, commands)
    return mcp
