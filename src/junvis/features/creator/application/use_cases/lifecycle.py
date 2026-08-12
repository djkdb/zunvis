"""상태 전이 유스케이스 — 버리기, 발행 기록, 성과 기록."""

from __future__ import annotations

from junvis.core.eventbus.bus import EventBus
from junvis.core.policy.engine import PolicyEngine
from junvis.core.trace.recorder import TraceRecorder
from junvis.core.usecase import TracedUseCase
from junvis.features.creator.application.dto import ContentSummary
from junvis.features.creator.application.ports import (
    ClockPort,
    SystemClock,
    UnitOfWorkPort,
)
from junvis.features.creator.domain.errors import ContentNotFound
from junvis.features.creator.domain.model import ContentIdea
from junvis.features.creator.domain.repository import BrandVoiceStore, ContentRepository
from junvis.features.creator.domain.value_objects import BrandVoice, IdeaId


class _ContentCommand(TracedUseCase):
    """상태를 바꾸고 저장·발행하는 공통 뼈대."""

    def __init__(
        self,
        repository: ContentRepository,
        bus: EventBus,
        unit_of_work: UnitOfWorkPort,
        *,
        policy: PolicyEngine | None = None,
        clock: ClockPort | None = None,
        tracer: TraceRecorder | None = None,
    ) -> None:
        super().__init__(tracer)
        self._repository = repository
        self._bus = bus
        self._uow = unit_of_work
        self._policy = policy
        self._clock = clock or SystemClock()

    def _load(self, idea_id: str) -> ContentIdea:
        idea = self._repository.get(IdeaId(idea_id))
        if idea is None:
            raise ContentNotFound(f"없는 콘텐츠입니다: {idea_id}")
        return idea

    def _commit(self, idea: ContentIdea) -> ContentSummary:
        with self._uow():
            self._repository.save(idea)
            for event in idea.pull_events():
                self._bus.publish(event)
        return ContentSummary.of(idea)


class DismissContent(_ContentCommand):
    def __call__(self, idea_id: str, reason: str = "") -> ContentSummary:
        with self.trace("content.dismiss", idea_id=idea_id):
            if self._policy is not None:
                self._policy.guard("content.dismiss", idea_id)
            idea = self._load(idea_id)
            idea.dismiss(reason, now=self._clock.now())
            return self._commit(idea)


class MarkPublished(_ContentCommand):
    """발행 '기록'이다. JUNVIS가 Instagram에 올리지 않는다.

    자동 게시는 브리프에 없고 되돌릴 수 없는 외부 행위다
    (docs/03-CREATOR-MODE.md §7).
    """

    def __call__(self, idea_id: str, url: str | None = None) -> ContentSummary:
        with self.trace("content.record_published", idea_id=idea_id):
            if self._policy is not None:
                self._policy.guard("content.record_published", idea_id)
            idea = self._load(idea_id)
            idea.mark_published(url, now=self._clock.now())
            return self._commit(idea)


class RecordPerformance(_ContentCommand):
    def __call__(self, idea_id: str, note: str) -> ContentSummary:
        with self.trace("content.record_published", idea_id=idea_id, kind="performance"):
            if self._policy is not None:
                self._policy.guard("content.record_published", idea_id)
            idea = self._load(idea_id)
            idea.record_performance(note, now=self._clock.now())
            return self._commit(idea)


class UpdateBrandVoice(TracedUseCase):
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

    def __call__(
        self,
        *,
        topics: list[str] | None = None,
        tone: str | None = None,
        audience: str | None = None,
        banned_phrases: list[str] | None = None,
    ) -> BrandVoice:
        """주지 않은 항목은 건드리지 않는다."""
        with self.trace("content.update_brand_voice"):
            if self._policy is not None:
                self._policy.guard("content.update_brand_voice")
            current = self._store.get()
            updated = BrandVoice(
                topics=tuple(topics) if topics is not None else current.topics,
                tone=tone if tone is not None else current.tone,
                audience=audience if audience is not None else current.audience,
                banned_phrases=(
                    tuple(banned_phrases)
                    if banned_phrases is not None
                    else current.banned_phrases
                ),
            )
            self._store.save(updated)
            return updated
