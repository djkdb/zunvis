"""테스트용 최소 MCP 서버.

JUNVIS의 MCP Host가 **실제 서버 프로세스**를 상대로 동작하는지 확인하기
위한 것이다. 목(mock)으로는 프로세스 기동·초기화·stdio 왕복을 검증할 수 없다.

`JUNVIS_TEST_SERVER_FAIL=1`이면 즉시 죽는다 — 기동 실패 경로를 검증한다.
"""

from __future__ import annotations

import os
import sys

import anyio
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

TOOLS = [
    types.Tool(
        name="echo",
        description="들어온 문장을 그대로 돌려준다",
        inputSchema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    ),
    types.Tool(
        name="add_numbers",
        description="두 숫자를 더한다. 계산기 산수",
        inputSchema={
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    ),
    types.Tool(
        name="explode",
        description="언제나 오류를 돌려준다",
        inputSchema={"type": "object", "properties": {}},
    ),
]


async def on_list_tools(_ctx, _params) -> types.ListToolsResult:
    return types.ListToolsResult(tools=TOOLS)


async def on_call_tool(_ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
    arguments = params.arguments or {}
    if params.name == "echo":
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=str(arguments.get("text", "")))],
            structuredContent={"echoed": arguments.get("text", "")},
        )
    if params.name == "add_numbers":
        total = float(arguments.get("a", 0)) + float(arguments.get("b", 0))
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=str(total))],
            structuredContent={"total": total},
        )
    if params.name == "explode":
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="일부러 실패")],
            isError=True,
        )
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=f"알 수 없는 도구: {params.name}")],
        isError=True,
    )


async def serve() -> None:
    server = Server(
        "junvis-test-server",
        version="0.0.1",
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    if os.environ.get("JUNVIS_TEST_SERVER_FAIL") == "1":
        sys.exit(3)
    anyio.run(serve)
