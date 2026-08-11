"""도메인 이벤트의 공통 기반 타입.

이 모듈은 표준 라이브러리 외에는 아무것도 임포트하지 않는다.
(docs/02-ARCHITECTURE.md §1 의존성 규칙 1)
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import PurePath
from typing import Any, ClassVar


def utcnow() -> datetime:
    """시스템 전체가 쓰는 단일 시각 소스. 항상 UTC aware."""
    return datetime.now(timezone.utc)


def jsonable(value: Any) -> Any:
    """도메인 값을 JSON 직렬화 가능한 형태로 낮춘다.

    Outbox·Trace 저장과 MCP 응답이 같은 표현을 쓰도록 한 곳에 모았다.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, PurePath):
        return str(value)
    if isinstance(value, Enum):
        return jsonable(value.value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: jsonable(getattr(value, f.name))
            for f in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [jsonable(v) for v in value]
    return str(value)


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """모든 도메인 이벤트의 기반.

    `kw_only=True`라서 하위 클래스가 필수 필드를 자유롭게 추가할 수 있다.
    토픽은 `<context>.<과거형 사실>` 규칙을 따른다.
    """

    topic: ClassVar[str] = "domain.event"
    occurred_at: datetime = field(default_factory=utcnow)

    def payload(self) -> dict[str, Any]:
        """occurred_at을 제외한 나머지 필드를 직렬화한다.

        occurred_at은 봉투(EventEnvelope)가 별도로 들고 있으므로 중복시키지 않는다.
        """
        return {
            f.name: jsonable(getattr(self, f.name))
            for f in dataclasses.fields(self)
            if f.name != "occurred_at"
        }


@dataclass(frozen=True)
class EventEnvelope:
    """전달 경로(동기/비동기)와 무관하게 핸들러가 받는 단일 형태.

    비동기 핸들러는 프로세스 재시작 뒤 payload(JSON)만으로 복원되므로,
    동기 핸들러도 같은 봉투를 받게 해서 핸들러 시그니처를 하나로 유지한다.
    """

    topic: str
    payload: dict[str, Any]
    occurred_at: datetime

    @classmethod
    def of(cls, event: DomainEvent) -> EventEnvelope:
        return cls(
            topic=type(event).topic,
            payload=event.payload(),
            occurred_at=event.occurred_at,
        )
