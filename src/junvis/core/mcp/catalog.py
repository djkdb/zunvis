"""도구 카탈로그 캐시.

"부팅 시 전체 서버 기동 금지"와 "어떤 도구가 있는지 알아야 한다"는 충돌한다.
서버를 띄우지 않으면 도구 목록을 모르기 때문이다. 그래서 처음 한 번만 띄워
목록을 받아 두고, 이후 조회는 캐시에서 답한다(docs/07-MCP-HOST.md §2).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from junvis.core.domain.event import utcnow
from junvis.core.persistence.database import Database


@dataclass(frozen=True)
class ExternalTool:
    server_id: str
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)

    @property
    def qualified_name(self) -> str:
        """서버가 달라도 도구 이름이 겹칠 수 있다."""
        return f"{self.server_id}.{self.name}"

    @property
    def searchable(self) -> str:
        return f"{self.name} {self.description}"


class ToolCatalog:
    def __init__(self, db: Database) -> None:
        self._db = db

    def replace(self, server_id: str, tools: list[ExternalTool], *, now: datetime | None = None) -> None:
        moment = now or utcnow()
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM mcp_tools WHERE server_id = ?", (server_id,))
            conn.executemany(
                """
                INSERT INTO mcp_tools
                    (server_id, name, description, input_schema, discovered_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        tool.server_id,
                        tool.name,
                        tool.description,
                        json.dumps(tool.input_schema, ensure_ascii=False),
                        moment.isoformat(),
                    )
                    for tool in tools
                ],
            )

    def forget(self, server_id: str) -> None:
        self._db.execute("DELETE FROM mcp_tools WHERE server_id = ?", (server_id,))

    def tools(self, server_id: str | None = None) -> list[ExternalTool]:
        if server_id is None:
            rows = self._db.query("SELECT * FROM mcp_tools ORDER BY server_id, name")
        else:
            rows = self._db.query(
                "SELECT * FROM mcp_tools WHERE server_id = ? ORDER BY name", (server_id,)
            )
        return [self._hydrate(row) for row in rows]

    def find(self, server_id: str, name: str) -> ExternalTool | None:
        row = self._db.query_one(
            "SELECT * FROM mcp_tools WHERE server_id = ? AND name = ?", (server_id, name)
        )
        return self._hydrate(row) if row else None

    def known_servers(self) -> set[str]:
        return {row["server_id"] for row in self._db.query("SELECT DISTINCT server_id FROM mcp_tools")}

    def discovered_at(self, server_id: str) -> datetime | None:
        row = self._db.query_one(
            "SELECT MAX(discovered_at) AS at FROM mcp_tools WHERE server_id = ?",
            (server_id,),
        )
        return datetime.fromisoformat(row["at"]) if row and row["at"] else None

    @staticmethod
    def _hydrate(row) -> ExternalTool:
        return ExternalTool(
            server_id=row["server_id"],
            name=row["name"],
            description=row["description"],
            input_schema=json.loads(row["input_schema"]),
        )
