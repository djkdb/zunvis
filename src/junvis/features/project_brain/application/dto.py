"""유스케이스가 주고받는 자료구조.

애그리게이트를 계층 밖으로 내보내지 않는다. 밖으로 나가는 것은 이 DTO뿐이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from junvis.features.project_brain.domain.model import Project


@dataclass(frozen=True)
class RegisterProjectCommand:
    name: str | None = None
    slug: str | None = None
    path: Path | None = None
    purpose: str = ""
    architecture_note: str = ""
    remote_url: str | None = None


@dataclass(frozen=True)
class ProjectSummary:
    """다른 Context와 인터페이스 계층에 공개되는 읽기 전용 표현."""

    slug: str
    name: str
    purpose: str
    repo_full_name: str | None
    tech_stack: tuple[str, ...]
    branch: str | None
    dirty: bool
    last_commit: str | None
    open_todo_count: int
    note_count: int
    local_path: str | None
    updated_at: datetime

    @classmethod
    def of(cls, project: Project) -> ProjectSummary:
        snapshot = project.snapshot
        return cls(
            slug=project.slug.value,
            name=project.name,
            purpose=project.purpose,
            repo_full_name=project.repo.full_name if project.repo else None,
            tech_stack=tuple(project.tech_stack),
            branch=snapshot.branch if snapshot else None,
            dirty=snapshot.dirty if snapshot else False,
            last_commit=(
                snapshot.recent_commits[0].summary()
                if snapshot and snapshot.recent_commits
                else None
            ),
            open_todo_count=sum(1 for todo in project.todos if not todo.done),
            note_count=len(project.notes),
            local_path=str(project.local_path) if project.local_path else None,
            updated_at=project.updated_at,
        )
