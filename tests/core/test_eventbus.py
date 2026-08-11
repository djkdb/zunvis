"""M3 완료 기준: 프로세스가 죽어도 비동기 이벤트가 유실되지 않는다."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pytest

from junvis.core.domain.event import DomainEvent, utcnow
from junvis.core.eventbus.bus import Delivery, EventBus
from junvis.core.eventbus.outbox import SqliteOutbox
from junvis.core.persistence import CORE_MIGRATIONS, Database


@dataclass(frozen=True, kw_only=True)
class Ping(DomainEvent):
    topic = "test.ping"
    note: str


def test_sync_handler_runs_immediately(bus: EventBus) -> None:
    seen = []
    bus.subscribe("test.ping", lambda env: seen.append(env.payload["note"]))

    bus.publish(Ping(note="안녕"))

    assert seen == ["안녕"]


def test_sync_handler_failure_propagates_to_publisher(bus: EventBus) -> None:
    def explode(_env):
        raise RuntimeError("동기 구독자 실패")

    bus.subscribe("test.ping", explode)

    # 동기 구독자는 발행자와 운명을 같이한다 → 트랜잭션이 함께 롤백된다.
    with pytest.raises(RuntimeError):
        bus.publish(Ping(note="x"))


def test_async_handler_does_not_run_until_drain(bus: EventBus) -> None:
    seen = []
    bus.subscribe("test.ping", lambda env: seen.append(env.payload["note"]), mode=Delivery.ASYNC)

    bus.publish(Ping(note="나중에"))
    assert seen == []

    report = bus.drain()
    assert seen == ["나중에"]
    assert report.processed == 1


def test_pattern_matching(bus: EventBus) -> None:
    prefix, exact, everything = [], [], []
    bus.subscribe("test.*", lambda e: prefix.append(e.topic), name="prefix")
    bus.subscribe("test.ping", lambda e: exact.append(e.topic), name="exact")
    bus.subscribe("*", lambda e: everything.append(e.topic), name="all")

    bus.publish(Ping(note="a"))

    assert prefix == exact == everything == ["test.ping"]


def test_outbox_survives_process_restart(tmp_path) -> None:
    """M3 완료 기준의 핵심: 파일 DB에 적재된 뒤 프로세스가 죽어도 남는다."""
    path = tmp_path / "junvis.db"

    first = Database(path)
    first.migrate(CORE_MIGRATIONS)
    bus = EventBus(SqliteOutbox(first))
    bus.subscribe("test.ping", lambda e: None, mode=Delivery.ASYNC, name="worker")
    bus.publish(Ping(note="살아남아라"))
    first.close()  # 프로세스 종료를 흉내낸다

    second = Database(path)
    second.migrate(CORE_MIGRATIONS)
    revived = EventBus(SqliteOutbox(second))
    seen = []
    revived.subscribe(
        "test.ping", lambda e: seen.append(e.payload["note"]), mode=Delivery.ASYNC, name="worker"
    )

    assert revived.drain().processed == 1
    assert seen == ["살아남아라"]
    second.close()


def test_failing_async_handler_retries_then_deadletters(bus: EventBus, outbox: SqliteOutbox) -> None:
    def always_fails(_env):
        raise RuntimeError("계속 실패")

    bus.subscribe("test.ping", always_fails, mode=Delivery.ASYNC, name="flaky")
    bus.publish(Ping(note="x"))

    now = utcnow()
    # 1·2회차는 백오프 뒤 재시도, 3회차에서 deadletter로 간다.
    assert bus.drain(now=now).failed == 1
    assert bus.drain(now=now + timedelta(seconds=5)).failed == 1
    assert bus.drain(now=now + timedelta(seconds=30)).deadlettered == 1

    assert outbox.pending_count() == 0
    assert outbox.deadletter_count() == 1


def test_backoff_delays_retry(bus: EventBus) -> None:
    bus.subscribe(
        "test.ping",
        lambda e: (_ for _ in ()).throw(RuntimeError("실패")),
        mode=Delivery.ASYNC,
        name="flaky",
    )
    bus.publish(Ping(note="x"))
    now = utcnow()

    bus.drain(now=now)
    # 백오프(2초)가 지나기 전에는 다시 집어가지 않는다.
    assert bus.drain(now=now + timedelta(seconds=1)).total == 0


def test_orphaned_subscription_goes_to_deadletter(db: Database, outbox: SqliteOutbox) -> None:
    bus = EventBus(outbox)
    bus.subscribe("test.ping", lambda e: None, mode=Delivery.ASYNC, name="사라질구독자")
    bus.publish(Ping(note="x"))

    # 구독자가 없어진 새 프로세스
    fresh = EventBus(outbox)
    assert fresh.drain().deadlettered == 1


def test_duplicate_subscription_name_rejected(bus: EventBus) -> None:
    bus.subscribe("test.ping", lambda e: None, name="dup")
    with pytest.raises(ValueError):
        bus.subscribe("test.other", lambda e: None, name="dup")


def test_async_subscription_requires_outbox() -> None:
    with pytest.raises(ValueError):
        EventBus().subscribe("test.ping", lambda e: None, mode=Delivery.ASYNC)
