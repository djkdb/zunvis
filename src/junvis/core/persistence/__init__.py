from pathlib import Path

from junvis.core.persistence.database import MEMORY, Database, MigrationSource

#: core가 소유한 스키마. 조립 루트가 Database.migrate()에 넘긴다.
CORE_MIGRATIONS = MigrationSource("core", Path(__file__).parent / "migrations")

__all__ = ["Database", "MigrationSource", "MEMORY", "CORE_MIGRATIONS"]
