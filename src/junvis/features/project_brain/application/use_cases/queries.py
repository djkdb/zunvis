"""읽기 전용 조회.

쓰기 유스케이스는 시나리오마다 파일을 나누지만, 읽기는 부작용도 이벤트도
없으므로 한 곳에 모은다(CQRS의 읽기 측).
"""

from __future__ import annotations

from junvis.core.policy.engine import PolicyEngine
from junvis.core.trace.recorder import TraceRecorder
from junvis.features.project_brain.application.base import TracedUseCase
from junvis.features.project_brain.application.dto import ProjectSummary
from junvis.features.project_brain.domain.repository import ProjectRepository


class ListProjects(TracedUseCase):
    def __init__(
        self,
        repository: ProjectRepository,
        *,
        policy: PolicyEngine | None = None,
        tracer: TraceRecorder | None = None,
    ) -> None:
        super().__init__(tracer)
        self._repository = repository
        self._policy = policy

    def __call__(self) -> list[ProjectSummary]:
        with self.trace("project.list"):
            if self._policy is not None:
                self._policy.guard("project.list")
            return [ProjectSummary.of(p) for p in self._repository.list()]


class SearchProjects(TracedUseCase):
    def __init__(
        self,
        repository: ProjectRepository,
        *,
        policy: PolicyEngine | None = None,
        tracer: TraceRecorder | None = None,
    ) -> None:
        super().__init__(tracer)
        self._repository = repository
        self._policy = policy

    def __call__(self, query: str, *, limit: int = 10) -> list[ProjectSummary]:
        with self.trace("project.search", query=query) as handle:
            if self._policy is not None:
                self._policy.guard("project.search", query)
            results = self._repository.search(query, limit=limit)
            if handle is not None:
                handle.annotate(hits=len(results))
            return [ProjectSummary.of(p) for p in results]
