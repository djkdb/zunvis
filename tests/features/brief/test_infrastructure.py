"""B4 완료 기준: Trace 분석은 실제 SQLite로, 나머지는 파서·필터 단위로."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from junvis.features.brief.infrastructure.calendar_adapter import (
    FIELD_SEP,
    RECORD_SEP,
    MacCalendarAdapter,
)
from junvis.features.brief.infrastructure.habit_analyzer import TraceHabitAnalyzer
from junvis.features.brief.infrastructure.news_adapter import HackerNewsAdapter
from junvis.features.brief.infrastructure.notifier import _escape

NOW = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)


# -- Trace 습관 분석 ---------------------------------------------------------


def add_trace(db, *, request: str, outcome: str = "ok", at: datetime = NOW) -> None:
    db.execute(
        "INSERT INTO traces (id, request, outcome, occurred_at) VALUES (?,?,?,?)",
        (f"{request}-{at.isoformat()}-{outcome}", request, outcome, at.isoformat()),
    )


def test_no_traces_means_no_habits(db) -> None:
    assert TraceHabitAnalyzer(db).digest(NOW) is None


def test_counts_runs_and_failures(db) -> None:
    add_trace(db, request="project.context")
    add_trace(db, request="content.create", outcome="error", at=NOW - timedelta(hours=1))
    add_trace(db, request="content.create", at=NOW - timedelta(hours=2))

    digest = TraceHabitAnalyzer(db).digest(NOW)

    assert digest.runs_last_7d == 3
    assert digest.failures_last_7d == 1


def test_top_tools_are_ranked_by_frequency(db) -> None:
    for index in range(5):
        add_trace(db, request="content.create", at=NOW - timedelta(minutes=index))
    for index in range(2):
        add_trace(db, request="project.list", at=NOW - timedelta(hours=index + 1))

    digest = TraceHabitAnalyzer(db).digest(NOW)
    assert digest.top_tools[0] == "content.create"
    assert "project.list" in digest.top_tools


def test_traces_outside_the_window_are_ignored(db) -> None:
    add_trace(db, request="old", at=NOW - timedelta(days=8))
    add_trace(db, request="recent", at=NOW - timedelta(days=1))

    digest = TraceHabitAnalyzer(db).digest(NOW)
    assert digest.runs_last_7d == 1
    assert digest.top_tools == ("recent",)


def test_busiest_hour_is_reported_in_local_time(db) -> None:
    """저장은 UTC지만 사용자가 알고 싶은 것은 자기 시간대의 활동 시간대다."""
    moment = NOW - timedelta(hours=3)
    for index in range(3):
        add_trace(db, request="x", at=moment + timedelta(minutes=index))

    digest = TraceHabitAnalyzer(db).digest(NOW)
    assert digest.busiest_hour == moment.astimezone().hour


def test_unparseable_timestamp_does_not_crash(db) -> None:
    db.execute(
        "INSERT INTO traces (id, request, outcome, occurred_at) VALUES (?,?,?,?)",
        ("bad", "x", "ok", "9999-99-99"),
    )
    add_trace(db, request="good")
    digest = TraceHabitAnalyzer(db).digest(NOW)
    assert digest is not None
    assert digest.runs_last_7d >= 1


# -- 캘린더 파서 -------------------------------------------------------------


def record(title: str, when: str, location: str = "", all_day: str = "false") -> str:
    return FIELD_SEP.join([title, when, location, all_day]) + RECORD_SEP


def test_parses_applescript_output() -> None:
    output = (
        record("스탠드업", "Wednesday, August 12, 2026 at 02:30:00 PM", "회의실 A")
        + record("휴가", "Wednesday, August 12, 2026 at 12:00:00 AM", "missing value", "true")
    )

    events = MacCalendarAdapter.parse(output, NOW)

    assert [e.title for e in events] == ["휴가", "스탠드업"]  # 시간순 정렬
    assert events[1].location == "회의실 A"
    assert events[0].all_day is True
    assert events[0].location == ""  # "missing value"는 빈 값으로 다룬다


def test_parser_skips_malformed_records() -> None:
    output = record("정상", "Wednesday, August 12, 2026 at 09:00:00 AM") + "쓰레기" + RECORD_SEP
    assert len(MacCalendarAdapter.parse(output, NOW)) == 1


def test_unknown_date_format_falls_back_to_start_of_day() -> None:
    output = record("이상한 날짜", "알 수 없는 형식")
    events = MacCalendarAdapter.parse(output, NOW)
    assert len(events) == 1
    assert events[0].starts_at.hour == 0


def test_empty_output_is_no_events() -> None:
    assert MacCalendarAdapter.parse("", NOW) == ()


def test_calendar_is_silent_off_macos() -> None:
    # 테스트 환경은 Linux다. 플랫폼 검사가 osascript 호출 자체를 막는다.
    assert MacCalendarAdapter().today(NOW) == ()


# -- 뉴스 --------------------------------------------------------------------


class StubNews(HackerNewsAdapter):
    def __init__(self, hits, **kwargs) -> None:
        super().__init__(**kwargs)
        self.hits = hits

    def _fetch(self):
        return {"hits": self.hits}


def hit(title: str, url: str = "https://example.com", object_id: str = "1") -> dict:
    return {"title": title, "url": url, "objectID": object_id}


def test_filters_by_default_ai_keywords() -> None:
    adapter = StubNews(
        [
            hit("New LLM agent framework released"),
            hit("How to bake sourdough bread"),
            hit("Ollama adds structured outputs"),
        ]
    )

    items = adapter.headlines(())

    assert [i.title for i in items] == [
        "New LLM agent framework released",
        "Ollama adds structured outputs",
    ]


def test_brand_topics_widen_the_filter() -> None:
    adapter = StubNews([hit("Swift 7 ships with new concurrency model")])

    assert adapter.headlines(()) == ()  # 기본 AI 키워드로는 안 걸린다
    assert len(adapter.headlines(("Swift",))) == 1  # 브랜드 주제로는 걸린다


def test_limit_is_respected() -> None:
    adapter = StubNews([hit(f"AI story {n}", object_id=str(n)) for n in range(10)])
    assert len(adapter.headlines((), limit=3)) == 3


def test_missing_url_falls_back_to_the_discussion_link() -> None:
    adapter = StubNews([{"title": "AI thing", "objectID": "42"}])
    assert adapter.headlines(())[0].url == "https://news.ycombinator.com/item?id=42"


def test_network_failure_gives_no_news() -> None:
    # 아무도 듣고 있지 않은 주소. 예외 대신 빈 결과여야 한다.
    adapter = HackerNewsAdapter(api_url="http://127.0.0.1:1/", timeout=2)
    assert adapter.headlines(("AI",)) == ()


def test_untitled_entries_are_skipped() -> None:
    assert StubNews([{"title": "  ", "url": "x"}]).headlines(()) == ()


def test_keywords_match_on_word_boundaries_not_substrings() -> None:
    """부분 문자열로 비교하면 'ai'가 'maintain'에 걸려 섹션이 쓰레기가 된다."""
    adapter = StubNews(
        [
            hit("How we maintain our monorepo", object_id="1"),
            hit("A chair design retrospective", object_id="2"),
            hit("Agentless deployment tooling", object_id="3"),
            hit("Building an AI agent from scratch", object_id="4"),
        ]
    )
    assert [i.title for i in adapter.headlines(())] == [
        "Building an AI agent from scratch"
    ]


def test_multi_word_interest_uses_substring_matching() -> None:
    adapter = StubNews([hit("바이브 코딩으로 만든 웹앱")])
    assert len(adapter.headlines(("바이브 코딩",))) == 1


# -- 알림 --------------------------------------------------------------------


def test_notification_text_is_escaped() -> None:
    """AppleScript 문자열 안에 따옴표가 들어가면 스크립트가 깨진다."""
    assert _escape('그는 "안녕"이라고 했다') == '그는 \\"안녕\\"이라고 했다'
    assert _escape("경로: C:\\temp") == "경로: C:\\\\temp"
