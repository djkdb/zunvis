"""브리핑을 조립하는 데 필요한 입력의 **형태**.

`brief`는 `project_brain`도 `creator`도 임포트하지 않는다. 대신 자기가
무엇을 필요로 하는지를 여기서 스스로 정의하고, 조립 루트가 어댑터로 채운다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ProjectDigest:
    slug: str
    name: str
    purpose: str = ""
    branch: str | None = None
    dirty: bool = False
    last_commit: str | None = None
    last_commit_at: datetime | None = None
    open_todos: tuple[str, ...] = ()
    open_issues: tuple[str, ...] = ()
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ContentLine:
    id: str
    subject: str

    @property
    def short_id(self) -> str:
        return self.id[:8]


@dataclass(frozen=True)
class ContentDigest:
    suggested: tuple[ContentLine, ...] = ()
    drafted: tuple[ContentLine, ...] = ()
    last_published_at: datetime | None = None
    published_last_30d: int = 0
    has_ever_published: bool = False


@dataclass(frozen=True)
class CalendarEvent:
    title: str
    starts_at: datetime
    location: str = ""
    all_day: bool = False


@dataclass(frozen=True)
class HabitDigest:
    """Trace에서 나온 관찰.

    설계 §5.2에서 "Trace는 로그가 아니라 개인화의 원재료"라고 했던 것이
    처음으로 현금화되는 지점이다.
    """

    runs_last_7d: int = 0
    failures_last_7d: int = 0
    busiest_hour: int | None = None
    top_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    source: str = ""
