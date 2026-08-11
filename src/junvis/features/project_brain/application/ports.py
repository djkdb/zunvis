"""application이 필요로 하는 바깥 세계의 계약(Port).

도메인·유스케이스는 git도 GitHub도 SQLite도 모른다. 여기 선언된 형태만
알고, 실제 구현은 infrastructure가 제공한다(DIP).
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from junvis.core.domain.event import utcnow
from junvis.features.project_brain.domain.model import CommitRef, IssueRef
from junvis.features.project_brain.domain.value_objects import RepoRef, TechStack


@dataclass(frozen=True)
class GitReading:
    """로컬 git 저장소에서 읽어낸 사실."""

    branch: str | None = None
    dirty: bool = False
    commits: tuple[CommitRef, ...] = ()
    remote_url: str | None = None


@dataclass(frozen=True)
class ScanResult:
    """파일 시스템에서 읽어낸 사실."""

    readme_excerpt: str = ""
    stack: TechStack = field(default_factory=TechStack.empty)
    todos: tuple[str, ...] = ()


class GitPort(Protocol):
    def read(self, path: Path, *, commit_limit: int = 10) -> GitReading | None:
        """git 저장소가 아니거나 읽을 수 없으면 None."""


class ProjectScannerPort(Protocol):
    def scan(self, path: Path) -> ScanResult: ...


class IssueTrackerPort(Protocol):
    def open_issues(self, repo: RepoRef, *, limit: int = 10) -> tuple[IssueRef, ...]:
        """접근할 수 없으면 빈 튜플. 이슈를 못 읽는다고 스냅샷 전체가 실패하면 안 된다."""


class UnitOfWorkPort(Protocol):
    """저장과 이벤트 발행을 한 경계로 묶는다."""

    def __call__(self) -> AbstractContextManager[object]: ...


class ClockPort(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    """기본 시계. 테스트는 고정 시계를 주입한다."""

    def now(self) -> datetime:
        return utcnow()
