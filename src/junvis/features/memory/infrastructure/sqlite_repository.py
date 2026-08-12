"""MemoryRepository의 SQLite + FTS5 구현.

Mem0를 기본으로 쓰지 않는 이유는 docs/06-MEMORY.md §0에 있다. 요점은
"한 줄을 기억시키려고 벡터 DB를 세우라는 것은 로컬 우선이 아니다"이다.
의미 검색이 필요해지면 이 클래스를 대체하는 어댑터를 하나 더 만들면 된다 —
`MemoryRepository`가 그 이음매다.
"""

from __future__ import annotations

import json
from datetime import datetime

from junvis.core.persistence.database import Database
from junvis.core.persistence.fts import fts_expression
from junvis.features.memory.domain.model import (
    MemoryEntry,
    MemoryHit,
    MemoryScope,
    Recall,
)
from junvis.features.memory.domain.repository import MemoryRepository


#: 관련도를 이 범위로 정규화한다. 최근성·고정 보정과 섞일 수 있는 크기여야 한다.
RELEVANCE_MIN = 0.5
RELEVANCE_MAX = 1.5


class SqliteMemoryRepository(MemoryRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    # -- 쓰기 ---------------------------------------------------------------

    def add(self, entry: MemoryEntry) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO memories
                    (id, text, normalized, scope, subject, tags, source, pinned,
                     created_at, last_recalled_at, recall_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._row(entry),
            )
            self._index(conn, entry)

    def update(self, entry: MemoryEntry) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """
                UPDATE memories
                SET text = ?, normalized = ?, scope = ?, subject = ?, tags = ?,
                    source = ?, pinned = ?, last_recalled_at = ?, recall_count = ?
                WHERE id = ?
                """,
                (
                    entry.text,
                    entry.normalized,
                    entry.scope.value,
                    entry.subject,
                    json.dumps(list(entry.tags), ensure_ascii=False),
                    entry.source,
                    int(entry.pinned),
                    entry.last_recalled_at.isoformat() if entry.last_recalled_at else None,
                    entry.recall_count,
                    entry.id,
                ),
            )
            conn.execute("DELETE FROM memory_search WHERE memory_id = ?", (entry.id,))
            self._index(conn, entry)

    def remove(self, entry_id: str) -> bool:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM memory_search WHERE memory_id = ?", (entry_id,))
            cursor = conn.execute("DELETE FROM memories WHERE id = ?", (entry_id,))
        return cursor.rowcount > 0

    @staticmethod
    def _row(entry: MemoryEntry) -> tuple:
        return (
            entry.id,
            entry.text,
            entry.normalized,
            entry.scope.value,
            entry.subject,
            json.dumps(list(entry.tags), ensure_ascii=False),
            entry.source,
            int(entry.pinned),
            entry.created_at.isoformat(),
            entry.last_recalled_at.isoformat() if entry.last_recalled_at else None,
            entry.recall_count,
        )

    @staticmethod
    def _index(conn, entry: MemoryEntry) -> None:
        conn.execute(
            """
            INSERT INTO memory_search (text, tags, subject, memory_id)
            VALUES (?, ?, ?, ?)
            """,
            (entry.text, " ".join(entry.tags), entry.subject, entry.id),
        )

    # -- 읽기 ---------------------------------------------------------------

    def get(self, entry_id: str) -> MemoryEntry | None:
        row = self._db.query_one("SELECT * FROM memories WHERE id = ?", (entry_id,))
        return self._hydrate(row) if row else None

    def find_similar(self, normalized_text: str) -> MemoryEntry | None:
        row = self._db.query_one(
            "SELECT * FROM memories WHERE normalized = ?", (normalized_text,)
        )
        return self._hydrate(row) if row else None

    def all(self, *, limit: int = 100) -> list[MemoryEntry]:
        rows = self._db.query(
            "SELECT * FROM memories ORDER BY pinned DESC, created_at DESC LIMIT ?",
            (limit,),
        )
        return [self._hydrate(row) for row in rows]

    def search(self, recall: Recall) -> list[MemoryHit]:
        expression = fts_expression(recall.query)
        if expression is None:
            return self._browse(recall)
        return self._match(recall, expression)

    def _browse(self, recall: Recall) -> list[MemoryHit]:
        """질의가 없으면 스코프 안의 최근 기억을 돌려준다.

        콘텐츠 생성처럼 "이 스코프의 규칙을 전부 달라"는 요청이 흔하다.
        """
        clauses, params = self._scope_clauses(recall)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.query(
            f"""
            SELECT * FROM memories {where}
            ORDER BY pinned DESC, created_at DESC LIMIT ?
            """,
            (*params, recall.limit),
        )
        return [MemoryHit(self._hydrate(row), 1.0) for row in rows]

    def _match(self, recall: Recall, expression: str) -> list[MemoryHit]:
        clauses, params = self._scope_clauses(recall, prefix="m.")
        extra = f" AND {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.query(
            f"""
            SELECT m.*, bm25(memory_search) AS bm
            FROM memory_search s
            JOIN memories m ON m.id = s.memory_id
            WHERE memory_search MATCH ?{extra}
            ORDER BY bm
            LIMIT ?
            """,
            (expression, *params, recall.limit),
        )
        scores = [float(row["bm"]) for row in rows]
        relevances = _normalize_bm25(scores)
        return [
            MemoryHit(self._hydrate(row), relevance)
            for row, relevance in zip(rows, relevances)
        ]

    @staticmethod
    def _scope_clauses(recall: Recall, prefix: str = "") -> tuple[list[str], list]:
        clauses: list[str] = []
        params: list = []
        if recall.scope is not None:
            clauses.append(f"{prefix}scope = ?")
            params.append(recall.scope.value)
        if recall.subject:
            clauses.append(f"{prefix}subject = ?")
            params.append(recall.subject)
        return clauses, params


    @staticmethod
    def _hydrate(row) -> MemoryEntry:
        return MemoryEntry(
            id=row["id"],
            text=row["text"],
            scope=MemoryScope(row["scope"]),
            subject=row["subject"],
            tags=tuple(json.loads(row["tags"])),
            source=row["source"],
            pinned=bool(row["pinned"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            last_recalled_at=(
                datetime.fromisoformat(row["last_recalled_at"])
                if row["last_recalled_at"]
                else None
            ),
            recall_count=row["recall_count"],
        )


def _normalize_bm25(scores: list[float]) -> list[float]:
    """SQLite의 bm25()는 작을수록(더 음수일수록) 좋은 점수다.

    절대값의 크기가 질의마다 달라 그대로 쓰면 최근성 보정과 섞이지 않는다.
    그래서 결과 집합 안에서 [RELEVANCE_MIN, RELEVANCE_MAX]로 편다.
    """
    if not scores:
        return []
    best, worst = min(scores), max(scores)
    if best == worst:
        return [RELEVANCE_MAX] * len(scores)
    span = worst - best
    return [
        RELEVANCE_MAX - (score - best) / span * (RELEVANCE_MAX - RELEVANCE_MIN)
        for score in scores
    ]
