"""B2 완료 기준: 우선순위가 순수 단위 테스트로 검증된다.

브리프의 마지막 문장 — "모든 제안은 사용자의 장기 목표를 기준으로 우선순위를
판단한다" — 가 실제로 코드에 있는지 확인하는 것이 이 파일의 목적이다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from junvis.features.brief.domain.composer import (
    CONTENT_GAP_ATTENTION_DAYS,
    CONTENT_GAP_NOTICE_DAYS,
    CONTENT_GAP_URGENT_DAYS,
    MAX_TODOS,
    compose,
    content_gap_urgency,
)
from junvis.features.brief.domain.digests import (
    CalendarEvent,
    ContentDigest,
    ContentLine,
    HabitDigest,
    NewsItem,
    ProjectDigest,
)
from junvis.features.brief.domain.model import Urgency

NOW = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)


def project(**overrides) -> ProjectDigest:
    defaults = dict(slug="zunvis", name="ZUNVIS", purpose="개인 AI OS")
    defaults.update(overrides)
    return ProjectDigest(**defaults)


def titles(briefing) -> list[str]:
    return [section.title for section in briefing.sections]


# -- 빈 브리핑 ---------------------------------------------------------------


def test_nothing_to_report() -> None:
    briefing = compose(now=NOW)
    assert briefing.is_empty
    assert "오늘 챙길 것이 없습니다" in briefing.to_markdown()
    assert briefing.headline() == "오늘 챙길 것이 없습니다."


def test_empty_sections_are_dropped() -> None:
    briefing = compose(now=NOW, projects=(project(),))
    # 프로젝트는 있지만 TODO·이슈·dirty는 없다
    assert titles(briefing) == ["진행 중인 프로젝트"]


# -- 순서 --------------------------------------------------------------------


def test_sections_follow_the_designed_priority() -> None:
    briefing = compose(
        now=NOW,
        projects=(
            project(dirty=True, open_todos=("스케줄러 만들기",), open_issues=("#3 버그",)),
        ),
        content=ContentDigest(suggested=(ContentLine("a" * 32, "제작기 릴스"),)),
        events=(CalendarEvent("스탠드업", NOW + timedelta(hours=4)),),
        habits=HabitDigest(runs_last_7d=12, busiest_hour=22),
        news=(NewsItem("New AI agent framework", "https://x"),),
    )

    assert titles(briefing) == [
        "오늘 일정",
        "멈춰 있는 작업",
        "해야 할 작업",
        "열린 이슈",
        "ZUN 콘텐츠",  # 발행 이력이 없는데 제안이 쌓여 있으면 여기서 알려준다
        "대기 중인 아이디어",
        "진행 중인 프로젝트",
        "AI 소식",
        "작업 습관",
    ]


def test_urgent_content_gap_outranks_issues() -> None:
    """ZUN 브랜드 성장이 장기 목표라서, 공백이 길면 잡무를 이긴다."""
    briefing = compose(
        now=NOW,
        projects=(project(open_issues=("#3 버그",)),),
        content=ContentDigest(
            last_published_at=NOW - timedelta(days=CONTENT_GAP_URGENT_DAYS),
            has_ever_published=True,
        ),
    )

    order = titles(briefing)
    assert order.index("ZUN 콘텐츠") < order.index("열린 이슈")
    assert briefing.peak_urgency is Urgency.URGENT


def test_non_urgent_content_stays_below_issues() -> None:
    briefing = compose(
        now=NOW,
        projects=(project(open_issues=("#3 버그",)),),
        content=ContentDigest(
            last_published_at=NOW - timedelta(days=CONTENT_GAP_NOTICE_DAYS),
            has_ever_published=True,
        ),
    )
    order = titles(briefing)
    assert order.index("열린 이슈") < order.index("ZUN 콘텐츠")


# -- 콘텐츠 공백 긴급도 -------------------------------------------------------


@pytest.mark.parametrize(
    "days, expected",
    [
        (0, Urgency.INFO),
        (CONTENT_GAP_NOTICE_DAYS - 1, Urgency.INFO),
        (CONTENT_GAP_NOTICE_DAYS, Urgency.NOTICE),
        (CONTENT_GAP_ATTENTION_DAYS, Urgency.ATTENTION),
        (CONTENT_GAP_URGENT_DAYS, Urgency.URGENT),
        (100, Urgency.URGENT),
    ],
)
def test_content_gap_thresholds(days: int, expected: Urgency) -> None:
    assert content_gap_urgency(days) is expected


def test_recent_upload_produces_no_content_item() -> None:
    briefing = compose(
        now=NOW,
        content=ContentDigest(
            last_published_at=NOW - timedelta(days=1), has_ever_published=True
        ),
    )
    assert "ZUN 콘텐츠" not in titles(briefing)


def test_never_published_with_pending_work_is_flagged() -> None:
    briefing = compose(
        now=NOW,
        content=ContentDigest(drafted=(ContentLine("b" * 32, "초안 하나"),)),
    )
    section = next(s for s in briefing.sections if s.title == "ZUN 콘텐츠")
    assert "아직 발행한 콘텐츠가 없습니다" in section.items[0].text
    assert "발행 대기 중인 초안 1건" in section.items[1].text


def test_never_published_with_nothing_pending_is_silent() -> None:
    briefing = compose(now=NOW, content=ContentDigest())
    assert "ZUN 콘텐츠" not in titles(briefing)


# -- 멈춰 있는 작업 -----------------------------------------------------------


def test_dirty_tree_is_attention_with_an_action() -> None:
    briefing = compose(now=NOW, projects=(project(dirty=True, branch="main"),))
    item = next(s for s in briefing.sections if s.title == "멈춰 있는 작업").items[0]

    assert item.urgency is Urgency.ATTENTION
    assert "커밋되지 않은 변경" in item.text
    assert item.action == "junvis context zunvis"


def test_clean_tree_is_not_reported() -> None:
    briefing = compose(now=NOW, projects=(project(dirty=False),))
    assert "멈춰 있는 작업" not in titles(briefing)


# -- 일정 --------------------------------------------------------------------


def test_imminent_event_gets_attention() -> None:
    briefing = compose(
        now=NOW,
        events=(
            CalendarEvent("곧 시작", NOW + timedelta(minutes=30)),
            CalendarEvent("나중에", NOW + timedelta(hours=6)),
        ),
    )
    items = briefing.sections[0].items
    assert items[0].urgency is Urgency.ATTENTION
    assert items[1].urgency is Urgency.NOTICE


def test_all_day_event_is_rendered_as_such() -> None:
    briefing = compose(now=NOW, events=(CalendarEvent("휴가", NOW, all_day=True),))
    assert "종일" in briefing.sections[0].items[0].text


def test_events_are_sorted_by_time() -> None:
    briefing = compose(
        now=NOW,
        events=(
            CalendarEvent("두 번째", NOW + timedelta(hours=5)),
            CalendarEvent("첫 번째", NOW + timedelta(hours=2)),
        ),
    )
    assert "첫 번째" in briefing.sections[0].items[0].text


# -- 상한 --------------------------------------------------------------------


def test_todo_cap_keeps_the_briefing_a_summary() -> None:
    many = project(open_todos=tuple(f"할 일 {n}" for n in range(20)))
    briefing = compose(now=NOW, projects=(many,))
    section = next(s for s in briefing.sections if s.title == "해야 할 작업")
    assert len(section.items) == MAX_TODOS


def test_todos_span_multiple_projects() -> None:
    briefing = compose(
        now=NOW,
        projects=(
            project(slug="a", name="A", open_todos=("A의 할 일",)),
            project(slug="b", name="B", open_todos=("B의 할 일",)),
        ),
    )
    section = next(s for s in briefing.sections if s.title == "해야 할 작업")
    assert [item.detail for item in section.items] == ["A", "B"]


# -- 습관 (Trace) -------------------------------------------------------------


def test_habits_appear_only_when_there_is_activity() -> None:
    assert "작업 습관" not in titles(compose(now=NOW, habits=HabitDigest(runs_last_7d=0)))

    briefing = compose(
        now=NOW,
        habits=HabitDigest(
            runs_last_7d=30, failures_last_7d=2, busiest_hour=23, top_tools=("content.create",)
        ),
    )
    section = next(s for s in briefing.sections if s.title == "작업 습관")
    rendered = section.render()
    assert "30번" in rendered
    assert "23시" in rendered
    assert "content.create" in rendered
    assert "실패한 작업 2건" in rendered


def test_no_failures_means_no_failure_line() -> None:
    briefing = compose(now=NOW, habits=HabitDigest(runs_last_7d=5, failures_last_7d=0))
    section = next(s for s in briefing.sections if s.title == "작업 습관")
    assert all("실패" not in item.text for item in section.items)


# -- 출력 --------------------------------------------------------------------


def test_headline_is_the_top_item() -> None:
    briefing = compose(
        now=NOW,
        projects=(project(dirty=True),),
        events=(CalendarEvent("스탠드업", NOW + timedelta(hours=2)),),
    )
    assert briefing.headline().startswith("오늘 일정:")


def test_markdown_has_date_and_sections_and_actions() -> None:
    briefing = compose(now=NOW, projects=(project(dirty=True),))
    markdown = briefing.to_markdown()

    assert markdown.startswith("# 2026-08-12 브리핑")
    assert "## 멈춰 있는 작업" in markdown
    assert "→ junvis context zunvis" in markdown
    assert "! " in markdown  # ATTENTION 표시
