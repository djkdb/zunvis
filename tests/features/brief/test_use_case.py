"""B3 완료 기준: Fake Port로 전 조합을 검증한다.

가장 중요한 것은 마지막 절이다 — 수집원 하나가 죽어도 브리핑은 나와야 한다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from junvis.core.eventbus.bus import EventBus
from junvis.core.trace.recorder import TraceRecorder
from junvis.core.trace.store import SqliteTraceStore
from junvis.features.brief.application.use_cases.compose_briefing import ComposeBriefing
from junvis.features.brief.domain.digests import (
    CalendarEvent,
    ContentDigest,
    HabitDigest,
    NewsItem,
    ProjectDigest,
)
from tests.features.fakes import FixedClock

NOW = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)


class FakeProjects:
    def __init__(self, digests=(), *, fail=False) -> None:
        self.digests = digests
        self.fail = fail

    def recent(self, limit: int = 10):
        if self.fail:
            raise RuntimeError("프로젝트 조회 실패")
        return self.digests[:limit]


class FakeContent:
    def __init__(self, digest=None, *, fail=False) -> None:
        self.digest_value = digest or ContentDigest()
        self.fail = fail

    def digest(self, now):
        if self.fail:
            raise RuntimeError("콘텐츠 조회 실패")
        return self.digest_value


class FakeCalendar:
    def __init__(self, events=(), *, fail=False) -> None:
        self.events = events
        self.fail = fail

    def today(self, now):
        if self.fail:
            raise PermissionError("캘린더 접근 권한 없음")
        return self.events


class FakeHabits:
    def __init__(self, digest=None) -> None:
        self.digest_value = digest

    def digest(self, now):
        return self.digest_value


class FakeNews:
    def __init__(self, items=(), *, fail=False) -> None:
        self.items = items
        self.fail = fail
        self.asked: list[tuple[str, ...]] = []

    def headlines(self, interests, *, limit=5):
        self.asked.append(interests)
        if self.fail:
            raise OSError("네트워크 없음")
        return self.items[:limit]


class FakeInterests:
    def __init__(self, topics=("AI", "MCP")) -> None:
        self.topics_value = topics

    def topics(self):
        return self.topics_value


def build(**kwargs) -> ComposeBriefing:
    defaults = dict(
        projects=FakeProjects((ProjectDigest("zunvis", "ZUNVIS", dirty=True),)),
        content=FakeContent(),
    )
    defaults.update(kwargs)
    projects = defaults.pop("projects")
    content = defaults.pop("content")
    return ComposeBriefing(projects, content, clock=FixedClock(NOW), **defaults)


# -- 기본 동작 ---------------------------------------------------------------


def test_composes_from_every_source() -> None:
    news = FakeNews((NewsItem("Claude gets better at agents", "https://x"),))
    briefing = build(
        calendar=FakeCalendar((CalendarEvent("스탠드업", NOW.replace(hour=14)),)),
        habits=FakeHabits(HabitDigest(runs_last_7d=9, busiest_hour=22)),
        news=news,
        interests=FakeInterests(),
    )()

    assert [s.title for s in briefing.sections] == [
        "오늘 일정",
        "멈춰 있는 작업",
        "진행 중인 프로젝트",
        "AI 소식",
        "작업 습관",
    ]
    assert briefing.day == NOW.date()


def test_brand_topics_are_used_to_filter_news() -> None:
    news = FakeNews()
    build(news=news, interests=FakeInterests(("바이브 코딩", "MCP")))()
    assert news.asked == [("바이브 코딩", "MCP")]


def test_news_is_skipped_when_no_port_is_wired() -> None:
    """오프라인 모드에서는 뉴스 어댑터를 아예 끼우지 않는다."""
    briefing = build(news=None)()
    assert "AI 소식" not in [s.title for s in briefing.sections]


# -- 수집원 격리 (핵심) ------------------------------------------------------


def test_calendar_permission_failure_does_not_kill_the_briefing() -> None:
    briefing = build(calendar=FakeCalendar(fail=True))()

    assert "오늘 일정" not in [s.title for s in briefing.sections]
    assert "멈춰 있는 작업" in [s.title for s in briefing.sections]


def test_network_failure_does_not_kill_the_briefing() -> None:
    briefing = build(news=FakeNews(fail=True), interests=FakeInterests())()
    assert "멈춰 있는 작업" in [s.title for s in briefing.sections]


def test_project_source_failure_still_yields_other_sections() -> None:
    briefing = build(
        projects=FakeProjects(fail=True),
        content=FakeContent(ContentDigest(drafted=(), suggested=())),
        habits=FakeHabits(HabitDigest(runs_last_7d=3)),
    )()
    assert [s.title for s in briefing.sections] == ["작업 습관"]


def test_every_source_failing_gives_an_empty_briefing_not_an_error() -> None:
    briefing = build(
        projects=FakeProjects(fail=True),
        content=FakeContent(fail=True),
        calendar=FakeCalendar(fail=True),
        news=FakeNews(fail=True),
        interests=FakeInterests(),
    )()
    assert briefing.is_empty
    assert "오늘 챙길 것이 없습니다" in briefing.to_markdown()


# -- 정책과 Trace ------------------------------------------------------------


def test_compose_is_a_safe_read(db) -> None:
    from junvis.core.policy.engine import Action, Decision, PolicyEngine

    assert PolicyEngine().evaluate(Action("brief.compose")).decision is Decision.ALLOW


def test_briefing_leaves_a_trace_with_collection_steps(db) -> None:
    store = SqliteTraceStore(db)
    build(
        tracer=TraceRecorder(store, EventBus()),
        calendar=FakeCalendar(fail=True),
    )()

    trace = store.recent()[0]
    assert trace.request == "brief.compose"
    assert trace.context["sections"] >= 1
    names = {call.name for call in trace.tool_calls}
    assert {"brief.projects", "brief.content", "brief.calendar"} <= names
    # 실패한 수집원이 Trace에 남는다 — 왜 섹션이 비었는지 나중에 알 수 있다
    failed = next(c for c in trace.tool_calls if c.name == "brief.calendar")
    assert failed.ok is False
    assert "권한" in failed.error


def test_works_without_a_tracer() -> None:
    assert build()().sections  # tracer=None 경로
