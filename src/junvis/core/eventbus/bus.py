"""Event Bus — feature 간 결합을 끊는 유일한 통로.

설계 근거(docs/02-ARCHITECTURE.md §3):
`project_brain`은 `creator`의 존재를 몰라야 한다. 새 기능은 구독자를
추가해서 붙이고 기존 코드는 건드리지 않는다(OCP).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Protocol

from junvis.core.domain.event import DomainEvent, EventEnvelope, utcnow

logger = logging.getLogger(__name__)

Handler = Callable[[EventEnvelope], None]

MAX_ATTEMPTS = 3


class Delivery(str, Enum):
    """전달 모드.

    SYNC  — 같은 트랜잭션 안에서 즉시. 실패하면 발행자와 함께 롤백된다.
    ASYNC — Outbox에 기록 후 워커가 처리. 프로세스가 죽어도 유실되지 않는다.
    """

    SYNC = "sync"
    ASYNC = "async"


@dataclass(frozen=True)
class Subscription:
    name: str
    pattern: str
    handler: Handler
    mode: Delivery

    def matches(self, topic: str) -> bool:
        if self.pattern == "*":
            return True
        if self.pattern.endswith(".*"):
            return topic.startswith(self.pattern[:-1])
        return self.pattern == topic


@dataclass(frozen=True)
class OutboxRecord:
    id: int
    topic: str
    handler: str
    payload: dict[str, Any]
    occurred_at: datetime
    attempts: int


class OutboxPort(Protocol):
    """비동기 전달의 내구성 저장소. 버스는 SQLite를 모른다."""

    def enqueue(self, topic: str, handler: str, envelope: EventEnvelope) -> None: ...

    def fetch_due(self, now: datetime, limit: int) -> list[OutboxRecord]: ...

    def mark_done(self, record_id: int, now: datetime) -> None: ...

    def reschedule(
        self, record_id: int, now: datetime, next_attempt_at: datetime, error: str
    ) -> None: ...

    def move_to_deadletter(self, record: OutboxRecord, now: datetime, error: str) -> None: ...


@dataclass
class DrainReport:
    processed: int = 0
    failed: int = 0
    deadlettered: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.processed + self.failed + self.deadlettered


class EventBus:
    """발행-구독. 동기 구독자는 즉시, 비동기 구독자는 Outbox를 거친다."""

    def __init__(self, outbox: OutboxPort | None = None) -> None:
        self._subscriptions: list[Subscription] = []
        self._outbox = outbox

    def subscribe(
        self,
        pattern: str,
        handler: Handler,
        *,
        mode: Delivery = Delivery.SYNC,
        name: str | None = None,
    ) -> Subscription:
        """`pattern`은 정확 일치, `project.*` 접두 일치, 또는 `*` 전체."""
        resolved = name or f"{getattr(handler, '__name__', 'handler')}@{pattern}"
        if any(s.name == resolved for s in self._subscriptions):
            raise ValueError(f"구독자 이름이 중복됩니다: {resolved}")
        if mode is Delivery.ASYNC and self._outbox is None:
            raise ValueError("ASYNC 구독에는 Outbox가 필요합니다")
        subscription = Subscription(resolved, pattern, handler, mode)
        self._subscriptions.append(subscription)
        return subscription

    def publish(self, event: DomainEvent) -> None:
        self.publish_envelope(EventEnvelope.of(event))

    def publish_envelope(self, envelope: EventEnvelope) -> None:
        """동기 구독자를 즉시 실행하고, 비동기 구독자는 Outbox에 적재한다.

        비동기는 구독자마다 한 행씩 쌓는다. 한 구독자의 실패가 다른
        구독자의 재시도에 영향을 주지 않도록 하기 위해서다.
        """
        for subscription in self._subscriptions:
            if not subscription.matches(envelope.topic):
                continue
            if subscription.mode is Delivery.SYNC:
                subscription.handler(envelope)
            else:
                assert self._outbox is not None  # subscribe()에서 보장
                self._outbox.enqueue(envelope.topic, subscription.name, envelope)

    def drain(self, limit: int = 100, *, now: datetime | None = None) -> DrainReport:
        """Outbox를 소비한다. 데몬 워커와 테스트가 같은 경로를 쓴다."""
        report = DrainReport()
        if self._outbox is None:
            return report
        moment = now or utcnow()
        for record in self._outbox.fetch_due(moment, limit):
            subscription = self._find(record.handler)
            if subscription is None:
                # 구독자가 사라진 이벤트를 영원히 재시도하지 않는다.
                self._outbox.move_to_deadletter(record, moment, "구독자를 찾을 수 없음")
                report.deadlettered += 1
                continue
            envelope = EventEnvelope(record.topic, record.payload, record.occurred_at)
            try:
                subscription.handler(envelope)
            except Exception as exc:  # 구독자 하나가 워커 전체를 죽이지 않는다
                attempts = record.attempts + 1
                message = f"{type(exc).__name__}: {exc}"
                report.errors.append(f"{record.handler}: {message}")
                if attempts >= MAX_ATTEMPTS:
                    self._outbox.move_to_deadletter(record, moment, message)
                    report.deadlettered += 1
                    logger.error("이벤트를 deadletter로 옮김: %s (%s)", record.handler, message)
                else:
                    backoff = timedelta(seconds=2**attempts)
                    self._outbox.reschedule(record.id, moment, moment + backoff, message)
                    report.failed += 1
            else:
                self._outbox.mark_done(record.id, moment)
                report.processed += 1
        return report

    def _find(self, name: str) -> Subscription | None:
        return next((s for s in self._subscriptions if s.name == name), None)
