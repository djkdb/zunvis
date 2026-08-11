"""Outbox의 SQLite 구현.

발행자의 트랜잭션과 같은 커넥션을 쓰기 때문에, 애그리게이트 저장과
이벤트 적재가 원자적으로 함께 커밋된다. "저장은 됐는데 이벤트는 유실"
상황이 구조적으로 생기지 않는다.
"""

from __future__ import annotations

import json
from datetime import datetime

from junvis.core.domain.event import EventEnvelope
from junvis.core.eventbus.bus import OutboxRecord
from junvis.core.persistence.database import Database


class SqliteOutbox:
    def __init__(self, db: Database) -> None:
        self._db = db

    def enqueue(self, topic: str, handler: str, envelope: EventEnvelope) -> None:
        self._db.execute(
            """
            INSERT INTO outbox (topic, handler, payload, occurred_at, next_attempt_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                topic,
                handler,
                json.dumps(envelope.payload, ensure_ascii=False),
                envelope.occurred_at.isoformat(),
                envelope.occurred_at.isoformat(),
            ),
        )

    def fetch_due(self, now: datetime, limit: int) -> list[OutboxRecord]:
        rows = self._db.query(
            """
            SELECT id, topic, handler, payload, occurred_at, attempts
            FROM outbox
            WHERE processed_at IS NULL AND next_attempt_at <= ?
            ORDER BY id
            LIMIT ?
            """,
            (now.isoformat(), limit),
        )
        return [
            OutboxRecord(
                id=row["id"],
                topic=row["topic"],
                handler=row["handler"],
                payload=json.loads(row["payload"]),
                occurred_at=datetime.fromisoformat(row["occurred_at"]),
                attempts=row["attempts"],
            )
            for row in rows
        ]

    def mark_done(self, record_id: int, now: datetime) -> None:
        self._db.execute(
            "UPDATE outbox SET processed_at = ?, attempts = attempts + 1 WHERE id = ?",
            (now.isoformat(), record_id),
        )

    def reschedule(
        self, record_id: int, now: datetime, next_attempt_at: datetime, error: str
    ) -> None:
        self._db.execute(
            """
            UPDATE outbox
            SET attempts = attempts + 1, next_attempt_at = ?, last_error = ?
            WHERE id = ?
            """,
            (next_attempt_at.isoformat(), error, record_id),
        )

    def move_to_deadletter(self, record: OutboxRecord, now: datetime, error: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO deadletter
                    (topic, handler, payload, occurred_at, failed_at, attempts, last_error)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.topic,
                    record.handler,
                    json.dumps(record.payload, ensure_ascii=False),
                    record.occurred_at.isoformat(),
                    now.isoformat(),
                    record.attempts + 1,
                    error,
                ),
            )
            conn.execute("DELETE FROM outbox WHERE id = ?", (record.id,))

    # -- 운영 조회 (Daily Brief가 소비한다) ---------------------------------

    def pending_count(self) -> int:
        row = self._db.query_one("SELECT COUNT(*) AS c FROM outbox WHERE processed_at IS NULL")
        return int(row["c"]) if row else 0

    def deadletter_count(self) -> int:
        row = self._db.query_one("SELECT COUNT(*) AS c FROM deadletter")
        return int(row["c"]) if row else 0
