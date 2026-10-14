"""읽기 전용 리소스. JSON 문자열을 돌려준다."""
from __future__ import annotations

import json

from mcp.server import MCPServer

from ..logic.commands import Commands


def register_resources(mcp: MCPServer, commands: Commands) -> None:
    @mcp.resource("logic://status", description="연결 상태, 설정 여부, 보이는 번호")
    def status() -> str:
        return json.dumps(commands.status(), ensure_ascii=False)

    @mcp.resource("logic://transport", description="트랜스포트 LED와 타임 디스플레이(최신값)")
    def transport() -> str:
        st = commands.surface.state
        return json.dumps({**st.transport.__dict__, "time": {"mode": st.time.mode, "text": st.time.text,
                                                              "parsed": st.time.parsed()}}, ensure_ascii=False)

    @mcp.resource("logic://strips", description="현재 뱅크 스트립 8개")
    def strips() -> str:
        st = commands.surface.state
        return json.dumps({"settling": commands.surface.clock() < st.connection.dirty_until,
                           "strips": [commands._strip_view(i) for i in range(8)]}, ensure_ascii=False)

    @mcp.resource("logic://lcd", description="LCD 2×56 원문")
    def lcd() -> str:
        st = commands.surface.state
        return json.dumps({"row1": st.lcd[0], "row2": st.lcd[1],
                           "settling": commands.surface.clock() < st.connection.dirty_until}, ensure_ascii=False)
