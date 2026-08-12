"""브리프의 Creator Mode 본체.

"릴스 하나 만들자" → 주제·Hook·대본·장면·B-roll·캡션·해시태그·
썸네일 문구·댓글 유도 문구까지 한 번에.
"""

from __future__ import annotations

from junvis.core.eventbus.bus import EventBus
from junvis.core.policy.engine import PolicyEngine
from junvis.core.trace.recorder import TraceRecorder
from junvis.features.creator.application.base import TracedUseCase
from junvis.features.creator.application.dto import ContentDetail
from junvis.features.creator.application.ports import (
    ClockPort,
    GenerationRequest,
    ProjectContextPort,
    ScriptGeneratorPort,
    SystemClock,
    UnitOfWorkPort,
)
from junvis.features.creator.domain.errors import ContentNotFound
from junvis.features.creator.domain.model import ContentIdea
from junvis.features.creator.domain.repository import BrandVoiceStore, ContentRepository
from junvis.features.creator.domain.value_objects import ContentFormat, IdeaId

#: 프로젝트 컨텍스트에 줄 토큰 예산. 대본 생성 프롬프트의 일부일 뿐이므로
#: Context Pack 기본값(2000)보다 작게 잡는다.
PROJECT_CONTEXT_BUDGET = 800


class GenerateContent(TracedUseCase):
    def __init__(
        self,
        repository: ContentRepository,
        brand_voice: BrandVoiceStore,
        generator: ScriptGeneratorPort,
        bus: EventBus,
        unit_of_work: UnitOfWorkPort,
        *,
        project_context: ProjectContextPort | None = None,
        policy: PolicyEngine | None = None,
        clock: ClockPort | None = None,
        tracer: TraceRecorder | None = None,
    ) -> None:
        super().__init__(tracer)
        self._repository = repository
        self._brand_voice = brand_voice
        self._generator = generator
        self._bus = bus
        self._uow = unit_of_work
        self._project_context = project_context
        self._policy = policy
        self._clock = clock or SystemClock()

    def __call__(
        self,
        *,
        subject: str | None = None,
        idea_id: str | None = None,
        project_slug: str | None = None,
        content_format: ContentFormat = ContentFormat.REELS,
        direction: str = "",
    ) -> ContentDetail:
        """주제로 새로 만들거나, 기존 제안(idea_id)에 대본을 붙인다."""
        with self.trace("content.create", subject=subject or "", idea_id=idea_id or "") as handle:
            if self._policy is not None:
                self._policy.guard("content.create", subject or idea_id or "")

            idea = self._resolve_idea(
                subject=subject,
                idea_id=idea_id,
                project_slug=project_slug,
                content_format=content_format,
            )

            context = self._load_context(idea.source_project_slug or project_slug)
            if handle is not None:
                handle.annotate(has_project_context=context is not None)

            script = self._generator.generate(
                GenerationRequest(
                    subject=idea.subject,
                    content_format=idea.content_format,
                    brand_voice=self._brand_voice.get(),
                    project_context=context,
                    direction=direction,
                )
            )
            idea.attach_script(script, now=self._clock.now())

            with self._uow():
                self._repository.save(idea)
                for event in idea.pull_events():
                    self._bus.publish(event)

            return ContentDetail.of(idea)

    # -- 내부 ---------------------------------------------------------------

    def _resolve_idea(
        self,
        *,
        subject: str | None,
        idea_id: str | None,
        project_slug: str | None,
        content_format: ContentFormat,
    ) -> ContentIdea:
        if idea_id:
            existing = self._repository.get(IdeaId(idea_id))
            if existing is None:
                raise ContentNotFound(f"없는 콘텐츠입니다: {idea_id}")
            return existing
        if not subject:
            raise ValueError("subject 또는 idea_id 중 하나는 있어야 합니다")
        return ContentIdea.suggest(
            subject,
            content_format=content_format,
            source_project_slug=project_slug,
            now=self._clock.now(),
        )

    def _load_context(self, slug: str | None) -> str | None:
        """프로젝트 컨텍스트는 있으면 좋은 것이지 필수가 아니다."""
        if not slug or self._project_context is None:
            return None
        return self._project_context.get_context(slug, budget_tokens=PROJECT_CONTEXT_BUDGET)
