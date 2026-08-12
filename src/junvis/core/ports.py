"""여러 Bounded Context가 공유하는 application 수준 Port.

feature마다 UnitOfWork와 Clock을 각자 선언하면 같은 개념이 두 벌
생긴다. 이런 것이 Shared Kernel에 있어야 할 것들이다.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from typing import Protocol

from junvis.core.domain.event import utcnow


class UnitOfWorkPort(Protocol):
    """저장과 이벤트 발행을 한 경계로 묶는다.

    `Database.transaction`이 그대로 이 형태를 만족하므로 래퍼가 필요 없다.
    """

    def __call__(self) -> AbstractContextManager[object]: ...


class ClockPort(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    """기본 시계. 테스트는 고정 시계를 주입한다."""

    def now(self) -> datetime:
        return utcnow()
