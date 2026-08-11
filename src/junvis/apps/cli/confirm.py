"""터미널에서의 사용자 확인 통로.

MCP 서버에서는 Elicitation이 같은 자리를 맡는다. PolicyEngine은
어느 쪽인지 모른 채 ConfirmPort만 본다.
"""

from __future__ import annotations

import sys

from junvis.core.policy.engine import Action, Verdict


class TerminalConfirmer:
    def __init__(self, assume_yes: bool = False) -> None:
        self._assume_yes = assume_yes

    def confirm(self, action: Action, verdict: Verdict) -> bool:
        if self._assume_yes:
            return True
        if not sys.stdin.isatty():
            # 물어볼 사람이 없으면 승인하지 않는다. 침묵은 동의가 아니다.
            return False
        print(f"\n[{verdict.level.name}] {action}\n  이유: {verdict.reason}")
        answer = input("  진행할까요? [y/N] ").strip().lower()
        return answer in {"y", "yes"}
