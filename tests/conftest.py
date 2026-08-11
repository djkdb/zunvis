from __future__ import annotations

import pytest

from junvis.core.eventbus.bus import EventBus
from junvis.core.eventbus.outbox import SqliteOutbox
from junvis.core.persistence import CORE_MIGRATIONS, MEMORY, Database
from junvis.features.project_brain.infrastructure import PROJECT_BRAIN_MIGRATIONS


@pytest.fixture()
def db() -> Database:
    database = Database(MEMORY)
    database.migrate(CORE_MIGRATIONS, PROJECT_BRAIN_MIGRATIONS)
    yield database
    database.close()


@pytest.fixture()
def outbox(db: Database) -> SqliteOutbox:
    return SqliteOutbox(db)


@pytest.fixture()
def bus(outbox: SqliteOutbox) -> EventBus:
    return EventBus(outbox)
