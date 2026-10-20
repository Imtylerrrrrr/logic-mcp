from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server import MCPServer

from ..logic.commands import Commands
from .resources import register_resources
from .tools import register_tools


INSTRUCTIONS = (
    "Logic Pro를 Mackie Control 에뮬레이션으로 조작한다. 시작 순서: logic_session wait_ready → "
    "logic_session configure(처음 한 번. Logic이 서피스를 다시 설치한 뒤에도 한 번) → logic://plugins 리소스 확인"
    "(scanned_at이 없거나 logic_version이 다르면 logic_plugin scan 권장).\n"
    "트랙은 strip(현재 뱅크 1~8) 또는 number(LCD에 찍히는 Logic 트랙 번호) 중 하나로 지정한다.\n"
    "모든 결과는 ok·verified(verified/unverified/skipped/timeout)·note를 가진다. ok가 false면 note가 이유다.\n"
    "EQ·플러그인·센드의 순서와 함정은 레포의 skills/logic-plugins/SKILL.md에 있다. 서버는 프로젝트를 저장하지 않는다."
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

    mcp = MCPServer("logic-mcp", instructions=INSTRUCTIONS, lifespan=lifespan)
    register_tools(mcp, commands)
    register_resources(mcp, commands)
    return mcp
