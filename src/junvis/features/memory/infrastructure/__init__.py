from pathlib import Path

from junvis.core.persistence.database import MigrationSource

MEMORY_MIGRATIONS = MigrationSource("memory", Path(__file__).parent / "migrations")

__all__ = ["MEMORY_MIGRATIONS"]
