"""project_brain 도메인 예외."""

from __future__ import annotations

from junvis.core.domain.errors import ConflictError, DomainError, NotFoundError


class InvalidSlug(DomainError):
    """slug 형식 위반."""


class ProjectNotFound(NotFoundError):
    """등록되지 않은 프로젝트."""


class DuplicateSlug(ConflictError):
    """이미 쓰이고 있는 slug."""
