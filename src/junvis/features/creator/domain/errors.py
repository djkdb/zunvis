"""creator 도메인 예외."""

from __future__ import annotations

from junvis.core.domain.errors import DomainError, NotFoundError


class InvalidScript(DomainError):
    """플랫폼 규칙이나 구조 요건을 어긴 대본."""


class InvalidStateTransition(DomainError):
    """상태 기계가 허용하지 않는 전이."""


class ContentNotFound(NotFoundError):
    """등록되지 않은 콘텐츠."""
