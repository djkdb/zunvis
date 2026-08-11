"""M2 완료 기준: 마이그레이션이 멱등하고 왕복이 된다."""

from __future__ import annotations

import pytest

from junvis.core.persistence import CORE_MIGRATIONS, MEMORY, Database
from junvis.features.project_brain.infrastructure import PROJECT_BRAIN_MIGRATIONS


def tables(db: Database) -> set[str]:
    return {
        row["name"]
        for row in db.query("SELECT name FROM sqlite_master WHERE type IN ('table','view')")
    }


def test_migrate_creates_core_and_feature_tables(db: Database) -> None:
    names = tables(db)
    assert {"outbox", "deadletter", "traces"} <= names          # core 소유
    assert {"projects", "project_snapshots", "project_notes"} <= names  # feature 소유


def test_migrate_is_idempotent() -> None:
    database = Database(MEMORY)
    first = database.migrate(CORE_MIGRATIONS, PROJECT_BRAIN_MIGRATIONS)
    second = database.migrate(CORE_MIGRATIONS, PROJECT_BRAIN_MIGRATIONS)

    assert len(first) == 2
    assert second == []  # 두 번째는 아무것도 적용하지 않는다
    database.close()


def test_migration_names_are_namespaced_by_directory(db: Database) -> None:
    """core와 feature가 같은 파일명을 써도 충돌하지 않아야 한다."""
    applied = {row["name"] for row in db.query("SELECT name FROM schema_migrations")}
    assert any(name.startswith("migrations/") for name in applied)
    assert len(applied) == 2


def test_file_database_persists_across_connections(tmp_path) -> None:
    path = tmp_path / "junvis.db"
    first = Database(path)
    first.migrate(CORE_MIGRATIONS)
    first.execute(
        "INSERT INTO traces (id, request, outcome, occurred_at) VALUES (?,?,?,?)",
        ("t1", "요청", "ok", "2026-08-11T00:00:00+00:00"),
    )
    first.close()

    second = Database(path)
    assert second.query_one("SELECT request FROM traces WHERE id='t1'")["request"] == "요청"
    second.close()


def test_transaction_rolls_back_on_error(db: Database) -> None:
    with pytest.raises(RuntimeError):
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO traces (id, request, outcome, occurred_at) VALUES (?,?,?,?)",
                ("t1", "요청", "ok", "2026-08-11T00:00:00+00:00"),
            )
            raise RuntimeError("중간에 실패")

    assert db.query("SELECT * FROM traces") == []


def test_nested_transactions_commit_once(db: Database) -> None:
    """유스케이스가 저장소를 부르면 트랜잭션이 중첩된다. 그래도 깨지지 않아야 한다."""
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO traces (id, request, outcome, occurred_at) VALUES (?,?,?,?)",
            ("outer", "밖", "ok", "2026-08-11T00:00:00+00:00"),
        )
        with db.transaction() as inner:
            inner.execute(
                "INSERT INTO traces (id, request, outcome, occurred_at) VALUES (?,?,?,?)",
                ("inner", "안", "ok", "2026-08-11T00:00:00+00:00"),
            )

    assert len(db.query("SELECT * FROM traces")) == 2


def test_nested_rollback_discards_everything(db: Database) -> None:
    with pytest.raises(RuntimeError):
        with db.transaction():
            with db.transaction() as inner:
                inner.execute(
                    "INSERT INTO traces (id, request, outcome, occurred_at) VALUES (?,?,?,?)",
                    ("inner", "안", "ok", "2026-08-11T00:00:00+00:00"),
                )
            raise RuntimeError("바깥에서 실패")

    assert db.query("SELECT * FROM traces") == []


def test_foreign_keys_are_enforced(db: Database) -> None:
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO project_notes (id, project_id, text, created_at) VALUES (?,?,?,?)",
            ("n1", "존재하지-않는-프로젝트", "메모", "2026-08-11T00:00:00+00:00"),
        )
