"""brief가 필요로 하는 바깥 세계의 계약."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from junvis.features.brief.domain.digests import (
    CalendarEvent,
    ContentDigest,
    HabitDigest,
    NewsItem,
    ProjectDigest,
)

__all__ = [
    "ProjectDigestPort",
    "ContentDigestPort",
    "CalendarPort",
    "HabitPort",
    "NewsPort",
    "InterestsPort",
]


class ProjectDigestPort(Protocol):
    def recent(self, limit: int = 10) -> tuple[ProjectDigest, ...]: ...


class ContentDigestPort(Protocol):
    def digest(self, now: datetime) -> ContentDigest: ...


class CalendarPort(Protocol):
    def today(self, now: datetime) -> tuple[CalendarEvent, ...]:
        """읽을 수 없으면 빈 튜플. 권한이 없다고 브리핑이 실패하면 안 된다."""


class HabitPort(Protocol):
    def digest(self, now: datetime) -> HabitDigest | None: ...


class InterestsPort(Protocol):
    def topics(self) -> tuple[str, ...]:
        """뉴스를 거를 관심 주제. 사용자의 브랜드 주제를 그대로 쓴다."""


class NewsPort(Protocol):
    def headlines(
        self, interests: tuple[str, ...], *, limit: int = 5
    ) -> tuple[NewsItem, ...]: ...
