"""project_brain이 발행하는 도메인 이벤트.

이 이벤트들이 다른 Bounded Context와의 **유일한 접점**이다.
`creator`가 "이 프로젝트 릴스 만들까?"를 제안하는 것도, `brief`가 오늘의
브리핑에 항목을 추가하는 것도 전부 여기 구독해서 이뤄진다.
project_brain은 그들의 존재를 모른다.
"""

from __future__ import annotations

from dataclasses import dataclass

from junvis.core.domain.event import DomainEvent


@dataclass(frozen=True, kw_only=True)
class ProjectRegistered(DomainEvent):
    topic = "project.registered"

    project_id: str
    slug: str
    name: str
    repo_full_name: str | None = None


@dataclass(frozen=True, kw_only=True)
class ProjectSnapshotRefreshed(DomainEvent):
    topic = "project.snapshot_refreshed"

    project_id: str
    slug: str
    branch: str | None = None
    commit_count: int = 0
    todo_count: int = 0


@dataclass(frozen=True, kw_only=True)
class ProjectNoteAdded(DomainEvent):
    topic = "project.note_added"

    project_id: str
    slug: str
    note_id: str
    text: str
