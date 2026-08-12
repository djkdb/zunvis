"""MCP Host를 다시 MCP 도구로 노출한다.

이것이 Host의 실제 값어치다. Claude Code가 JUNVIS를 통해 등록된 외부 서버를
쓸 수 있게 되고, 그 호출은 전부 JUNVIS의 정책 게이트와 도구 선별을 거친다.

`core`에 있는 이유: 이 도구들은 특정 Bounded Context의 것이 아니라
Host 자신의 기능이다.

확인 절차: 외부 호출은 MEDIUM이라 확인이 필요하다. MCP 경유에는 확인 통로가
없으므로 인자로 `confirm: true`를 요구한다. 호스트(Claude Code)가 사용자에게
묻고 넘긴다. SDK의 Elicitation을 쓰지 않는 이유는 도구 핸들러가 세션에
접근하지 않는 순수 함수이기 때문이다 — 그 단순함을 지키는 편이 낫다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from junvis.core.domain.errors import PolicyConfirmationRequired, PolicyDenied
from junvis.core.mcp.host import McpHost
from junvis.core.mcp.ranking import DEFAULT_LIMIT
from junvis.core.mcp.tools import ToolResult, ToolSpec


class ArgumentConfirmer:
    """도구 인자의 `confirm` 값을 사용자 확인으로 삼는다.

    조립 루트가 이 인스턴스 하나를 `PolicyEngine`과 도구 양쪽에 넘긴다.
    도구가 정책 엔진의 내부를 들여다보지 않게 하기 위해서다.
    """

    def __init__(self) -> None:
        self.confirmed = False

    def confirm(self, action, verdict) -> bool:
        return self.confirmed


def build_host_tools(
    host: McpHost, confirmer: ArgumentConfirmer | None = None
) -> list[ToolSpec]:
    def handle_list(arguments: Mapping[str, Any]) -> ToolResult:
        query = str(arguments.get("query", ""))
        tools = host.tools(query, limit=int(arguments.get("limit", DEFAULT_LIMIT)))
        if not tools:
            registered = ", ".join(sorted(host.servers)) or "없음"
            return ToolResult(
                f"해당하는 외부 도구가 없습니다. (등록된 서버: {registered})",
                {"tools": []},
            )
        lines = []
        for tool in tools:
            lines.append(f"- {tool.qualified_name}")
            if tool.description:
                lines.append(f"    {tool.description.splitlines()[0]}")
        return ToolResult(
            "\n".join(lines),
            {
                "tools": [
                    {
                        "server": tool.server_id,
                        "name": tool.name,
                        "qualified_name": tool.qualified_name,
                        "description": tool.description,
                        "input_schema": tool.input_schema,
                    }
                    for tool in tools
                ]
            },
        )

    def handle_call(arguments: Mapping[str, Any]) -> ToolResult:
        server = str(arguments["server"])
        tool = str(arguments["tool"])
        requested = arguments.get("confirm")
        if confirmer is not None:
            confirmer.confirmed = bool(requested)
        try:
            result = host.call(server, tool, dict(arguments.get("arguments") or {}))
        except (PolicyConfirmationRequired, PolicyDenied):
            # 정책 엔진은 "확인을 못 받았다"와 "사용자가 거부했다"를 같은
            # 자리에서 낸다. 부른 쪽이 confirm을 **명시적으로 false**로 준
            # 경우만 거부로 읽는다. 안 준 것은 아직 안 물어본 것이다.
            if requested is False:
                return ToolResult(
                    f"'{server}.{tool}' 호출이 거부되었습니다.",
                    {"denied": True, "server": server, "tool": tool},
                )
            return ToolResult(
                f"'{server}.{tool}'는 외부 서버 호출이라 사용자 확인이 필요합니다. "
                "사용자에게 물어본 뒤 confirm=true로 다시 부르세요.",
                {"needs_confirmation": True, "server": server, "tool": tool},
            )
        return ToolResult(
            result.text or "(빈 응답)",
            {
                "server": result.server_id,
                "tool": result.tool,
                "is_error": result.is_error,
                "structured": result.data,
            },
        )

    return [
        ToolSpec(
            name="junvis_external_tools",
            description=(
                "JUNVIS에 등록된 외부 MCP 서버의 도구를 찾는다. query와 관련된 "
                "것만 돌려주므로, 무엇을 하고 싶은지 적어 부르면 된다. "
                "브라우저 조작처럼 JUNVIS가 직접 못 하는 일을 할 때 먼저 부른다."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "하고 싶은 일"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "additionalProperties": False,
            },
            handler=handle_list,
        ),
        ToolSpec(
            name="junvis_external_call",
            description=(
                "외부 MCP 서버의 도구를 호출한다. junvis_external_tools로 찾은 "
                "server와 name을 쓴다. 외부 서버 호출은 사용자 확인이 필요하므로, "
                "사용자에게 물어본 뒤 confirm=true로 부른다."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "server": {"type": "string"},
                    "tool": {"type": "string"},
                    "arguments": {"type": "object"},
                    "confirm": {
                        "type": "boolean",
                        "description": "사용자가 이 호출을 승인했는가",
                    },
                },
                "required": ["server", "tool"],
                "additionalProperties": False,
            },
            handler=handle_call,
            read_only=False,
        ),
    ]
