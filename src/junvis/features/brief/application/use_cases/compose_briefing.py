"""오늘의 브리핑을 조립한다."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from junvis.core.policy.engine import PolicyEngine
from junvis.core.ports import ClockPort, SystemClock
from junvis.core.trace.recorder import TraceHandle, TraceRecorder
from junvis.features.brief.application.ports import (
    CalendarPort,
    ContentDigestPort,
    HabitPort,
    InterestsPort,
    NewsPort,
    ProjectDigestPort,
)
from junvis.features.brief.domain.composer import compose
from junvis.features.brief.domain.model import Briefing

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: 브리핑에 올릴 프로젝트 수집 상한.
PROJECT_LIMIT = 10
NEWS_LIMIT = 5


class ComposeBriefing:
    """수집원 하나가 실패해도 나머지는 반영한다.

    캘린더 권한이 없다고, 네트워크가 없다고 브리핑 전체가 사라지면
    정작 필요한 아침에 아무것도 못 본다. 오프라인은 정상 상태 중 하나다.
    """

    def __init__(
        self,
        projects: ProjectDigestPort,
        content: ContentDigestPort,
        *,
        calendar: CalendarPort | None = None,
        habits: HabitPort | None = None,
        news: NewsPort | None = None,
        interests: InterestsPort | None = None,
        policy: PolicyEngine | None = None,
        clock: ClockPort | None = None,
        tracer: TraceRecorder | None = None,
    ) -> None:
        self._projects = projects
        self._content = content
        self._calendar = calendar
        self._habits = habits
        self._news = news
        self._interests = interests
        self._policy = policy
        self._clock = clock or SystemClock()
        self._tracer = tracer

    def __call__(self) -> Briefing:
        if self._policy is not None:
            self._policy.guard("brief.compose")

        now = self._clock.now()
        if self._tracer is None:
            return self._collect(now, None)
        with self._tracer.record("brief.compose") as handle:
            briefing = self._collect(now, handle)
            handle.annotate(
                sections=len(briefing.sections),
                peak_urgency=briefing.peak_urgency.name,
            )
            return briefing

    def _collect(self, now, handle: TraceHandle | None) -> Briefing:
        projects = self._safe(
            "projects", lambda: self._projects.recent(PROJECT_LIMIT), (), handle
        )
        content = self._safe("content", lambda: self._content.digest(now), None, handle)

        events = ()
        if self._calendar is not None:
            events = self._safe("calendar", lambda: self._calendar.today(now), (), handle)

        habits = None
        if self._habits is not None:
            habits = self._safe("habits", lambda: self._habits.digest(now), None, handle)

        news = ()
        if self._news is not None:
            interests = ()
            if self._interests is not None:
                interests = self._safe("interests", self._interests.topics, (), handle)
            news = self._safe(
                "news",
                lambda: self._news.headlines(interests, limit=NEWS_LIMIT),
                (),
                handle,
            )

        return compose(
            now=now,
            projects=projects,
            content=content,
            events=events,
            habits=habits,
            news=news,
        )

    def _safe(
        self, name: str, call: Callable[[], T], fallback: T, handle: TraceHandle | None
    ) -> T:
        """수집원 하나를 격리한다. 실패는 Trace에 남기고 넘어간다."""
        try:
            if handle is None:
                return call()
            with handle.tool(f"brief.{name}"):
                return call()
        except Exception as exc:
            logger.debug("브리핑 수집 실패(%s): %s", name, exc)
            return fallback
