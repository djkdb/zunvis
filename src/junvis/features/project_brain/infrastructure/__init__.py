from pathlib import Path

from junvis.core.persistence.database import MigrationSource

#: feature가 자기 스키마를 소유한다. core 마이그레이션에 섞지 않는다.
PROJECT_BRAIN_MIGRATIONS = MigrationSource(
    "project_brain", Path(__file__).parent / "migrations"
)

__all__ = ["PROJECT_BRAIN_MIGRATIONS"]
