"""M9 완료 기준: 실제 MCP 클라이언트가 JUNVIS 서버에 붙어 도구를 부른다.

이 테스트가 통과하면 Claude Code에서도 그대로 동작한다 — 같은 프로토콜,
같은 stdio 전송이기 때문이다.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

EXPECTED_TOOLS = {
    "junvis_project_list",
    "junvis_project_context",
    "junvis_project_search",
    "junvis_project_register",
    "junvis_project_remember",
    "junvis_project_refresh",
}


def _git_project(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)

    def run(*args: str) -> None:
        subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)

    run("init", "-q")
    run("config", "user.email", "zun@example.com")
    run("config", "user.name", "ZUN")
    (path / "README.md").write_text("# 릴스 편집기\n\nZUN 브랜드용 도구\n", encoding="utf-8")
    (path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    run("add", ".")
    run("commit", "-q", "-m", "첫 커밋")
    return path


def _server_env(home: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["JUNVIS_HOME"] = str(home)
    env["JUNVIS_OFFLINE"] = "1"  # 테스트는 네트워크에 나가지 않는다
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    return env


def _text(result) -> str:
    return "\n".join(block.text for block in result.content if getattr(block, "text", None))


def test_full_mcp_roundtrip(tmp_path: Path) -> None:
    project_dir = _git_project(tmp_path / "reels-editor")
    home = tmp_path / "home"

    async def scenario() -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "junvis.apps.mcp_server.main"],
            env=_server_env(home),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                assert init.server_info.name == "junvis"
                assert "junvis_project_context" in (init.instructions or "")

                # 1. 도구 목록
                tools = await session.list_tools()
                names = {tool.name for tool in tools.tools}
                assert EXPECTED_TOOLS <= names

                # 2. 처음엔 비어 있다
                listed = await session.call_tool("junvis_project_list", {})
                assert listed.is_error is not True
                assert "등록된 프로젝트가 없습니다" in _text(listed)

                # 3. 등록 — 로컬 경로에서 git·README·스택을 알아낸다
                registered = await session.call_tool(
                    "junvis_project_register",
                    {
                        "path": str(project_dir),
                        "slug": "reels-editor",
                        "name": "릴스 편집기",
                        "purpose": "ZUN 브랜드 콘텐츠 제작 도구",
                    },
                )
                assert registered.is_error is not True
                assert registered.structured_content["slug"] == "reels-editor"

                # 4. 등록 이벤트가 비동기 스냅샷 수집을 일으켰는지
                listed = await session.call_tool("junvis_project_list", {})
                assert "reels-editor" in _text(listed)
                assert "Python" in _text(listed)

                # 5. 기억 주입
                remembered = await session.call_tool(
                    "junvis_project_remember",
                    {"slug": "reels-editor", "text": "썸네일은 항상 3단어 이하"},
                )
                assert remembered.is_error is not True

                # 6. Context Pack — MVP의 핵심 시나리오
                context = await session.call_tool(
                    "junvis_project_context",
                    {"slug": "reels-editor", "budget_tokens": 1500},
                )
                markdown = _text(context)
                assert markdown.startswith("# 릴스 편집기 (reels-editor)")
                assert "ZUN 브랜드 콘텐츠 제작 도구" in markdown
                assert "첫 커밋" in markdown
                assert "썸네일은 항상 3단어 이하" in markdown
                assert context.structured_content["truncated"] is False

                # 7. 검색
                found = await session.call_tool(
                    "junvis_project_search", {"query": "브랜드"}
                )
                assert "reels-editor" in _text(found)

                # 8. 없는 프로젝트는 오류로 돌아온다 (예외로 죽지 않는다)
                missing = await session.call_tool(
                    "junvis_project_context", {"slug": "no-such-project"}
                )
                assert missing.is_error is True
                assert "등록되지 않은" in _text(missing)

    anyio.run(scenario)
