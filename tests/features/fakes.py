"""application 계층 테스트용 Fake 어댑터.

M7 완료 기준: 실제 SQLite·git 없이 전 유스케이스를 검증할 수 있어야 한다.
그게 안 되면 DIP가 지켜지지 않은 것이다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from junvis.features.project_brain.application.ports import GitReading, ScanResult
from junvis.features.project_brain.domain.model import CommitRef, IssueRef, Project
from junvis.features.project_brain.domain.repository import ProjectRepository
from junvis.features.project_brain.domain.value_objects import (
    ProjectId,
    RepoRef,
    Slug,
    TechStack,
)

FIXED_NOW = datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc)


class FixedClock:
    def __init__(self, moment: datetime = FIXED_NOW) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


class InMemoryProjectRepository(ProjectRepository):
    def __init__(self) -> None:
        self.items: dict[str, Project] = {}

    def save(self, project: Project) -> None:
        self.items[project.id.value] = project

    def get(self, project_id: ProjectId) -> Project | None:
        return self.items.get(project_id.value)

    def get_by_slug(self, slug: Slug) -> Project | None:
        return next((p for p in self.items.values() if p.slug == slug), None)

    def list(self) -> list[Project]:
        return sorted(self.items.values(), key=lambda p: p.updated_at, reverse=True)

    def search(self, query: str, limit: int = 10) -> list[Project]:
        needle = query.lower()
        hits = [
            p
            for p in self.items.values()
            if needle in p.name.lower()
            or needle in p.slug.value.lower()
            or needle in p.purpose.lower()
        ]
        return hits[:limit]

    def remove(self, project_id: ProjectId) -> bool:
        return self.items.pop(project_id.value, None) is not None


class FakeGit:
    def __init__(self, reading: GitReading | None = None) -> None:
        self.reading = reading
        self.calls: list[Path] = []

    def read(self, path: Path, *, commit_limit: int = 10) -> GitReading | None:
        self.calls.append(path)
        return self.reading


class FakeScanner:
    def __init__(self, result: ScanResult | None = None) -> None:
        self.result = result or ScanResult()

    def scan(self, path: Path) -> ScanResult:
        return self.result


class FakeIssues:
    def __init__(self, issues: tuple[IssueRef, ...] = (), *, fail: bool = False) -> None:
        self.issues = issues
        self.fail = fail

    def open_issues(self, repo: RepoRef, *, limit: int = 10) -> tuple[IssueRef, ...]:
        if self.fail:
            raise RuntimeError("네트워크 없음")
        return self.issues


def sample_reading() -> GitReading:
    return GitReading(
        branch="main",
        dirty=False,
        commits=(CommitRef("a" * 40, "첫 커밋", FIXED_NOW, "ZUN"),),
        remote_url="git@github.com:djkdb/zunvis.git",
    )


def sample_scan() -> ScanResult:
    return ScanResult(
        readme_excerpt="JUNVIS는 개인 AI OS다.",
        stack=TechStack.of(["Python", "MCP"]),
        todos=("MCP 서버 노출",),
    )
