"""memory의 저장소 인터페이스."""

from __future__ import annotations

from abc import ABC, abstractmethod

from junvis.features.memory.domain.model import MemoryEntry, MemoryHit, Recall


class MemoryRepository(ABC):
    @abstractmethod
    def add(self, entry: MemoryEntry) -> None: ...

    @abstractmethod
    def get(self, entry_id: str) -> MemoryEntry | None: ...

    @abstractmethod
    def update(self, entry: MemoryEntry) -> None:
        """회상 통계·고정 여부 갱신."""

    @abstractmethod
    def remove(self, entry_id: str) -> bool: ...

    @abstractmethod
    def search(self, recall: Recall) -> list[MemoryHit]:
        """질의가 비어 있으면 스코프 안의 최근 기억을 돌려준다."""

    @abstractmethod
    def all(self, *, limit: int = 100) -> list[MemoryEntry]: ...

    @abstractmethod
    def find_similar(self, normalized_text: str) -> MemoryEntry | None:
        """같은 사실을 두 번 저장하지 않기 위해."""
