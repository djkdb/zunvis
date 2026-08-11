"""Trace의 SQLite 저장소."""

from __future__ import annotations

import json
from datetime import datetime

from junvis.core.domain.event import jsonable
from junvis.core.persistence.database import Database
from junvis.core.trace.model import Outcome, ToolCall, Trace


class SqliteTraceStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def save(self, trace: Trace) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO traces
                (id, request, plan, tool_calls, model, tokens, latency_ms,
                 cost, outcome, user_feedback, context, occurred_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace.id,
                trace.request,
                trace.plan,
                json.dumps(jsonable(trace.tool_calls), ensure_ascii=False),
                trace.model,
                trace.tokens,
                trace.latency_ms,
                trace.cost,
                trace.outcome.value,
                trace.user_feedback,
                json.dumps(jsonable(trace.context), ensure_ascii=False),
                trace.occurred_at.isoformat(),
            ),
        )

    def recent(self, limit: int = 20) -> list[Trace]:
        rows = self._db.query(
            "SELECT * FROM traces ORDER BY occurred_at DESC LIMIT ?", (limit,)
        )
        return [self._to_trace(row) for row in rows]

    @staticmethod
    def _to_trace(row) -> Trace:
        return Trace(
            id=row["id"],
            request=row["request"],
            plan=row["plan"],
            tool_calls=[ToolCall(**call) for call in json.loads(row["tool_calls"])],
            model=row["model"],
            tokens=row["tokens"],
            latency_ms=row["latency_ms"],
            cost=row["cost"],
            outcome=Outcome(row["outcome"]),
            user_feedback=row["user_feedback"],
            context=json.loads(row["context"]),
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
        )
