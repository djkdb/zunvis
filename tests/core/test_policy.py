"""M4 완료 기준: HIGH 행위가 확인 없이 통과하지 않는다."""

from __future__ import annotations

import pytest

from junvis.core.domain.errors import PolicyConfirmationRequired, PolicyDenied
from junvis.core.policy.engine import Action, Decision, PolicyEngine, RiskLevel


class Always:
    def __init__(self, answer: bool) -> None:
        self.answer = answer
        self.asked: list[Action] = []

    def confirm(self, action, verdict) -> bool:
        self.asked.append(action)
        return self.answer


def test_reads_are_allowed_without_confirmation() -> None:
    engine = PolicyEngine()
    verdict = engine.evaluate(Action("project.context", "zunvis"))
    assert verdict.level is RiskLevel.SAFE
    assert verdict.decision is Decision.ALLOW


def test_high_risk_requires_confirmation() -> None:
    engine = PolicyEngine()  # 확인 통로 없음
    with pytest.raises(PolicyConfirmationRequired):
        engine.guard("git.push", "origin/main")


def test_high_risk_passes_when_user_confirms() -> None:
    confirmer = Always(True)
    engine = PolicyEngine(confirmer=confirmer)
    verdict = engine.guard("git.push", "origin/main")
    assert verdict.level is RiskLevel.HIGH
    assert len(confirmer.asked) == 1


def test_user_rejection_denies() -> None:
    engine = PolicyEngine(confirmer=Always(False))
    with pytest.raises(PolicyDenied):
        engine.guard("shell.exec", "rm -rf /")


def test_forbidden_is_never_asked() -> None:
    confirmer = Always(True)
    engine = PolicyEngine(confirmer=confirmer)
    with pytest.raises(PolicyDenied):
        engine.guard("credential.read", "keychain")
    assert confirmer.asked == []  # 물어보지도 않는다


def test_sensitive_capture_is_forbidden() -> None:
    engine = PolicyEngine(confirmer=Always(True))
    with pytest.raises(PolicyDenied):
        engine.guard("vision.capture", "1Password", sensitive=True)
    # 민감하지 않은 앱은 확인 대상일 뿐 금지가 아니다
    assert engine.evaluate(Action("vision.capture", "VSCode")).decision is Decision.CONFIRM


def test_write_inside_workspace_is_low_but_outside_is_high() -> None:
    engine = PolicyEngine()
    inside = engine.evaluate(
        Action("file.write", "/w/app/main.py", {"workspace": "/w/app"})
    )
    outside = engine.evaluate(
        Action("file.write", "/etc/hosts", {"workspace": "/w/app"})
    )
    assert inside.level is RiskLevel.LOW
    assert outside.level is RiskLevel.HIGH


def test_unknown_action_fails_safe() -> None:
    engine = PolicyEngine()
    verdict = engine.evaluate(Action("무슨행위인지모름"))
    assert verdict.decision is Decision.CONFIRM
    assert verdict.rule == "unknown"


def test_capability_wildcards() -> None:
    engine = PolicyEngine()
    engine.check_capability({"memory:*"}, "memory:read")
    engine.check_capability({"*"}, "anything:at:all")
    with pytest.raises(PolicyDenied):
        engine.check_capability({"project:read"}, "memory:write")
