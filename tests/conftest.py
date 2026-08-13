from __future__ import annotations

import pytest

from junvis.core.eventbus.bus import EventBus
from junvis.core.eventbus.outbox import SqliteOutbox
from junvis.core.persistence import CORE_MIGRATIONS, MEMORY, Database
from junvis.features.creator.infrastructure import CREATOR_MIGRATIONS
from junvis.features.memory.infrastructure import MEMORY_MIGRATIONS
from junvis.features.project_brain.infrastructure import PROJECT_BRAIN_MIGRATIONS


@pytest.fixture(autouse=True)
def _no_shelling_out_to_claude(monkeypatch) -> None:
    """테스트가 진짜 Claude를 부르면 안 된다.

    이 기계에 `claude`가 깔려 있는지에 따라 결과가 달라지면 그건 테스트가
    아니다. 느리기도 하고 토큰도 태운다. Claude 어댑터 자체를 검증하는
    테스트는 이 픽스처를 자기 것으로 덮는다.
    """
    monkeypatch.setenv("JUNVIS_BRAIN", "ollama")


@pytest.fixture()
def db() -> Database:
    database = Database(MEMORY)
    database.migrate(
        CORE_MIGRATIONS, PROJECT_BRAIN_MIGRATIONS, CREATOR_MIGRATIONS, MEMORY_MIGRATIONS
    )
    yield database
    database.close()


@pytest.fixture()
def outbox(db: Database) -> SqliteOutbox:
    return SqliteOutbox(db)


@pytest.fixture()
def bus(outbox: SqliteOutbox) -> EventBus:
    return EventBus(outbox)
