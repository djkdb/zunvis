"""PolicyEngine — 모든 부작용이 통과하는 승인 게이트.

Open Interpreter의 승인 모델(docs/01-ANALYSIS.md §2)을 코드 실행에만 두지
않고 파일·git·브라우저·시스템 제어까지 **전역 개념으로 일반화**한 것이다.
사용자 확인은 MCP Elicitation을 기본 통로로 삼는다.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Protocol

from junvis.core.domain.errors import PolicyConfirmationRequired, PolicyDenied


class RiskLevel(IntEnum):
    SAFE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    FORBIDDEN = 4


class Decision(str, Enum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


_DECISION_BY_LEVEL = {
    RiskLevel.SAFE: Decision.ALLOW,
    RiskLevel.LOW: Decision.ALLOW,
    RiskLevel.MEDIUM: Decision.CONFIRM,
    RiskLevel.HIGH: Decision.CONFIRM,
    RiskLevel.FORBIDDEN: Decision.DENY,
}


@dataclass(frozen=True)
class Action:
    """판정 대상. 행위 이름만이 아니라 **대상과 맥락**까지 함께 본다."""

    name: str
    target: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.name}({self.target})" if self.target else self.name


@dataclass(frozen=True)
class Verdict:
    level: RiskLevel
    decision: Decision
    reason: str
    rule: str


@dataclass(frozen=True)
class Rule:
    name: str
    level: RiskLevel
    reason: str
    actions: tuple[str, ...] = ()
    predicate: Callable[[Action], bool] | None = None

    def matches(self, action: Action) -> bool:
        if self.actions and not any(_action_matches(action.name, p) for p in self.actions):
            return False
        if self.predicate is not None and not self.predicate(action):
            return False
        return bool(self.actions) or self.predicate is not None


def _action_matches(name: str, pattern: str) -> bool:
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        return name.startswith(pattern[:-1])
    return name == pattern


class ConfirmPort(Protocol):
    """사용자 확인 통로. 기본 구현은 MCP Elicitation을 사용한다."""

    def confirm(self, action: Action, verdict: Verdict) -> bool: ...


def _writes_outside_workspace(action: Action) -> bool:
    workspace = action.context.get("workspace")
    target = action.context.get("path") or action.target
    if not workspace or not target:
        return False
    return not str(target).startswith(str(workspace))


def default_rules() -> tuple[Rule, ...]:
    """설계 §5.1의 위험 등급 표.

    순서가 곧 우선순위다. 더 구체적인 규칙을 먼저 둔다.
    """
    return (
        # -- 절대 금지 ----------------------------------------------------
        Rule(
            "credential-access",
            RiskLevel.FORBIDDEN,
            "자격증명·키체인 접근은 허용하지 않는다",
            actions=("credential.*", "keychain.*"),
        ),
        Rule(
            "sensitive-capture",
            RiskLevel.FORBIDDEN,
            "민감 앱 화면 캡처는 영구 차단된다",
            actions=("vision.capture",),
            predicate=lambda a: bool(a.context.get("sensitive")),
        ),
        Rule(
            "bulk-delete",
            RiskLevel.FORBIDDEN,
            "대량 삭제는 되돌릴 수 없다",
            actions=("fs.delete_bulk",),
        ),
        # -- 구체 규칙이 일반 규칙보다 앞선다 --------------------------------
        Rule(
            "write-outside-workspace",
            RiskLevel.HIGH,
            "작업 디렉터리 밖에 쓰려고 한다",
            actions=("file.write",),
            predicate=_writes_outside_workspace,
        ),
        # -- HIGH ----------------------------------------------------------
        Rule(
            "push-and-shell",
            RiskLevel.HIGH,
            "원격 이력이나 시스템 상태를 바꾼다",
            actions=("git.push", "shell.exec", "system.control", "payment.*"),
        ),
        # -- MEDIUM --------------------------------------------------------
        Rule(
            "external-effects",
            RiskLevel.MEDIUM,
            "외부 상태나 로컬 이력을 바꾼다",
            actions=("git.commit", "browser.*", "http.*", "mcp.external.*"),
        ),
        # -- LOW -----------------------------------------------------------
        Rule(
            "local-writes",
            RiskLevel.LOW,
            "작업 디렉터리 안의 로컬 쓰기",
            actions=(
                "file.write",
                "project.register",
                "project.remember",
                "project.refresh",
                "memory.remember",
                # creator: 전부 로컬 기록이다. JUNVIS는 Instagram에 올리지 않는다.
                "content.create",
                "content.dismiss",
                "content.record_published",
                "content.update_brand_voice",
            ),
        ),
        # -- SAFE ----------------------------------------------------------
        Rule(
            "reads",
            RiskLevel.SAFE,
            "읽기 전용",
            actions=(
                "project.read",
                "project.list",
                "project.search",
                "project.context",
                "memory.recall",
                "trace.read",
                "content.list",
                "content.read",
                "brief.compose",
            ),
        ),
    )


class PolicyEngine:
    """행위를 등급으로 판정하고, 필요하면 사용자 확인을 요구한다."""

    #: 규칙에 걸리지 않은 행위의 기본값. 모르는 것은 안전하게 확인을 받는다.
    UNKNOWN_LEVEL = RiskLevel.MEDIUM

    def __init__(
        self,
        rules: Iterable[Rule] | None = None,
        confirmer: ConfirmPort | None = None,
    ) -> None:
        self._rules = tuple(rules) if rules is not None else default_rules()
        self._confirmer = confirmer

    def evaluate(self, action: Action) -> Verdict:
        for rule in self._rules:
            if rule.matches(action):
                return Verdict(rule.level, _DECISION_BY_LEVEL[rule.level], rule.reason, rule.name)
        return Verdict(
            self.UNKNOWN_LEVEL,
            _DECISION_BY_LEVEL[self.UNKNOWN_LEVEL],
            "규칙에 없는 행위이므로 확인을 요구한다",
            "unknown",
        )

    def enforce(self, action: Action) -> Verdict:
        """통과하면 Verdict를 반환하고, 아니면 예외를 던진다."""
        verdict = self.evaluate(action)
        if verdict.decision is Decision.ALLOW:
            return verdict
        if verdict.decision is Decision.DENY:
            raise PolicyDenied(f"거부됨: {action} — {verdict.reason}")
        if self._confirmer is None:
            raise PolicyConfirmationRequired(
                f"확인이 필요하지만 확인 통로가 없습니다: {action} — {verdict.reason}"
            )
        if not self._confirmer.confirm(action, verdict):
            raise PolicyDenied(f"사용자가 거부함: {action}")
        return verdict

    def guard(self, name: str, target: str = "", **context: Any) -> Verdict:
        return self.enforce(Action(name=name, target=target, context=context))

    # -- 플러그인 Capability ------------------------------------------------

    def check_capability(self, declared: Collection[str], required: str) -> None:
        """선언하지 않은 Capability는 쓸 수 없다(설계 §4).

        `memory:*` 같은 와일드카드 선언을 허용한다.
        """
        for granted in declared:
            if granted == required or granted == "*":
                return
            if granted.endswith(":*") and required.startswith(granted[:-1]):
                return
        raise PolicyDenied(f"선언되지 않은 권한입니다: {required}")
