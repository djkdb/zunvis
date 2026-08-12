"""memory 유스케이스가 주고받는 자료구조."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from junvis.features.memory.domain.model import MemoryEntry


@dataclass(frozen=True)
class MemoryView:
    id: str
    text: str
    scope: str
    subject: str
    tags: tuple[str, ...]
    source: str
    pinned: bool
    created_at: datetime
    recall_count: int
    score: float = 0.0

    @property
    def short_id(self) -> str:
        return self.id[:8]

    @classmethod
    def of(cls, entry: MemoryEntry, score: float = 0.0) -> MemoryView:
        return cls(
            id=entry.id,
            text=entry.text,
            scope=entry.scope.value,
            subject=entry.subject,
            tags=entry.tags,
            source=entry.source,
            pinned=entry.pinned,
            created_at=entry.created_at,
            recall_count=entry.recall_count,
            score=score,
        )
