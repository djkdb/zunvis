"""memory 도메인 예외."""

from __future__ import annotations

from junvis.core.domain.errors import DomainError, NotFoundError


class InvalidMemory(DomainError):
    """비어 있거나 형식이 맞지 않는 기억."""


class MemoryNotFound(NotFoundError):
    """존재하지 않는 기억."""
