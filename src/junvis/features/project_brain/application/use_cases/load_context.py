"""Context Pack을 조립해 반환한다 — MVP의 대표 시나리오.

Claude Code가 세션을 시작할 때 이걸 부르면, JUNVIS가 이미 알고 있는
프로젝트 지식이 그대로 주입된다.
"""

from __future__ import annotations

from junvis.core.policy.engine import PolicyEngine
from junvis.core.trace.recorder import TraceRecorder
from junvis.core.usecase import TracedUseCase
from junvis.features.project_brain.domain.context_pack import ContextPack
from junvis.features.project_brain.domain.errors import ProjectNotFound
from junvis.features.project_brain.domain.repository import ProjectRepository
from junvis.features.project_brain.domain.value_objects import Slug, TokenBudget


class LoadProjectContext(TracedUseCase):
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

    def __call__(self, slug: str, *, budget_tokens: int = 2000) -> ContextPack:
        with self.trace("project.context", slug=slug) as handle:
            if self._policy is not None:
                self._policy.guard("project.context", slug)

            project = self._repository.get_by_slug(Slug(slug))
            if project is None:
                raise ProjectNotFound(f"등록되지 않은 프로젝트입니다: {slug}")

            pack = project.context_pack(TokenBudget(budget_tokens))
            if handle is not None:
                handle.annotate(
                    sections=len(pack.sections),
                    estimated_tokens=pack.estimated_tokens,
                    truncated=pack.truncated,
                )
            return pack
