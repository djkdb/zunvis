"""JUNVIS를 MCP 서버로 노출한다 (M9).

이것이 MVP의 성공 판정 기준이다. 여기까지 되면 JUNVIS는 독립된 "앱"이
아니라 Claude Code가 직접 읽는 **개인 지식 계층**이 된다.

MCP SDK를 아는 유일한 파일이다. feature 쪽은 ToolSpec만 알고 있고,
SDK가 바뀌어도 고칠 곳은 여기뿐이다.
"""

from __future__ import annotations

import logging
import os
import sys

import anyio
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from junvis.apps.container import Junvis, build
from junvis.apps.mcp_server.exposure import (
    PROMPTS,
    build_prompt,
    list_projects_as_resources,
    read_project_resource,
)
from junvis.core.domain.errors import JunvisError
from junvis.core.mcp.host_tools import ArgumentConfirmer, build_host_tools
from junvis.features.brief.interface.mcp_tools import build_brief_tools
from junvis.features.creator.interface.mcp_tools import build_creator_tools
from junvis.features.memory.interface.mcp_tools import build_memory_tools
from junvis.features.project_brain.interface.mcp_tools import ToolSpec, build_project_tools

logger = logging.getLogger(__name__)

SERVER_NAME = "junvis"
SERVER_VERSION = "0.1.0"
INSTRUCTIONS = (
    "JUNVIS는 사용자의 개발 프로젝트와 콘텐츠를 기억하는 개인 지식 계층이다.\n"
    "- 특정 프로젝트에서 작업을 시작할 때 junvis_project_context를 먼저 불러 "
    "목적·기술스택·최근 커밋·TODO를 파악하라. 어떤 프로젝트가 있는지 모르면 "
    "junvis_project_list를 부르면 된다.\n"
    "- 사용자가 릴스·캐러셀 등 ZUN 브랜드 콘텐츠를 만들고 싶어 하면 "
    "junvis_content_create를 써라. project 인자를 주면 그 프로젝트의 실제 "
    "정보를 근거로 기획한다. junvis_content_list의 suggested 상태는 아직 "
    "손대지 않은 제안이다.\n"
    "- 사용자가 선호·규칙·습관을 말하면 junvis_remember로 남겨라. 다음에도 "
    "유효한 사실만 남기고, 지나가는 말은 남기지 않는다. 작업 전에 "
    "junvis_recall로 관련 기억을 확인하면 같은 말을 두 번 듣지 않는다.\n"
    "- JUNVIS가 직접 못 하는 일(브라우저 조작 등)은 junvis_external_tools로 "
    "등록된 외부 MCP 서버의 도구를 찾고 junvis_external_call로 부른다. "
    "외부 호출은 사용자 확인이 필요하니 먼저 물어보고 confirm=true로 부른다."
)


def collect_tools(
    container: Junvis, confirmer: ArgumentConfirmer | None = None
) -> list[ToolSpec]:
    """feature마다 자기 도구를 내놓고, 조립 루트가 모은다."""
    return [
        *build_project_tools(
            register=container.projects.register,
            refresh=container.projects.refresh,
            load_context=container.projects.load_context,
            search=container.projects.search,
            list_projects=container.projects.list_all,
            remember=container.projects.remember,
        ),
        *build_creator_tools(
            generate=container.creator.generate,
            list_content=container.creator.list_all,
            get_content=container.creator.get,
            dismiss=container.creator.dismiss,
            mark_published=container.creator.mark_published,
            get_brand_voice=container.creator.get_brand_voice,
            update_brand_voice=container.creator.update_brand_voice,
        ),
        *build_brief_tools(compose=container.brief.compose),
        *build_memory_tools(
            remember=container.memory.remember,
            recall=container.memory.recall,
            list_memories=container.memory.list_all,
            forget=container.memory.forget,
            pin=container.memory.pin,
        ),
        # JUNVIS가 Host로서 가진 것을 다시 도구로 내놓는다.
        *build_host_tools(container.mcp, confirmer),
    ]


def _to_mcp_tool(spec: ToolSpec) -> types.Tool:
    return types.Tool(
        name=spec.name,
        description=spec.description,
        inputSchema=spec.input_schema,
        annotations=types.ToolAnnotations(readOnlyHint=spec.read_only),
    )


