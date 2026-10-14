"""MCP 툴. 입력 검증과 Commands 호출만 한다."""
from __future__ import annotations

import math
from typing import Annotated, Literal

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from ..logic.commands import Commands, ToolResult

Strip = Annotated[int | None, Field(ge=1, le=8, description="현재 뱅크의 스트립 1-8. number와 둘 중 하나만")]
Number = Annotated[int | None, Field(ge=1, description="LCD에 찍히는 Logic 채널 번호(절대 주소). strip과 둘 중 하나만")]


def register_tools(mcp: MCPServer, commands: Commands) -> None:
    @mcp.tool(name="logic_transport", annotations=ToolAnnotations(idempotent_hint=True),
              description="재생/정지/녹음/사이클/되감기/빨리감기. LED와 타임 디스플레이로 검증한다.")
    def logic_transport(
        action: Literal["play", "stop", "record", "cycle_on", "cycle_off", "rewind", "fast_forward"],
    ) -> ToolResult:
        return commands.transport(action)

    @mcp.tool(name="logic_track", annotations=ToolAnnotations(idempotent_hint=True),
              description="트랙 뮤트/솔로/녹음 활성/선택. 이미 그 상태면 보내지 않는다(skipped).")
    def logic_track(
        action: Literal["mute", "unmute", "solo", "unsolo", "arm", "disarm", "select"],
        strip: Strip = None,
        number: Number = None,
    ) -> ToolResult:
        return commands.track(action, strip=strip, number=number)

    @mcp.tool(name="logic_mixer", annotations=ToolAnnotations(idempotent_hint=True),
              description="볼륨(dB, -inf..+6.0)과 팬(-64..63). 팬은 V-Pot가 PAN 모드일 때만.")
    def logic_mixer(
        action: Literal["set_volume", "set_pan"],
        strip: Strip = None,
        number: Number = None,
        db: Annotated[float | Literal["-inf"] | None, Field(description="set_volume: dB. 문자열 \"-inf\" 허용")] = None,
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
              description="8스트립 뱅크 이동. show는 number가 보이도록 뱅크를 찾아간다.")
    def logic_bank(
        action: Literal["left", "right", "channel_left", "channel_right", "first", "last", "show"],
        number: Number = None,
    ) -> ToolResult:
        return commands.bank(action, number=number)

    @mcp.tool(name="logic_session",
              description="status: 연결 상태. wait_ready: Logic이 서피스를 설치할 때까지 대기. configure: 번호 표시·값 모드·Beats 클락 보정(처음 한 번).")
    def logic_session(
        action: Literal["status", "wait_ready", "configure"],
        timeout_s: Annotated[float, Field(gt=0, le=120)] = 10.0,
    ) -> ToolResult:
        if action == "status":
            return ToolResult(ok=True, verified="skipped", action=action, after=commands.status())
        if action == "wait_ready":
            return commands.wait_ready(timeout_s)
        return commands.configure()
