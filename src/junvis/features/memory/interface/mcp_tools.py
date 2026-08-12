"""memory를 MCP 도구로 노출한다.

Claude Code가 이 도구로 사실을 남기면, 다음 세션에서 JUNVIS가 그것을 안다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from junvis.core.mcp.tools import ToolResult, ToolSpec
from junvis.features.memory.application.dto import MemoryView
from junvis.features.memory.application.use_cases.queries import (
    ListMemories,
    RecallMemories,
)
from junvis.features.memory.application.use_cases.remember import (
    ForgetFact,
    PinFact,
    RememberFact,
)
from junvis.features.memory.domain.model import MemoryScope


def _view_dict(view: MemoryView) -> dict[str, Any]:
    return {
        "id": view.id,
        "text": view.text,
        "scope": view.scope,
        "subject": view.subject,
        "tags": list(view.tags),
        "pinned": view.pinned,
        "source": view.source,
        "created_at": view.created_at.isoformat(),
    }


def _line(view: MemoryView) -> str:
    marks = []
    if view.pinned:
        marks.append("고정")
    if view.scope != MemoryScope.USER.value:
        marks.append(MemoryScope(view.scope).label)
    if view.subject:
        marks.append(view.subject)
    suffix = f" [{', '.join(marks)}]" if marks else ""
    return f"- {view.text}{suffix} ({view.short_id})"


def build_memory_tools(
    *,
    remember: RememberFact,
    recall: RecallMemories,
    list_memories: ListMemories,
    forget: ForgetFact,
    pin: PinFact,
) -> list[ToolSpec]:
    def handle_remember(arguments: Mapping[str, Any]) -> ToolResult:
        view = remember(
            str(arguments["text"]),
            scope=MemoryScope(str(arguments.get("scope", MemoryScope.USER.value))),
            subject=str(arguments.get("subject", "")),
            tags=tuple(arguments.get("tags", ())),
            pinned=bool(arguments.get("pinned", False)),
        )
        return ToolResult(f"기억했습니다: {view.text}", _view_dict(view))

    def handle_recall(arguments: Mapping[str, Any]) -> ToolResult:
        raw_scope = arguments.get("scope")
        views = recall(
            str(arguments.get("query", "")),
            scope=MemoryScope(raw_scope) if raw_scope else None,
            subject=str(arguments.get("subject", "")),
            limit=int(arguments.get("limit", 20)),
        )
        if not views:
            return ToolResult("기억나는 것이 없습니다.", {"memories": []})
        return ToolResult(
            "\n".join(_line(view) for view in views),
            {"memories": [_view_dict(view) for view in views]},
        )

    def handle_list(arguments: Mapping[str, Any]) -> ToolResult:
        views = list_memories(limit=int(arguments.get("limit", 100)))
        if not views:
            return ToolResult("아직 기억한 것이 없습니다.", {"memories": []})
        return ToolResult(
            "\n".join(_line(view) for view in views),
            {"memories": [_view_dict(view) for view in views]},
        )

    def handle_forget(arguments: Mapping[str, Any]) -> ToolResult:
        view = forget(str(arguments["id"]))
        return ToolResult(f"잊었습니다: {view.text}", _view_dict(view))

    def handle_pin(arguments: Mapping[str, Any]) -> ToolResult:
        view = pin(str(arguments["id"]), bool(arguments.get("pinned", True)))
        state = "고정했습니다" if view.pinned else "고정을 해제했습니다"
        return ToolResult(f"{state}: {view.text}", _view_dict(view))

    scope_property = {
        "type": "string",
        "enum": [scope.value for scope in MemoryScope],
        "description": "user=사람에 대한 사실, project=특정 프로젝트, content=ZUN 콘텐츠 규칙",
    }

    return [
        ToolSpec(
            name="junvis_remember",
            description=(
                "사용자에 대해 기억해둘 사실을 남긴다. 선호·규칙·습관처럼 "
                "다음에도 유효한 것만 남긴다. pinned=true면 항상 우선 주입된다."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "기억할 사실"},
                    "scope": scope_property,
                    "subject": {"type": "string", "description": "프로젝트 slug 등"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "pinned": {"type": "boolean"},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
            handler=handle_remember,
            read_only=False,
        ),
        ToolSpec(
            name="junvis_recall",
            description=(
                "기억을 회상한다. query를 비우면 해당 스코프의 최근 기억을 돌려준다."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "scope": scope_property,
                    "subject": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
                "additionalProperties": False,
            },
            handler=handle_recall,
        ),
        ToolSpec(
            name="junvis_memories",
            description="기억한 것을 전부 나열한다(고정된 것 먼저, 최근 순).",
            input_schema={
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 500}},
                "additionalProperties": False,
            },
            handler=handle_list,
        ),
        ToolSpec(
            name="junvis_forget",
            description="기억을 지운다. 사용자가 명시적으로 요청할 때만 쓴다.",
            input_schema={
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
                "additionalProperties": False,
            },
            handler=handle_forget,
            read_only=False,
        ),
        ToolSpec(
            name="junvis_pin_memory",
            description="기억을 고정하거나 해제한다. 고정된 기억은 항상 먼저 주입된다.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "pinned": {"type": "boolean"},
                },
                "required": ["id"],
                "additionalProperties": False,
            },
            handler=handle_pin,
            read_only=False,
        ),
    ]
