"""ProjectRepository — 도메인이 선언하고 인프라가 구현한다(DIP)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from junvis.features.project_brain.domain.model import Project
from junvis.features.project_brain.domain.value_objects import ProjectId, Slug


class ProjectRepository(ABC):
    @abstractmethod
    def save(self, project: Project) -> None:
        """새 프로젝트를 추가하거나 기존 프로젝트를 갱신한다."""

    @abstractmethod
    def get(self, project_id: ProjectId) -> Project | None: ...

    @abstractmethod
    def get_by_slug(self, slug: Slug) -> Project | None: ...

    @abstractmethod
    def list(self) -> list[Project]:
        """최근 갱신 순으로 전부 반환한다. 개인용이라 페이지네이션을 두지 않는다."""

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> list[Project]:
        """전문 검색. 구현은 FTS5를 쓰지만 도메인은 그것을 모른다."""

    @abstractmethod
    def remove(self, project_id: ProjectId) -> bool: ...
