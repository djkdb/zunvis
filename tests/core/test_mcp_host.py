"""H1~H3 완료 기준: 실제 MCP 서버 프로세스를 상대로 왕복한다."""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest

from junvis.core.domain.errors import PolicyConfirmationRequired
from junvis.core.domain.event import utcnow
from junvis.core.mcp.catalog import ExternalTool, ToolCatalog
from junvis.core.mcp.config import DEFAULT_IDLE_SECONDS, McpConfig, ServerSpec
from junvis.core.mcp.host import McpHost, McpServerError, UnknownServer
from junvis.core.mcp.ranking import TokenOverlapRanker
from junvis.core.policy.engine import PolicyEngine

SERVER_SCRIPT = Path(__file__).resolve().parents[1] / "apps" / "fixture_mcp_server.py"
SRC = Path(__file__).resolve().parents[2] / "src"


def spec(server_id: str = "test", **overrides) -> ServerSpec:
    defaults = dict(
        id=server_id,
        command=sys.executable,
        args=(str(SERVER_SCRIPT),),
        env={"PYTHONPATH": str(SRC)},
    )
    defaults.update(overrides)
    return ServerSpec(**defaults)


@pytest.fixture()
def catalog(db) -> ToolCatalog:
    return ToolCatalog(db)


@pytest.fixture()
def host(catalog) -> McpHost:
    instance = McpHost(catalog, {"test": spec()})
    yield instance
    instance.close()


class AlwaysConfirm:
    def __init__(self, answer: bool = True) -> None:
        self.answer = answer
        self.asked = []

    def confirm(self, action, verdict) -> bool:
        self.asked.append(action)
        return self.answer


# -- 설정 --------------------------------------------------------------------


def test_config_roundtrip(tmp_path) -> None:
    config = McpConfig(tmp_path / "mcp.json")
    config.add(ServerSpec("browser", "uvx", ("--from", "browser-use", "x"), trusted=True))

    loaded = config.load()

    assert loaded["browser"].command == "uvx"
    assert loaded["browser"].args == ("--from", "browser-use", "x")
    assert loaded["browser"].trusted is True
    assert loaded["browser"].idle_seconds == DEFAULT_IDLE_SECONDS


def test_config_uses_the_claude_code_shape(tmp_path) -> None:
    """익숙한 형식을 두고 새 형식을 만들 이유가 없다."""
    import json

    path = tmp_path / "mcp.json"
    path.write_text(
        json.dumps({"mcpServers": {"x": {"command": "echo", "args": ["hi"]}}}),
        encoding="utf-8",
    )
    assert McpConfig(path).load()["x"].args == ("hi",)


def test_missing_config_is_not_an_error(tmp_path) -> None:
    assert McpConfig(tmp_path / "없음.json").load() == {}


def test_env_placeholder_is_filled_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("SOME_API_KEY", "실제값")
    resolved = ServerSpec("x", "cmd", env={"SOME_API_KEY": ""}).resolved_env()
    assert resolved["SOME_API_KEY"] == "실제값"


def test_config_remove(tmp_path) -> None:
    config = McpConfig(tmp_path / "mcp.json")
    config.add(ServerSpec("x", "cmd"))
    assert config.remove("x") is True
    assert config.remove("x") is False


def test_server_without_command_is_rejected(tmp_path) -> None:
    import json

    from junvis.core.mcp.config import McpConfigError

    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"mcpServers": {"x": {"args": []}}}), encoding="utf-8")
    with pytest.raises(McpConfigError):
        McpConfig(path).load()


# -- 카탈로그 ----------------------------------------------------------------


def test_catalog_replace_and_read(catalog) -> None:
    catalog.replace("s", [ExternalTool("s", "a", "설명"), ExternalTool("s", "b")])
    assert [t.name for t in catalog.tools("s")] == ["a", "b"]
    assert catalog.find("s", "a").description == "설명"
    assert catalog.find("s", "없음") is None


def test_catalog_replace_removes_stale_tools(catalog) -> None:
    catalog.replace("s", [ExternalTool("s", "old")])
    catalog.replace("s", [ExternalTool("s", "new")])
    assert [t.name for t in catalog.tools("s")] == ["new"]


def test_qualified_name_avoids_collisions_across_servers(catalog) -> None:
    catalog.replace("a", [ExternalTool("a", "search")])
    catalog.replace("b", [ExternalTool("b", "search")])
    assert {t.qualified_name for t in catalog.tools()} == {"a.search", "b.search"}


# -- 지연 기동과 호출 (실제 프로세스) -----------------------------------------


def test_discover_spawns_and_caches(host, catalog) -> None:
    tools = host.discover("test")

    assert {t.name for t in tools} == {"echo", "add_numbers", "explode"}
    # 캐시에 남아 다음부터는 서버 없이 답할 수 있다
    assert {t.name for t in catalog.tools("test")} == {"echo", "add_numbers", "explode"}
    assert host.running == {"test"}


def test_tools_are_served_from_cache_without_spawning(catalog) -> None:
    """부팅 시 전체 서버 기동 금지 — 목록 조회로 서버가 뜨면 안 된다."""
    catalog.replace("test", [ExternalTool("test", "echo", "설명")])
    fresh = McpHost(catalog, {"test": spec()})

    assert [t.name for t in fresh.tools()] == ["echo"]
    assert fresh.running == set()  # 아무것도 띄우지 않았다
    fresh.close()


def test_call_roundtrip(host) -> None:
    host.discover("test")
    result = host.call("test", "echo", {"text": "안녕"})

    assert result.text == "안녕"
    assert result.data == {"echoed": "안녕"}
    assert result.is_error is False


def test_call_spawns_lazily_without_explicit_discover(host) -> None:
    result = host.call("test", "add_numbers", {"a": 2, "b": 3})
    assert result.text == "5.0"


