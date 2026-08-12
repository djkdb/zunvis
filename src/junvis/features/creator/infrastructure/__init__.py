from pathlib import Path

from junvis.core.persistence.database import MigrationSource

CREATOR_MIGRATIONS = MigrationSource("creator", Path(__file__).parent / "migrations")

__all__ = ["CREATOR_MIGRATIONS"]
