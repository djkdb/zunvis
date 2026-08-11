"""JUNVIS 전역 예외 계층."""

from __future__ import annotations


class JunvisError(Exception):
    """모든 JUNVIS 예외의 뿌리."""


class DomainError(JunvisError):
    """도메인 불변식 위반."""


class NotFoundError(JunvisError):
    """요청한 애그리게이트를 찾지 못함."""


class ConflictError(JunvisError):
    """유일성 등 저장소 수준 충돌."""


class PolicyError(JunvisError):
    """PolicyEngine이 막은 행위."""


class PolicyDenied(PolicyError):
    """정책이 명시적으로 거부함. 재시도해도 통과하지 못한다."""


class PolicyConfirmationRequired(PolicyError):
    """사용자 확인이 필요하나 확인 통로가 없어 진행할 수 없음."""
