"""프로젝트를 등록하거나 이미 있으면 설명을 갱신한다."""

from __future__ import annotations

from pathlib import Path

from junvis.core.eventbus.bus import EventBus
from junvis.core.policy.engine import PolicyEngine
from junvis.core.trace.recorder import TraceRecorder
from junvis.features.project_brain.application.base import TracedUseCase
from junvis.features.project_brain.application.dto import (
    ProjectSummary,
    RegisterProjectCommand,
)
from junvis.features.project_brain.application.ports import (
    ClockPort,
    GitPort,
    SystemClock,
    UnitOfWorkPort,
)
from junvis.features.project_brain.domain.errors import InvalidSlug
from junvis.features.project_brain.domain.model import Project
from junvis.features.project_brain.domain.repository import ProjectRepository
from junvis.features.project_brain.domain.value_objects import RepoRef, Slug


class RegisterProject(TracedUseCase):
    def __init__(
        self,
        repository: ProjectRepository,
        bus: EventBus,
        unit_of_work: UnitOfWorkPort,
        *,
        policy: PolicyEngine | None = None,
        git: GitPort | None = None,
        clock: ClockPort | None = None,
        tracer: TraceRecorder | None = None,
    ) -> None:
        super().__init__(tracer)
        self._repository = repository
        self._bus = bus
        self._uow = unit_of_work
        self._policy = policy
        self._git = git
        self._clock = clock or SystemClock()

    def __call__(self, command: RegisterProjectCommand) -> ProjectSummary:
        with self.trace("project.register", slug=command.slug, path=str(command.path or "")):
            if self._policy is not None:
                self._policy.guard("project.register", command.slug or str(command.path or ""))

            path = command.path.expanduser().resolve() if command.path else None
            slug = self._resolve_slug(command, path)

            existing = self._repository.get_by_slug(slug)
            if existing is not None:
                return self._update(existing, command, path)
            return self._create(command, slug, path)

    # -- 내부 ---------------------------------------------------------------

    def _resolve_slug(self, command: RegisterProjectCommand, path: Path | None) -> Slug:
        if command.slug:
            return Slug(command.slug)
        source = command.name or (path.name if path else "")
        if not source:
            raise InvalidSlug("slug·이름·경로 중 하나는 있어야 합니다")
        return Slug.from_text(source)

    def _repo_ref(self, command: RegisterProjectCommand, path: Path | None) -> RepoRef | None:
        """명시된 원격 URL이 우선, 없으면 로컬 git에서 찾아본다."""
        if command.remote_url:
            return RepoRef.parse(command.remote_url)
        if path and self._git is not None:
            reading = self._git.read(path, commit_limit=1)
            if reading is not None:
                return RepoRef.parse(reading.remote_url)
        return None

    def _create(
        self, command: RegisterProjectCommand, slug: Slug, path: Path | None
    ) -> ProjectSummary:
        project = Project.register(
            slug=slug,
            name=command.name or slug.value,
            local_path=path,
            repo=self._repo_ref(command, path),
            purpose=command.purpose,
            architecture_note=command.architecture_note,
            now=self._clock.now(),
        )
        with self._uow():
            self._repository.save(project)
            for event in project.pull_events():
                self._bus.publish(event)
        return ProjectSummary.of(project)

    def _update(
        self, project: Project, command: RegisterProjectCommand, path: Path | None
    ) -> ProjectSummary:
        """이미 아는 프로젝트를 다시 등록하는 것은 오류가 아니라 갱신이다."""
        project.describe(
            purpose=command.purpose or None,
            architecture_note=command.architecture_note or None,
            now=self._clock.now(),
        )
        if path is not None:
            project.local_path = path
        repo = self._repo_ref(command, path)
        if repo is not None:
            project.repo = repo
        with self._uow():
            self._repository.save(project)
            for event in project.pull_events():
                self._bus.publish(event)
        return ProjectSummary.of(project)
