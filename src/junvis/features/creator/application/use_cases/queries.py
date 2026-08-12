"""읽기 전용 조회."""

from __future__ import annotations

from junvis.core.policy.engine import PolicyEngine
from junvis.core.trace.recorder import TraceRecorder
from junvis.core.usecase import TracedUseCase
from junvis.features.creator.application.dto import ContentDetail, ContentSummary
from junvis.features.creator.domain.errors import ContentNotFound
from junvis.features.creator.domain.repository import BrandVoiceStore, ContentRepository
from junvis.features.creator.domain.value_objects import BrandVoice, ContentStatus, IdeaId


class ListContent(TracedUseCase):
    def __init__(
        self,
        repository: ContentRepository,
        *,
        policy: PolicyEngine | None = None,
        tracer: TraceRecorder | None = None,
    ) -> None:
        super().__init__(tracer)
        self._repository = repository
        self._policy = policy

    def __call__(
        self, *, status: str | None = None, limit: int = 50
    ) -> list[ContentSummary]:
        with self.trace("content.list", status=status or "all"):
            if self._policy is not None:
                self._policy.guard("content.list")
            wanted = ContentStatus(status) if status else None
            return [
                ContentSummary.of(idea)
                for idea in self._repository.list(status=wanted, limit=limit)
            ]


class GetContent(TracedUseCase):
    def __init__(
        self,
        repository: ContentRepository,
        *,
        policy: PolicyEngine | None = None,
        tracer: TraceRecorder | None = None,
    ) -> None:
        super().__init__(tracer)
        self._repository = repository
        self._policy = policy

    def __call__(self, idea_id: str) -> ContentDetail:
        with self.trace("content.read", idea_id=idea_id):
            if self._policy is not None:
                self._policy.guard("content.read", idea_id)
            idea = self._repository.get(IdeaId(idea_id))
            if idea is None:
                raise ContentNotFound(f"없는 콘텐츠입니다: {idea_id}")
            return ContentDetail.of(idea)


class GetBrandVoice(TracedUseCase):
    def __init__(
        self,
        store: BrandVoiceStore,
        *,
        policy: PolicyEngine | None = None,
        tracer: TraceRecorder | None = None,
    ) -> None:
        super().__init__(tracer)
        self._store = store
        self._policy = policy

    def __call__(self) -> BrandVoice:
        with self.trace("content.read", target="brand_voice"):
            if self._policy is not None:
                self._policy.guard("content.read", "brand_voice")
            return self._store.get()
