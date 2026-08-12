"""creator의 저장소 인터페이스."""

from __future__ import annotations

from abc import ABC, abstractmethod

from junvis.features.creator.domain.model import ContentIdea
from junvis.features.creator.domain.value_objects import (
    BrandVoice,
    ContentStatus,
    IdeaId,
)


class ContentRepository(ABC):
    @abstractmethod
    def save(self, idea: ContentIdea) -> None: ...

    @abstractmethod
    def get(self, idea_id: IdeaId) -> ContentIdea | None: ...

    @abstractmethod
    def list(
        self, *, status: ContentStatus | None = None, limit: int = 50
    ) -> list[ContentIdea]:
        """최근 갱신 순. status를 주면 그 상태만."""

    @abstractmethod
    def find_by_project(self, slug: str) -> list[ContentIdea]:
        """같은 프로젝트로 제안을 중복 생성하지 않기 위해 필요하다."""


class BrandVoiceStore(ABC):
    @abstractmethod
    def get(self) -> BrandVoice:
        """저장된 값이 없으면 ZUN 기본값을 돌려준다."""

    @abstractmethod
    def save(self, voice: BrandVoice) -> None: ...
