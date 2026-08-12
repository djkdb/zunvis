"""memory가 발행하는 도메인 이벤트."""

from __future__ import annotations

from dataclasses import dataclass

from junvis.core.domain.event import DomainEvent


@dataclass(frozen=True, kw_only=True)
class MemoryRemembered(DomainEvent):
    topic = "memory.remembered"

    memory_id: str
    text: str
    scope: str
    source: str


@dataclass(frozen=True, kw_only=True)
class MemoryForgotten(DomainEvent):
    topic = "memory.forgotten"

    memory_id: str
    text: str
