from pathlib import Path

#: feature가 자기 스키마를 소유한다. core 마이그레이션에 섞지 않는다.
PROJECT_BRAIN_MIGRATIONS = Path(__file__).parent / "migrations"

__all__ = ["PROJECT_BRAIN_MIGRATIONS"]
