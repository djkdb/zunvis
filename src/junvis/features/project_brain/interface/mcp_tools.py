"""project_brain을 MCP 도구로 노출한다 — MVP의 성공 판정 기준(M9).

여기서 MCP SDK를 임포트하지 않는 것이 중요하다. 도구를 **명세(ToolSpec)**로
기술하고, SDK에 묶는 일은 조립 루트(apps/mcp_server)가 한다. 덕분에
SDK 없이도 도구 계약을 테스트할 수 있고, SDK가 바뀌어도 이 파일은 그대로다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from junvis.features.project_brain.application.dto import (
    ProjectSummary,
    RegisterProjectCommand,
)
from junvis.features.project_brain.application.use_cases.load_context import (
    LoadProjectContext,
)
from junvis.features.project_brain.application.use_cases.queries import (
    ListProjects,
    SearchProjects,
)
from junvis.features.project_brain.application.use_cases.refresh_snapshot import (
    RefreshSnapshot,
)
from junvis.features.project_brain.application.use_cases.register_project import (
    RegisterProject,
)
from junvis.features.project_brain.application.use_cases.remember_note import RememberNote

from pathlib import Path


@dataclass(frozen=True)
class ToolResult:
    """모델이 읽을 텍스트와, 기계가 읽을 구조화 데이터."""

    text: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[Mapping[str, Any]], ToolResult]
    read_only: bool = True


def _summary_dict(summary: ProjectSummary) -> dict[str, Any]:
    return {
        "slug": summary.slug,
        "name": summary.name,
        "purpose": summary.purpose,
        "repo": summary.repo_full_name,
        "tech_stack": list(summary.tech_stack),
        "branch": summary.branch,
        "dirty": summary.dirty,
        "last_commit": summary.last_commit,
        "open_todos": summary.open_todo_count,
        "notes": summary.note_count,
        "path": summary.local_path,
        "updated_at": summary.updated_at.isoformat(),
    }


def _summary_line(summary: ProjectSummary) -> str:
    bits = [f"- {summary.slug} — {summary.name}"]
    if summary.purpose:
        bits.append(f"  목적: {summary.purpose}")
    if summary.tech_stack:
        bits.append(f"  스택: {', '.join(summary.tech_stack)}")
    if summary.branch:
        state = " (변경 있음)" if summary.dirty else ""
        bits.append(f"  브랜치: {summary.branch}{state}")
    if summary.last_commit:
        bits.append(f"  최근: {summary.last_commit}")
    return "\n".join(bits)


def build_project_tools(
    *,
    register: RegisterProject,
    refresh: RefreshSnapshot,
    load_context: LoadProjectContext,
    search: SearchProjects,
    list_projects: ListProjects,
    remember: RememberNote,
) -> list[ToolSpec]:
    def handle_list(_arguments: Mapping[str, Any]) -> ToolResult:
        summaries = list_projects()
        if not summaries:
            return ToolResult("등록된 프로젝트가 없습니다.", {"projects": []})
        text = "\n".join(_summary_line(s) for s in summaries)
        return ToolResult(text, {"projects": [_summary_dict(s) for s in summaries]})

    def handle_context(arguments: Mapping[str, Any]) -> ToolResult:
        pack = load_context(
            str(arguments["slug"]),
            budget_tokens=int(arguments.get("budget_tokens", 2000)),
        )
        return ToolResult(
            pack.to_markdown(),
            {
                "slug": pack.slug,
                "sections": [s.title for s in pack.sections],
                "estimated_tokens": pack.estimated_tokens,
                "truncated": pack.truncated,
            },
        )

    def handle_search(arguments: Mapping[str, Any]) -> ToolResult:
        hits = search(str(arguments["query"]), limit=int(arguments.get("limit", 10)))
        if not hits:
            return ToolResult("검색 결과가 없습니다.", {"projects": []})
        text = "\n".join(_summary_line(s) for s in hits)
        return ToolResult(text, {"projects": [_summary_dict(s) for s in hits]})

    def handle_register(arguments: Mapping[str, Any]) -> ToolResult:
        raw_path = arguments.get("path")
        summary = register(
            RegisterProjectCommand(
                name=arguments.get("name"),
                slug=arguments.get("slug"),
                path=Path(str(raw_path)) if raw_path else None,
                purpose=str(arguments.get("purpose", "")),
                architecture_note=str(arguments.get("architecture_note", "")),
                remote_url=arguments.get("remote_url"),
            )
        )
        return ToolResult(f"'{summary.slug}' 등록/갱신 완료.", _summary_dict(summary))

    def handle_remember(arguments: Mapping[str, Any]) -> ToolResult:
        summary = remember(str(arguments["slug"]), str(arguments["text"]))
        return ToolResult(
            f"'{summary.slug}'에 기억했습니다. (메모 {summary.note_count}건)",
            _summary_dict(summary),
        )

    def handle_refresh(arguments: Mapping[str, Any]) -> ToolResult:
        summary = refresh(str(arguments["slug"]))
        return ToolResult(f"'{summary.slug}' 스냅샷을 갱신했습니다.", _summary_dict(summary))

    slug_property = {"type": "string", "description": "프로젝트 slug"}

    return [
        ToolSpec(
            name="junvis_project_list",
            description=(
                "JUNVIS가 기억하고 있는 모든 프로젝트를 나열한다. "
                "어떤 프로젝트가 있는지 모를 때 가장 먼저 부른다."
            ),
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=handle_list,
        ),
        ToolSpec(
            name="junvis_project_context",
            description=(
                "프로젝트의 Context Pack(목적·기술스택·아키텍처·최근 커밋·TODO·이슈·"
                "메모·README)을 토큰 예산에 맞춰 조립해 돌려준다. "
                "특정 프로젝트에서 작업을 시작할 때 가장 먼저 부른다."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "slug": slug_property,
                    "budget_tokens": {
                        "type": "integer",
                        "description": "컨텍스트 토큰 예산 (기본 2000)",
                        "minimum": 1,
                    },
                },
                "required": ["slug"],
                "additionalProperties": False,
            },
            handler=handle_context,
        ),
        ToolSpec(
            name="junvis_project_search",
            description="모든 프로젝트를 전문 검색한다. 이름·목적·스택·README·메모를 훑는다.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "검색어"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=handle_search,
        ),
        ToolSpec(
            name="junvis_project_register",
            description=(
                "프로젝트를 등록하거나 이미 있으면 설명을 갱신한다. "
                "로컬 경로를 주면 git 원격을 자동으로 알아낸다."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "slug": {"type": "string"},
                    "path": {"type": "string", "description": "로컬 저장소 경로"},
                    "purpose": {"type": "string", "description": "이 프로젝트가 존재하는 이유"},
                    "architecture_note": {"type": "string"},
                    "remote_url": {"type": "string"},
                },
                "additionalProperties": False,
            },
            handler=handle_register,
            read_only=False,
        ),
        ToolSpec(
            name="junvis_project_remember",
            description=(
                "이 프로젝트에 대해 기억해둘 사실을 남긴다. "
                "다음에 Context Pack을 부를 때 함께 주입된다."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "slug": slug_property,
                    "text": {"type": "string", "description": "기억할 내용"},
                },
                "required": ["slug", "text"],
                "additionalProperties": False,
            },
            handler=handle_remember,
            read_only=False,
        ),
        ToolSpec(
            name="junvis_project_refresh",
            description="git·파일시스템·GitHub에서 프로젝트 스냅샷을 다시 수집한다.",
            input_schema={
                "type": "object",
                "properties": {"slug": slug_property},
                "required": ["slug"],
                "additionalProperties": False,
            },
            handler=handle_refresh,
            read_only=False,
        ),
    ]
