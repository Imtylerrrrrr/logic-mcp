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
Slot = Annotated[int | None, Field(ge=1, le=15, description="인서트 슬롯 1-15")]


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

    @mcp.tool(name="logic_eq", annotations=ToolAnnotations(idempotent_hint=True),
              description="Channel EQ. get: 8밴드 전체(EQ가 없으면 has_eq=false, 삽입하지 않음). "
                          "set: band 1-8, param freq|gain|slope|q|on, value. 밴드 1·8은 gain 대신 slope(6/12/18/24/36/48). "
                          "EQ가 없으면 allow_insert=true일 때만 Channel EQ를 삽입한다. 끝나면 PAN 모드로 돌아간다.")
    def logic_eq(
        action: Literal["get", "set"],
        strip: Strip = None,
        number: Number = None,
        band: Annotated[int | None, Field(ge=1, le=8)] = None,
        param: Literal["freq", "gain", "slope", "q", "on"] | None = None,
        value: Annotated[float | bool | None, Field(description="freq Hz, gain dB, slope 6..48, q 수치, on 불")] = None,
        allow_insert: bool = True,
    ) -> ToolResult:
        if action == "get":
            return commands.eq.get(strip, number)
        if band is None or param is None or value is None:
            return ToolResult(ok=False, verified="skipped", action="eq_set", note="set에는 band, param, value가 필요")
        return commands.eq.set(strip, number, band, param, value, allow_insert)

    @mcp.tool(name="logic_plugin",
              description="인서트 플러그인. list: 인벤토리(strip/number 없으면 뱅크 전체). params: 플러그인 파라미터 전체(인덱스·축약명·값). "
                          "get/set: param은 이름(부분 일치) 또는 인덱스, value는 숫자 또는 선택지 텍스트. insert: plugin 이름(부분 일치), "
                          "차 있으면 replace=true 필요. remove. bypass(on). scan: 삽입 메뉴 전 범위 스캔(30~90초, 삽입 없음, 빈 슬롯 필요). "
                          "편집 뷰 진입 시 Logic이 플러그인 창을 열고 닫는다. 끝나면 PAN 모드로 돌아간다.")
    def logic_plugin(
        action: Literal["list", "params", "get", "set", "insert", "remove", "bypass", "scan"],
        strip: Strip = None,
        number: Number = None,
        slot: Slot = None,
        param: Annotated[str | int | None, Field(description="파라미터 이름(부분 일치) 또는 1부터 인덱스")] = None,
        value: Annotated[float | str | bool | None, Field(description="set: 숫자 또는 선택지 텍스트(예: \"On\")")] = None,
        plugin: Annotated[str | None, Field(description="insert: 플러그인 이름(부분 일치)")] = None,
        replace: bool = False,
        on: Annotated[bool | None, Field(description="bypass: true=바이패스")] = None,
        tolerance: Annotated[float | None, Field(gt=0, description="set: 허용 오차(기본 dB 0.1, 그 밖 1%)")] = None,
        force: bool = False,
    ) -> ToolResult:
        name = f"plugin_{action}"
        if action == "scan":
            return commands.plugin.scan(force)
        if action == "list":
            return commands.plugin.list(strip, number)
        if slot is None:
            return ToolResult(ok=False, verified="skipped", action=name, note="slot(1-15)이 필요")
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
        if on is None:
            return ToolResult(ok=False, verified="skipped", action=name, note="bypass에는 on(true/false)이 필요")
        return commands.plugin.bypass(strip, number, slot, on)