def test_tool_error_is_reported_not_raised(host) -> None:
    host.discover("test")
    result = host.call("test", "explode")
    assert result.is_error is True
    assert "일부러 실패" in result.text


def test_stale_catalog_is_refreshed_before_failing(host, catalog) -> None:
    """캐시가 낡아 도구를 모를 수 있다. 한 번 갱신하고 다시 본다."""
    catalog.replace("test", [ExternalTool("test", "옛도구")])

    result = host.call("test", "echo", {"text": "됨"})

    assert result.text == "됨"


def test_calling_a_tool_that_really_does_not_exist(host) -> None:
    host.discover("test")
    with pytest.raises(McpServerError, match="없습니다"):
        host.call("test", "존재하지않는도구")


def test_unregistered_server_cannot_be_called(host) -> None:
    with pytest.raises(UnknownServer):
        host.call("모르는서버", "echo")


def test_disabled_server_cannot_be_called(catalog) -> None:
    host = McpHost(catalog, {"test": spec(enabled=False)})
    with pytest.raises(UnknownServer, match="비활성화"):
        host.call("test", "echo")
    host.close()


def test_a_server_that_never_speaks_mcp_times_out(catalog) -> None:
    """프로세스로는 뜨지만 MCP로 말하지 않는 서버가 있다.

    (의존성 없는 인터프리터로 실행한 경우 등.) 한계가 없으면 영원히 멈춘다 —
    실제로 겪은 문제다.
    """
    # 정리가 자식 종료를 기다릴 수 있으므로 짧게 자는 명령을 쓴다.
    silent = McpHost(
        catalog,
        {"silent": spec("silent", command="sleep", args=("3",), startup_seconds=1)},
    )
    with pytest.raises(McpServerError, match="MCP 초기화에 응답하지 않았습니다"):
        silent.discover("silent")
    silent.close()


def test_spawn_failure_gives_an_actionable_message(catalog) -> None:
    host = McpHost(catalog, {"broken": spec("broken", command="존재하지-않는-명령")})
    with pytest.raises(McpServerError, match="띄우지 못했습니다"):
        host.discover("broken")
    host.close()


# -- 유휴 종료 ---------------------------------------------------------------


def test_idle_servers_are_shut_down(catalog) -> None:
    """한 번 쓴 서버가 영원히 떠 있으면 지연 기동의 의미가 없다."""
    host = McpHost(catalog, {"test": spec(idle_seconds=60)})
    now = utcnow()
    host.call("test", "echo", {"text": "x"}, now=now)
    assert host.running == {"test"}

    assert host.shutdown_idle(now=now + timedelta(seconds=30)) == []
    assert host.shutdown_idle(now=now + timedelta(seconds=90)) == ["test"]
    assert host.running == set()
    host.close()


def test_calling_again_respawns(host) -> None:
    host.call("test", "echo", {"text": "1"})
    host.stop("test")
    assert host.running == set()

    assert host.call("test", "echo", {"text": "2"}).text == "2"


def test_unregister_stops_and_forgets(host, catalog) -> None:
    host.discover("test")
    host.unregister("test")

    assert host.running == set()
    assert catalog.tools("test") == []
    assert host.servers == {}


# -- 정책 --------------------------------------------------------------------


def test_external_call_requires_confirmation(catalog) -> None:
    """외부 서버는 우리가 만들지 않은 코드다."""
    host = McpHost(catalog, {"test": spec()}, policy=PolicyEngine())
    with pytest.raises(PolicyConfirmationRequired):
        host.call("test", "echo", {"text": "x"})
    host.close()


def test_confirmed_external_call_proceeds(catalog) -> None:
    confirmer = AlwaysConfirm(True)
    host = McpHost(catalog, {"test": spec()}, policy=PolicyEngine(confirmer=confirmer))

    assert host.call("test", "echo", {"text": "x"}).text == "x"
    assert str(confirmer.asked[0]).startswith("mcp.external.test.echo")
    host.close()


def test_trusted_server_needs_no_confirmation(catalog) -> None:
    host = McpHost(catalog, {"test": spec(trusted=True)}, policy=PolicyEngine())
    assert host.call("test", "echo", {"text": "x"}).text == "x"
    host.close()


# -- 도구 선별 ---------------------------------------------------------------


def tool(name: str, description: str = "") -> ExternalTool:
    return ExternalTool("s", name, description)


def test_ranker_prefers_name_matches() -> None:
    ranker = TokenOverlapRanker()
    tools = [
        tool("unrelated", "brief 라는 단어만 설명에 있다"),
        tool("brief", "무언가"),
    ]
    assert [t.name for t in ranker.rank("brief", tools)] == ["brief", "unrelated"]


def test_ranker_drops_irrelevant_tools() -> None:
    ranked = TokenOverlapRanker().rank(
        "browser", [tool("navigate", "browser 제어"), tool("send_email", "메일")]
    )
    assert [t.name for t in ranked] == ["navigate"]


def test_ranker_respects_the_limit() -> None:
    tools = [tool(f"search_{n}", "search") for n in range(30)]
    assert len(TokenOverlapRanker().rank("search", tools, limit=5)) == 5


def test_empty_query_returns_a_stable_slice() -> None:
    tools = [tool("b"), tool("a"), tool("c")]
    assert [t.name for t in TokenOverlapRanker().rank("", tools, limit=2)] == ["a", "b"]


def test_host_ranks_when_listing(catalog) -> None:
    catalog.replace(
        "s",
        [ExternalTool("s", "navigate", "브라우저 이동"), ExternalTool("s", "send_mail", "메일")],
    )
    host = McpHost(catalog, {})
    assert [t.name for t in host.tools("브라우저")] == ["navigate"]
    host.close()
