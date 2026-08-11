""" "이 프로젝트에 대해 기억해둬" — 사용자가 직접 주입하는 지식."""

from __future__ import annotations

from junvis.core.eventbus.bus import EventBus
from junvis.core.policy.engine import PolicyEngine
from junvis.core.trace.recorder import TraceRecorder
from junvis.features.project_brain.application.base import TracedUseCase
from junvis.features.project_brain.application.dto import ProjectSummary
from junvis.features.project_brain.application.ports import (
    ClockPort,
    SystemClock,
    UnitOfWorkPort,
)
from junvis.features.project_brain.domain.errors import ProjectNotFound
from junvis.features.project_brain.domain.repository import ProjectRepository
from junvis.features.project_brain.domain.value_objects import Slug


class RememberNote(TracedUseCase):
    def __init__(
        self,
        repository: ProjectRepository,
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

    def __call__(self, slug: str, text: str) -> ProjectSummary:
        with self.trace("project.remember", slug=slug):
            if self._policy is not None:
                self._policy.guard("project.remember", slug)

            project = self._repository.get_by_slug(Slug(slug))
            if project is None:
                raise ProjectNotFound(f"등록되지 않은 프로젝트입니다: {slug}")

            project.remember(text, now=self._clock.now())
            with self._uow():
                self._repository.save(project)
                for event in project.pull_events():
                    self._bus.publish(event)
            return ProjectSummary.of(project)