def create_server(
    container: Junvis, confirmer: ArgumentConfirmer | None = None
) -> Server:
    specs = {spec.name: spec for spec in collect_tools(container, confirmer)}
    # SQLite 커넥션 하나를 공유하므로 도구 실행을 직렬화한다.
    # 개인용 단일 사용자 서버에서 이 정도 단순함이 옳다.
    lock = anyio.Lock()

    async def on_list_tools(_ctx, _params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[_to_mcp_tool(spec) for spec in specs.values()])

    async def on_call_tool(_ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
        spec = specs.get(params.name)
        if spec is None:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"알 수 없는 도구: {params.name}")],
                isError=True,
            )
        arguments = params.arguments or {}
        async with lock:
            try:
                # 도구 본체는 동기 코드(SQLite·git)라 스레드로 넘겨 이벤트 루프를 막지 않는다.
                result = await anyio.to_thread.run_sync(lambda: spec.handler(arguments))
                # 등록 후 스냅샷 수집 같은 비동기 후속 작업을 여기서 소비한다.
                await anyio.to_thread.run_sync(container.drain)
            except JunvisError as exc:
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text=str(exc))],
                    isError=True,
                )
            except Exception as exc:  # pragma: no cover - 방어적
                logger.exception("도구 실행 실패: %s", params.name)
                return types.CallToolResult(
                    content=[
                        types.TextContent(
                            type="text", text=f"{type(exc).__name__}: {exc}"
                        )
                    ],
                    isError=True,
                )

        return types.CallToolResult(
            content=[types.TextContent(type="text", text=result.text)],
            structuredContent=result.data or None,
        )

    # -- 리소스: 사람이 붙이는 것 -------------------------------------------
    #
    # 지금까지는 Claude Code가 `junvis_project_context`를 **부를 생각을 해야**
    # 컨텍스트가 갔다. 리소스로 내놓으면 사람이 파일처럼 붙인다.

    async def on_list_resources(_ctx, _params) -> types.ListResourcesResult:
        found = await anyio.to_thread.run_sync(
            lambda: list_projects_as_resources(container)
        )
        return types.ListResourcesResult(
            resources=[
                types.Resource(
                    uri=uri, name=name, description=detail, mimeType="text/markdown"
                )
                for uri, name, detail in found
            ]
        )

    async def on_read_resource(_ctx, params) -> types.ReadResourceResult:
        uri = str(params.uri)
        async with lock:
            text = await anyio.to_thread.run_sync(
                lambda: read_project_resource(container, uri)
            )
        return types.ReadResourceResult(
            contents=[
                types.TextResourceContents(
                    uri=params.uri, mimeType="text/markdown", text=text
                )
            ]
        )

    # -- 프롬프트: 시작점 -----------------------------------------------------

    async def on_list_prompts(_ctx, _params) -> types.ListPromptsResult:
        return types.ListPromptsResult(
            prompts=[
                types.Prompt(
                    name=name,
                    description=description,
                    arguments=[
                        types.PromptArgument(name=argument, required=False)
                        for argument in argument_names
                    ],
                )
                for name, description, argument_names in PROMPTS
            ]
        )

    async def on_get_prompt(_ctx, params) -> types.GetPromptResult:
        body = build_prompt(params.name, dict(params.arguments or {}))
        return types.GetPromptResult(
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(type="text", text=body),
                )
            ]
        )

    return Server(
        SERVER_NAME,
        version=SERVER_VERSION,
        instructions=INSTRUCTIONS,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
        on_list_resources=on_list_resources,
        on_read_resource=on_read_resource,
        on_list_prompts=on_list_prompts,
        on_get_prompt=on_get_prompt,
    )


async def serve(container: Junvis, confirmer: ArgumentConfirmer | None = None) -> None:
    server = create_server(container, confirmer)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> int:
    # stdout은 MCP 전용이다. 로그가 섞이면 프로토콜이 깨진다.
    logging.basicConfig(
        level=os.environ.get("JUNVIS_LOG_LEVEL", "WARNING").upper(),
        stream=sys.stderr,
    )
    # 확인 통로가 없는 경로다. 도구 인자의 confirm 값을 사용자 확인으로 삼는다.
    confirmer = ArgumentConfirmer()
    container = build(
        offline=os.environ.get("JUNVIS_OFFLINE") == "1", confirmer=confirmer
    )
    try:
        anyio.run(serve, container, confirmer)
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        container.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
