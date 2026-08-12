"""creator를 MCP 도구로 노출한다.

project_brain과 같은 규칙: 여기서 MCP SDK를 임포트하지 않는다.
ToolSpec은 `core/mcp`에서 온다 — 도구 명세는 특정 feature의 소유물이
아니라 인터페이스 계층의 공통 어휘이기 때문이다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from junvis.core.mcp.tools import ToolResult, ToolSpec
from junvis.features.creator.application.dto import ContentSummary
from junvis.features.creator.application.use_cases.generate_content import GenerateContent
from junvis.features.creator.application.use_cases.lifecycle import (
    DismissContent,
    MarkPublished,
    UpdateBrandVoice,
)
from junvis.features.creator.application.use_cases.queries import (
    GetBrandVoice,
    GetContent,
    ListContent,
)
from junvis.features.creator.domain.value_objects import ContentFormat, ContentStatus


def _summary_dict(summary: ContentSummary) -> dict[str, Any]:
    return {
        "id": summary.id,
        "subject": summary.subject,
        "format": summary.content_format,
        "status": summary.status,
        "project": summary.source_project_slug,
        "hook": summary.hook,
        "scenes": summary.scene_count,
        "duration_seconds": summary.duration_seconds,
        "hashtags": list(summary.hashtags),
        "published_url": summary.published_url,
        "updated_at": summary.updated_at.isoformat(),
    }


def _summary_line(summary: ContentSummary) -> str:
    marker = {
        ContentStatus.SUGGESTED.value: "제안",
        ContentStatus.DRAFTED.value: "초안",
        ContentStatus.PUBLISHED.value: "발행됨",
        ContentStatus.DISMISSED.value: "버림",
    }.get(summary.status, summary.status)
    line = f"- [{marker}] {summary.subject} ({summary.id[:8]})"
    if summary.hook:
        line += f"\n  Hook: {summary.hook}"
    if summary.scene_count:
        line += f"\n  장면 {summary.scene_count}개 · {summary.duration_seconds}초"
    if summary.source_project_slug:
        line += f"\n  프로젝트: {summary.source_project_slug}"
    return line


def build_creator_tools(
    *,
    generate: GenerateContent,
    list_content: ListContent,
    get_content: GetContent,
    dismiss: DismissContent,
    mark_published: MarkPublished,
    get_brand_voice: GetBrandVoice,
    update_brand_voice: UpdateBrandVoice,
) -> list[ToolSpec]:
    def handle_create(arguments: Mapping[str, Any]) -> ToolResult:
        raw_format = str(arguments.get("format", ContentFormat.REELS.value))
        detail = generate(
            subject=arguments.get("subject"),
            idea_id=arguments.get("id"),
            project_slug=arguments.get("project"),
            content_format=ContentFormat(raw_format),
            direction=str(arguments.get("direction", "")),
        )
        return ToolResult(detail.markdown, _summary_dict(detail.summary))

    def handle_list(arguments: Mapping[str, Any]) -> ToolResult:
        summaries = list_content(
            status=arguments.get("status"), limit=int(arguments.get("limit", 50))
        )
        if not summaries:
            return ToolResult("해당하는 콘텐츠가 없습니다.", {"content": []})
        return ToolResult(
            "\n".join(_summary_line(s) for s in summaries),
            {"content": [_summary_dict(s) for s in summaries]},
        )

    def handle_get(arguments: Mapping[str, Any]) -> ToolResult:
        detail = get_content(str(arguments["id"]))
        return ToolResult(detail.markdown, _summary_dict(detail.summary))

    def handle_dismiss(arguments: Mapping[str, Any]) -> ToolResult:
        summary = dismiss(str(arguments["id"]), str(arguments.get("reason", "")))
        return ToolResult(f"'{summary.subject}'을(를) 버렸습니다.", _summary_dict(summary))

    def handle_published(arguments: Mapping[str, Any]) -> ToolResult:
        summary = mark_published(str(arguments["id"]), arguments.get("url"))
        return ToolResult(f"'{summary.subject}' 발행을 기록했습니다.", _summary_dict(summary))

    def handle_brand_voice(arguments: Mapping[str, Any]) -> ToolResult:
        if any(key in arguments for key in ("topics", "tone", "audience", "banned_phrases")):
            voice = update_brand_voice(
                topics=arguments.get("topics"),
                tone=arguments.get("tone"),
                audience=arguments.get("audience"),
                banned_phrases=arguments.get("banned_phrases"),
            )
        else:
            voice = get_brand_voice()
        return ToolResult(
            voice.describe(),
            {
                "topics": list(voice.topics),
                "tone": voice.tone,
                "audience": voice.audience,
                "banned_phrases": list(voice.banned_phrases),
            },
        )

    id_property = {"type": "string", "description": "콘텐츠 id"}

    return [
        ToolSpec(
            name="junvis_content_create",
            description=(
                "릴스 또는 캐러셀 기획을 한 번에 생성한다. Hook·장면 구성·대본·"
                "B-roll·캡션·해시태그·썸네일 문구·댓글 유도 문구가 모두 나온다. "
                "subject로 새로 만들거나, id로 기존 제안에 대본을 붙인다. "
                "project를 주면 그 프로젝트의 실제 정보를 근거로 쓴다."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "콘텐츠 주제"},
                    "id": {"type": "string", "description": "기존 제안의 id"},
                    "project": {"type": "string", "description": "근거로 쓸 프로젝트 slug"},
                    "format": {"type": "string", "enum": ["reels", "carousel"]},
                    "direction": {"type": "string", "description": "추가 지시"},
                },
                "additionalProperties": False,
            },
            handler=handle_create,
            read_only=False,
        ),
        ToolSpec(
            name="junvis_content_list",
            description=(
                "콘텐츠 목록. status로 거른다 "
                "(suggested=아직 손대지 않은 제안, drafted=대본 있음, published, dismissed)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": [s.value for s in ContentStatus],
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                },
                "additionalProperties": False,
            },
            handler=handle_list,
        ),
        ToolSpec(
            name="junvis_content_get",
            description="콘텐츠 하나의 전체 대본을 마크다운으로 돌려준다.",
            input_schema={
                "type": "object",
                "properties": {"id": id_property},
                "required": ["id"],
                "additionalProperties": False,
            },
            handler=handle_get,
        ),
        ToolSpec(
            name="junvis_content_dismiss",
            description="제안이나 초안을 버린다.",
            input_schema={
                "type": "object",
                "properties": {"id": id_property, "reason": {"type": "string"}},
                "required": ["id"],
                "additionalProperties": False,
            },
            handler=handle_dismiss,
            read_only=False,
        ),
        ToolSpec(
            name="junvis_content_published",
            description=(
                "발행했다는 사실을 기록한다. JUNVIS가 Instagram에 올리지는 않는다 — "
                "사람이 올리고 JUNVIS는 기억만 한다."
            ),
            input_schema={
                "type": "object",
                "properties": {"id": id_property, "url": {"type": "string"}},
                "required": ["id"],
                "additionalProperties": False,
            },
            handler=handle_published,
            read_only=False,
        ),
        ToolSpec(
            name="junvis_brand_voice",
            description=(
                "ZUN 브랜드 성향을 조회하거나 갱신한다. "
                "인자를 주지 않으면 현재 값을 돌려준다."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "topics": {"type": "array", "items": {"type": "string"}},
                    "tone": {"type": "string"},
                    "audience": {"type": "string"},
                    "banned_phrases": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": False,
            },
            handler=handle_brand_voice,
            read_only=False,
        ),
    ]
