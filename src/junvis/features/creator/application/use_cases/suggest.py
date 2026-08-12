"""새 프로젝트를 감지해 콘텐츠를 제안한다 — 브리프의 'Content Assistant'.

`project_brain`이 `project.registered`를 발행하면 이 유스케이스가 돈다.
project_brain은 creator의 존재를 모른다.
"""

from __future__ import annotations

from junvis.core.eventbus.bus import EventBus
from junvis.core.trace.recorder import TraceRecorder
from junvis.features.creator.application.base import TracedUseCase
from junvis.features.creator.application.dto import ContentSummary
from junvis.features.creator.application.ports import (
    ClockPort,
    SystemClock,
    UnitOfWorkPort,
)
from junvis.features.creator.domain.model import ContentIdea
from junvis.features.creator.domain.repository import ContentRepository
from junvis.features.creator.domain.value_objects import ContentFormat


def default_subject(project_name: str) -> str:
    """프로젝트에서 기본 릴스 주제를 만든다.

    브리프의 콘텐츠 성향 중 '프로젝트 제작기'에 해당한다.
    """
    return f"{project_name} 만든 과정"


class SuggestForProject(TracedUseCase):
    def __init__(
        self,
        repository: ContentRepository,
        bus: EventBus,
        unit_of_work: UnitOfWorkPort,
        *,
        clock: ClockPort | None = None,
        tracer: TraceRecorder | None = None,
    ) -> None:
        super().__init__(tracer)
        self._repository = repository
        self._bus = bus
        self._uow = unit_of_work
        self._clock = clock or SystemClock()

    def __call__(self, slug: str, project_name: str) -> ContentSummary | None:
        """이미 같은 프로젝트로 만든 제안이 있으면 아무것도 하지 않는다.

        프로젝트를 다시 등록할 때마다 제안이 쌓이면 잔소리가 된다.
        """
        with self.trace("content.suggest", slug=slug) as handle:
            if self._repository.find_by_project(slug):
                if handle is not None:
                    handle.annotate(skipped="이미 제안이 있음")
                return None

            idea = ContentIdea.suggest(
                default_subject(project_name),
                content_format=ContentFormat.REELS,
                source_project_slug=slug,
                now=self._clock.now(),
            )
            with self._uow():
                self._repository.save(idea)
                for event in idea.pull_events():
                    self._bus.publish(event)
            return ContentSummary.of(idea)
