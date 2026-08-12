"""MCP Host — JUNVIS가 외부 MCP 서버를 도구로 쓴다.

설계 §6의 약속을 여기서 지킨다: 지연 기동, 유휴 종료, 도구 선별, 정책 게이트.

동기/비동기 경계: MCP 클라이언트는 비동기지만 JUNVIS의 유스케이스는 동기다.
`anyio`의 블로킹 포털로 배경 스레드에 이벤트 루프 하나를 띄우고, 그 위에서
세션을 유지한다. 호출자는 비동기를 전혀 모른다.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from anyio.from_thread import start_blocking_portal

from junvis.core.domain.errors import JunvisError
from junvis.core.domain.event import utcnow
from junvis.core.mcp.catalog import ExternalTool, ToolCatalog
from junvis.core.mcp.config import ServerSpec
from junvis.core.mcp.ranking import DEFAULT_LIMIT, ToolRankerPort, TokenOverlapRanker
from junvis.core.policy.engine import PolicyEngine

logger = logging.getLogger(__name__)


class McpServerError(JunvisError):
    """외부 서버를 띄우거나 부르지 못했다."""


class UnknownServer(JunvisError):
    """등록되지 않은 서버. 설정에 없는 것은 쓸 수 없다."""


@dataclass(frozen=True)
class ToolCallResult:
    server_id: str
    tool: str
    text: str = ""
    data: dict[str, Any] | None = None
    is_error: bool = False


@dataclass
class _LiveServer:
    """떠 있는 서버 하나. 유휴 종료를 위해 마지막 사용 시각을 들고 있다."""

    spec: ServerSpec
    session: Any
    stdio_cm: Any
    session_cm: Any
    last_used_at: datetime
    tool_names: set[str] = field(default_factory=set)
    errlog: Any = None


class McpHost:
    def __init__(
        self,
        catalog: ToolCatalog,
        servers: dict[str, ServerSpec] | None = None,
        *,
        policy: PolicyEngine | None = None,
        ranker: ToolRankerPort | None = None,
        log_dir: Path | None = None,
    ) -> None:
        self._catalog = catalog
        self._servers = dict(servers or {})
        self._policy = policy
        self._ranker = ranker or TokenOverlapRanker()
        self._log_dir = Path(log_dir) if log_dir else None
        self._live: dict[str, _LiveServer] = {}
        self._portal = None
        self._portal_cm = None

    # -- 등록 ---------------------------------------------------------------

    @property
    def servers(self) -> dict[str, ServerSpec]:
        return dict(self._servers)

    def register(self, spec: ServerSpec) -> None:
        self._servers[spec.id] = spec

    def unregister(self, server_id: str) -> None:
        self.stop(server_id)
        self._servers.pop(server_id, None)
        self._catalog.forget(server_id)

    def _spec(self, server_id: str) -> ServerSpec:
        spec = self._servers.get(server_id)
        if spec is None:
            known = ", ".join(sorted(self._servers)) or "없음"
            raise UnknownServer(
                f"등록되지 않은 서버입니다: {server_id} (등록된 서버: {known})"
            )
        if not spec.enabled:
            raise UnknownServer(f"비활성화된 서버입니다: {server_id}")
        return spec

    # -- 도구 목록 ----------------------------------------------------------

    def discover(self, server_id: str, *, now: datetime | None = None) -> list[ExternalTool]:
        """서버를 띄워 도구 목록을 받아 캐시에 저장한다."""
        spec = self._spec(server_id)
        live = self._ensure(spec, now=now)
        result = self._portal.call(live.session.list_tools)
        tools = [
            ExternalTool(
                server_id=spec.id,
                name=tool.name,
                description=tool.description or "",
                input_schema=_schema_of(tool),
            )
            for tool in result.tools
        ]
        live.tool_names = {tool.name for tool in tools}
        self._catalog.replace(spec.id, tools, now=now)
        return tools

    def tools(
        self, query: str = "", *, limit: int = DEFAULT_LIMIT, server_id: str | None = None
    ) -> list[ExternalTool]:
        """캐시에서 답한다. 서버를 띄우지 않는다."""
        cached = self._catalog.tools(server_id)
        return self._ranker.rank(query, cached, limit=limit)

    def refresh_all(self, *, now: datetime | None = None) -> dict[str, int]:
        """등록된 모든 서버의 카탈로그를 다시 만든다. 사용자가 명시적으로 부른다."""
        counts: dict[str, int] = {}
        for server_id, spec in self._servers.items():
            if not spec.enabled:
                continue
            try:
                counts[server_id] = len(self.discover(server_id, now=now))
            except JunvisError as exc:
                logger.warning("카탈로그 갱신 실패(%s): %s", server_id, exc)
                counts[server_id] = -1
        return counts

    # -- 호출 ---------------------------------------------------------------

    def call(
        self,
        server_id: str,
        tool: str,
        arguments: dict[str, Any] | None = None,
        *,
        now: datetime | None = None,
    ) -> ToolCallResult:
        spec = self._spec(server_id)
        if self._policy is not None:
            # 신뢰하는 서버는 등급이 낮다. 그 판단은 사용자가 설정에서 내린다.
            prefix = "mcp.trusted" if spec.trusted else "mcp.external"
            self._policy.guard(f"{prefix}.{server_id}.{tool}", tool, server=server_id)

        live = self._ensure(spec, now=now)
        if live.tool_names and tool not in live.tool_names:
            # 캐시가 낡았을 수 있다. 한 번 갱신하고 다시 본다.
            self.discover(server_id, now=now)
            live = self._live[server_id]
            if tool not in live.tool_names:
                raise McpServerError(f"'{server_id}'에 '{tool}' 도구가 없습니다")

        live.last_used_at = now or utcnow()
        try:
            result = self._portal.call(
                lambda: live.session.call_tool(tool, arguments or {})
            )
        except Exception as exc:
            raise McpServerError(f"'{server_id}.{tool}' 호출 실패: {exc}") from exc

        return ToolCallResult(
            server_id=server_id,
            tool=tool,
            text=_text_of(result),
            data=getattr(result, "structured_content", None),
            is_error=bool(getattr(result, "is_error", False)),
        )

    # -- 수명 관리 ----------------------------------------------------------

    def _ensure(self, spec: ServerSpec, *, now: datetime | None = None) -> _LiveServer:
        live = self._live.get(spec.id)
        if live is not None:
            live.last_used_at = now or utcnow()
            return live
        return self._spawn(spec, now=now)

    def _spawn(self, spec: ServerSpec, *, now: datetime | None = None) -> _LiveServer:
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        portal = self._ensure_portal()
        params = StdioServerParameters(
            command=spec.command,
            args=list(spec.args),
            env={**spec.resolved_env()} or None,
            cwd=spec.cwd,
        )
        errlog = self._open_errlog(spec.id)
        try:
            stdio_cm = portal.wrap_async_context_manager(stdio_client(params, errlog))
            read, write = stdio_cm.__enter__()
            session_cm = portal.wrap_async_context_manager(ClientSession(read, write))
            session = session_cm.__enter__()
            portal.call(session.initialize)
        except Exception as exc:
            errlog.close()
            hint = f" (로그: {self._log_path(spec.id)})" if self._log_dir else ""
            raise McpServerError(
                f"'{spec.id}' 서버를 띄우지 못했습니다 ({spec.command}): {exc}{hint}"
            ) from exc

        live = _LiveServer(
            spec=spec,
            session=session,
            stdio_cm=stdio_cm,
            session_cm=session_cm,
            last_used_at=now or utcnow(),
            tool_names={tool.name for tool in self._catalog.tools(spec.id)},
            errlog=errlog,
        )
        self._live[spec.id] = live
        logger.debug("MCP 서버 기동: %s", spec.id)
        return live

    def stop(self, server_id: str) -> bool:
        live = self._live.pop(server_id, None)
        if live is None:
            return False
        for manager in (live.session_cm, live.stdio_cm):
            try:
                manager.__exit__(None, None, None)
            except Exception as exc:  # pragma: no cover - 종료 실패는 치명적이지 않다
                logger.debug("서버 종료 중 오류(%s): %s", server_id, exc)
        if live.errlog is not None:
            live.errlog.close()
        logger.debug("MCP 서버 종료: %s", server_id)
        return True

    def shutdown_idle(self, *, now: datetime | None = None) -> list[str]:
        """유휴 서버를 내린다.

        부팅 시 전체 기동을 막는 것만으로는 부족하다. 한 번 쓴 서버가
        영원히 떠 있으면 결국 같은 자리에 도달한다.
        """
        moment = now or utcnow()
        stopped = []
        for server_id, live in list(self._live.items()):
            if moment - live.last_used_at >= timedelta(seconds=live.spec.idle_seconds):
                self.stop(server_id)
                stopped.append(server_id)
        return stopped

    @property
    def running(self) -> set[str]:
        return set(self._live)

    def close(self) -> None:
        for server_id in list(self._live):
            self.stop(server_id)
        if self._portal_cm is not None:
            try:
                self._portal_cm.__exit__(None, None, None)
            except Exception:  # pragma: no cover - 방어적
                pass
            self._portal = None
            self._portal_cm = None

    def _log_path(self, server_id: str) -> Path | None:
        return self._log_dir / f"mcp-{server_id}.log" if self._log_dir else None

    def _open_errlog(self, server_id: str):
        """서버의 stderr를 파일로 보낸다.

        두 가지를 동시에 해결한다. ① 서버가 왜 죽었는지 나중에 볼 수 있다.
        ② `sys.stderr`를 그대로 넘기면 그것이 진짜 파일이 아닐 때
        (pytest의 capsys, MCP 서버 모드 등) `fileno()`가 없어 기동이 실패한다.
        """
        path = self._log_path(server_id)
        if path is None:
            return open(os.devnull, "w", encoding="utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        return open(path, "a", encoding="utf-8")

    def _ensure_portal(self):
        """비동기 세션을 유지할 이벤트 루프를 배경 스레드에 하나만 둔다."""
        if self._portal is None:
            self._portal_cm = start_blocking_portal()
            self._portal = self._portal_cm.__enter__()
        return self._portal


def _schema_of(tool) -> dict[str, Any]:
    schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None)
    return dict(schema) if isinstance(schema, dict) else {}


def _text_of(result) -> str:
    blocks = getattr(result, "content", None) or []
    return "\n".join(
        block.text for block in blocks if getattr(block, "text", None)
    )
