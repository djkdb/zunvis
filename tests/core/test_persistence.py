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


def test_migration_names_are_namespaced_by_owner(db: Database) -> None:
    """모든 마이그레이션 폴더 이름이 `migrations`라서 소유자를 명시해야 한다.

    디렉터리 이름으로 유추하면 core의 001과 feature의 001이 조용히 충돌한다.
    """
    applied = {row["name"] for row in db.query("SELECT name FROM schema_migrations")}
    assert applied == {
        "core/001_core.sql",
        "project_brain/001_project_brain.sql",
        "creator/001_creator.sql",
    }


def test_same_filename_from_different_owners_does_not_collide(tmp_path) -> None:
    from junvis.core.persistence import MigrationSource

    for owner in ("alpha", "beta"):
        directory = tmp_path / owner / "migrations"
        directory.mkdir(parents=True)
        (directory / "001_init.sql").write_text(
            f"CREATE TABLE IF NOT EXISTS {owner}_t (id INTEGER);", encoding="utf-8"
        )

    database = Database(MEMORY)
    applied = database.migrate(
        MigrationSource("alpha", tmp_path / "alpha" / "migrations"),
        MigrationSource("beta", tmp_path / "beta" / "migrations"),
    )

    assert applied == ["alpha/001_init.sql", "beta/001_init.sql"]
    assert {"alpha_t", "beta_t"} <= tables(database)
    database.close()


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
