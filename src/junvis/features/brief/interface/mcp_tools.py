"""brief를 MCP 도구로 노출한다."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from junvis.core.mcp.tools import ToolResult, ToolSpec
from junvis.features.brief.application.use_cases.compose_briefing import ComposeBriefing


def build_brief_tools(*, compose: ComposeBriefing) -> list[ToolSpec]:
    def handle_brief(_arguments: Mapping[str, Any]) -> ToolResult:
        briefing = compose()
        return ToolResult(
            briefing.to_markdown(),
            {
                "day": briefing.day.isoformat(),
                "sections": [s.title for s in briefing.sections],
                "peak_urgency": briefing.peak_urgency.name,
                "headline": briefing.headline(),
            },
        )

    return [
        ToolSpec(
            name="junvis_daily_brief",
            description=(
                "오늘의 브리핑을 조립한다. 일정·멈춰 있는 작업·할 일·열린 이슈·"
                "ZUN 콘텐츠 현황·대기 중인 아이디어·진행 중인 프로젝트·AI 소식·"
                "작업 습관을 우선순위대로 돌려준다. 하루를 시작할 때 부른다."
            ),
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=handle_brief,
        )
    ]
