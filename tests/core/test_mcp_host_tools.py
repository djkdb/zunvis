"""MCP Host를 다시 MCP 도구로 노출한 부분.

핵심은 확인 게이트다. 외부 서버는 우리가 만들지 않은 코드이므로,
사용자가 승인하지 않은 호출은 실행되면 안 된다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from junvis.core.mcp.catalog import ExternalTool, ToolCatalog
from junvis.core.mcp.config import ServerSpec
from junvis.core.mcp.host import McpHost
from junvis.core.mcp.host_tools import ArgumentConfirmer, build_host_tools
from junvis.core.policy.engine import PolicyEngine

SERVER_SCRIPT = Path(__file__).resolve().parents[1] / "apps" / "fixture_mcp_server.py"
SRC = Path(__file__).resolve().parents[2] / "src"


def spec(**overrides) -> ServerSpec:
    defaults = dict(
        id="test",
        command=sys.executable,
        args=(str(SERVER_SCRIPT),),
        env={"PYTHONPATH": str(SRC)},
    )
    defaults.update(overrides)
    return ServerSpec(**defaults)


@pytest.fixture()
def wired(db):
    """MCP 서버 경로와 같은 방식으로 조립한다."""
    confirmer = ArgumentConfirmer()
    host = McpHost(
        ToolCatalog(db), {"test": spec()}, policy=PolicyEngine(confirmer=confirmer)
    )
    tools = {t.name: t for t in build_host_tools(host, confirmer)}
    yield host, tools
    host.close()


# -- 도구 찾기 ---------------------------------------------------------------


def test_lists_nothing_before_discovery(wired) -> None:
    _, tools = wired
    result = tools["junvis_external_tools"].handler({})
    assert "없습니다" in result.text
    assert "test" in result.text  # 등록된 서버는 알려준다


def test_lists_discovered_tools(wired) -> None:
    host, tools = wired
    host.discover("test")

    result = tools["junvis_external_tools"].handler({})

    assert "test.echo" in result.text
    assert {t["name"] for t in result.data["tools"]} == {
        "echo",
        "add_numbers",
        "explode",
    }


def test_query_narrows_the_list(wired) -> None:
    host, tools = wired
    host.discover("test")

    result = tools["junvis_external_tools"].handler({"query": "계산기 산수"})

    assert [t["name"] for t in result.data["tools"]] == ["add_numbers"]


def test_input_schema_is_passed_through(wired) -> None:
    """호출하려면 인자 모양을 알아야 한다."""
    host, tools = wired
    host.discover("test")

    listed = tools["junvis_external_tools"].handler({"query": "echo"})
    schema = listed.data["tools"][0]["input_schema"]
    assert schema["properties"]["text"]["type"] == "string"


# -- 확인 게이트 (핵심) ------------------------------------------------------


def test_call_without_confirmation_is_refused(wired) -> None:
    _, tools = wired
    result = tools["junvis_external_call"].handler(
        {"server": "test", "tool": "echo", "arguments": {"text": "안녕"}}
    )

    assert result.data["needs_confirmation"] is True
    assert "confirm=true" in result.text


def test_call_with_confirmation_proceeds(wired) -> None:
    _, tools = wired
    result = tools["junvis_external_call"].handler(
        {
            "server": "test",
            "tool": "echo",
            "arguments": {"text": "안녕"},
            "confirm": True,
        }
    )

    assert result.text == "안녕"
    assert result.data["is_error"] is False


def test_explicit_false_reads_as_a_refusal(wired) -> None:
    """confirm을 안 준 것과 false로 준 것은 다르다."""
    _, tools = wired
    result = tools["junvis_external_call"].handler(
        {"server": "test", "tool": "echo", "confirm": False}
    )
    assert result.data["denied"] is True
    assert "needs_confirmation" not in result.data


def test_confirmation_does_not_persist_between_calls(wired) -> None:
    """한 번 승인했다고 다음 호출까지 승인된 것은 아니다."""
    _, tools = wired
    call = tools["junvis_external_call"].handler
    call({"server": "test", "tool": "echo", "arguments": {}, "confirm": True})

    second = call({"server": "test", "tool": "echo", "arguments": {}})

    assert second.data.get("needs_confirmation") is True


def test_trusted_server_needs_no_confirmation(db) -> None:
    confirmer = ArgumentConfirmer()
    host = McpHost(
        ToolCatalog(db),
        {"test": spec(trusted=True)},
        policy=PolicyEngine(confirmer=confirmer),
    )
    tools = {t.name: t for t in build_host_tools(host, confirmer)}

    result = tools["junvis_external_call"].handler(
        {"server": "test", "tool": "echo", "arguments": {"text": "x"}}
    )

    assert result.text == "x"
    host.close()


# -- 오류 전달 ---------------------------------------------------------------


def test_tool_error_is_reported_with_the_flag(wired) -> None:
    _, tools = wired
    result = tools["junvis_external_call"].handler(
        {"server": "test", "tool": "explode", "confirm": True}
    )
    assert result.data["is_error"] is True


def test_unknown_server_raises_for_the_host_to_report(wired) -> None:
    from junvis.core.mcp.host import UnknownServer

    _, tools = wired
    with pytest.raises(UnknownServer):
        tools["junvis_external_call"].handler(
            {"server": "없는서버", "tool": "echo", "confirm": True}
        )


def test_tools_are_marked_read_only_correctly(wired) -> None:
    _, tools = wired
    assert tools["junvis_external_tools"].read_only is True
    assert tools["junvis_external_call"].read_only is False
