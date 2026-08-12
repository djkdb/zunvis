"""외부 MCP 서버 설정.

Claude Code와 같은 `mcpServers` 모양을 쓴다. 익숙한 형식을 두고 새 형식을
만들 이유가 없고, 사용자가 이미 가진 설정을 그대로 옮길 수 있다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from junvis.core.domain.errors import JunvisError

CONFIG_FILENAME = "mcp.json"

#: 마지막 호출 뒤 이만큼 지나면 서버 프로세스를 내린다.
DEFAULT_IDLE_SECONDS = 300

#: 기동 후 MCP 초기화까지 기다리는 한계.
#: 잘못 설정된 서버가 프로세스로는 뜨지만 MCP로 말하지 않는 경우가 있다
#: (예: 의존성이 없는 파이썬으로 실행). 이 한계가 없으면 영원히 멈춘다.
DEFAULT_STARTUP_SECONDS = 30

#: 도구 하나의 실행 한계. 브라우저 조작처럼 느린 작업이 있어 넉넉히 잡는다.
DEFAULT_CALL_SECONDS = 120


class McpConfigError(JunvisError):
    """설정 파일을 읽을 수 없거나 형식이 맞지 않는다."""


@dataclass(frozen=True)
class ServerSpec:
    id: str
    command: str
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None
    #: 신뢰하는 서버의 호출은 확인 없이 통과한다(정책 등급을 낮춘다).
    trusted: bool = False
    enabled: bool = True
    idle_seconds: int = DEFAULT_IDLE_SECONDS
    startup_seconds: int = DEFAULT_STARTUP_SECONDS
    call_seconds: int = DEFAULT_CALL_SECONDS

    def resolved_env(self) -> dict[str, str]:
        """빈 값은 현재 환경에서 채운다.

        설정 파일에 API 키를 적지 않고 `{"OPENAI_API_KEY": ""}`처럼 이름만
        선언해 두면, 실행 시 환경변수에서 가져온다.
        """
        resolved = {}
        for key, value in self.env.items():
            resolved[key] = value or os.environ.get(key, "")
        return resolved

    def to_json(self) -> dict:
        payload: dict = {"command": self.command}
        if self.args:
            payload["args"] = list(self.args)
        if self.env:
            payload["env"] = dict(self.env)
        if self.cwd:
            payload["cwd"] = self.cwd
        if self.trusted:
            payload["trusted"] = True
        if not self.enabled:
            payload["enabled"] = False
        if self.idle_seconds != DEFAULT_IDLE_SECONDS:
            payload["idleSeconds"] = self.idle_seconds
        if self.startup_seconds != DEFAULT_STARTUP_SECONDS:
            payload["startupSeconds"] = self.startup_seconds
        if self.call_seconds != DEFAULT_CALL_SECONDS:
            payload["callSeconds"] = self.call_seconds
        return payload

    @staticmethod
    def from_json(server_id: str, payload: dict) -> ServerSpec:
        command = payload.get("command")
        if not command:
            raise McpConfigError(f"'{server_id}' 서버에 command가 없습니다")
        return ServerSpec(
            id=server_id,
            command=str(command),
            args=tuple(str(a) for a in payload.get("args", ())),
            env={str(k): str(v) for k, v in (payload.get("env") or {}).items()},
            cwd=payload.get("cwd"),
            trusted=bool(payload.get("trusted", False)),
            enabled=bool(payload.get("enabled", True)),
            idle_seconds=int(payload.get("idleSeconds", DEFAULT_IDLE_SECONDS)),
            startup_seconds=int(payload.get("startupSeconds", DEFAULT_STARTUP_SECONDS)),
            call_seconds=int(payload.get("callSeconds", DEFAULT_CALL_SECONDS)),
        )


class McpConfig:
    """`~/.junvis/mcp.json`을 읽고 쓴다."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> dict[str, ServerSpec]:
        if not self._path.is_file():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise McpConfigError(f"{self._path}를 읽지 못했습니다: {exc}") from exc
        servers = raw.get("mcpServers")
        if not isinstance(servers, dict):
            return {}
        return {
            server_id: ServerSpec.from_json(server_id, payload)
            for server_id, payload in servers.items()
            if isinstance(payload, dict)
        }

    def save(self, servers: dict[str, ServerSpec]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "mcpServers": {spec.id: spec.to_json() for spec in servers.values()}
        }
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def add(self, spec: ServerSpec) -> None:
        servers = self.load()
        servers[spec.id] = spec
        self.save(servers)

    def remove(self, server_id: str) -> bool:
        servers = self.load()
        if server_id not in servers:
            return False
        del servers[server_id]
        self.save(servers)
        return True
