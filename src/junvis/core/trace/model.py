"""Trace — 실행 1건의 전 기록.

설계 §5.2: Trace는 로그가 아니라 **개인화의 원재료**다.
자주 쓰는 프롬프트·모델·MCP·작업 시간대·실패 패턴이 전부 여기서 파생된다.
비용과 지연을 1급 필드로 두어 "로컬 우선" 판단의 근거를 남긴다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from junvis.core.domain.event import DomainEvent, utcnow


class Outcome(str, Enum):
    OK = "ok"
    ERROR = "error"
    DENIED = "denied"


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    latency_ms: int = 0
    error: str | None = None


@dataclass
class Trace:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    request: str = ""
    plan: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str | None = None
    tokens: int = 0
    latency_ms: int = 0
    cost: float = 0.0
    outcome: Outcome = Outcome.OK
    user_feedback: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=utcnow)


@dataclass(frozen=True, kw_only=True)
class TraceCompleted(DomainEvent):
    """Trace가 기록될 때마다 발행된다. 개인화 구독자가 여기에 붙는다."""

    topic = "trace.completed"

    trace_id: str
    request: str
    outcome: str
    model: str | None
    latency_ms: int
    tool_names: tuple[str, ...]


class TraceStore(Protocol):
    def save(self, trace: Trace) -> None: ...

    def recent(self, limit: int = 20) -> list[Trace]: ...
