"""프로젝트 스냅샷을 다시 수집한다."""

from __future__ import annotations

from junvis.core.eventbus.bus import EventBus
from junvis.core.policy.engine import PolicyEngine
from junvis.core.trace.recorder import TraceRecorder
from junvis.core.usecase import TracedUseCase
from junvis.features.project_brain.application.dto import ProjectSummary
from junvis.features.project_brain.application.ports import (
    ClockPort,
    GitPort,
    IssueTrackerPort,
    ProjectScannerPort,
    ScanResult,
    SystemClock,
    UnitOfWorkPort,
)
from junvis.features.project_brain.domain.errors import ProjectNotFound
from junvis.features.project_brain.domain.model import ProjectSnapshot
from junvis.features.project_brain.domain.repository import ProjectRepository
from junvis.features.project_brain.domain.value_objects import Slug


class RefreshSnapshot(TracedUseCase):
    """git·파일시스템·이슈트래커에서 사실을 모아 스냅샷 하나로 만든다.

    수집원 하나가 실패해도 나머지는 반영한다. 이슈를 못 읽는다고 커밋
    기록까지 잃으면, 오프라인일 때 JUNVIS가 통째로 눈이 먼다.
    """

    def __init__(
        self,
        repository: ProjectRepository,
        bus: EventBus,
        unit_of_work: UnitOfWorkPort,
        git: GitPort,
        scanner: ProjectScannerPort,
        *,
        issues: IssueTrackerPort | None = None,
        policy: PolicyEngine | None = None,
        clock: ClockPort | None = None,
        tracer: TraceRecorder | None = None,
    ) -> None:
        super().__init__(tracer)
        self._repository = repository
        self._bus = bus
        self._uow = unit_of_work
        self._git = git
        self._scanner = scanner
        self._issues = issues
        self._policy = policy
        self._clock = clock or SystemClock()

    def __call__(
        self, slug: str, *, commit_limit: int = 10, issue_limit: int = 10
    ) -> ProjectSummary:
        with self.trace("project.refresh", slug=slug) as handle:
            if self._policy is not None:
                self._policy.guard("project.refresh", slug)

            project = self._repository.get_by_slug(Slug(slug))
            if project is None:
                raise ProjectNotFound(f"등록되지 않은 프로젝트입니다: {slug}")

            reading = None
            scan = ScanResult()
            path = project.local_path
            if path is not None and path.exists():
                reading = self._git.read(path, commit_limit=commit_limit)
                scan = self._scanner.scan(path)
                if handle is not None:
                    handle.annotate(scanned=True)

            open_issues = ()
            if self._issues is not None and project.repo is not None:
                open_issues = self._issues.open_issues(project.repo, limit=issue_limit)

            snapshot = ProjectSnapshot(
                captured_at=self._clock.now(),
                branch=reading.branch if reading else None,
                dirty=reading.dirty if reading else False,
                readme_excerpt=scan.readme_excerpt,
                recent_commits=reading.commits if reading else (),
                open_issues=open_issues,
                detected_stack=scan.stack,
                discovered_todos=scan.todos,
            )
            project.refresh(snapshot, now=self._clock.now())

            with self._uow():
                self._repository.save(project)
                for event in project.pull_events():
                    self._bus.publish(event)

            return ProjectSummary.of(project)
