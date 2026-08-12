"""브리핑 조립 규칙 — 이 Context의 심장.

브리프의 마지막 문장이 여기 코드로 들어와 있다:
"모든 제안은 사용자의 장기 목표(개발, 프로젝트, ZUN 브랜드 성장)를 기준으로
우선순위를 판단한다."

그래서 무엇을 먼저 보여줄지가 표현 계층의 정렬이 아니라 도메인 규칙이다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from junvis.features.brief.domain.digests import (
    CalendarEvent,
    ContentDigest,
    HabitDigest,
    NewsItem,
    ProjectDigest,
)
from junvis.features.brief.domain.model import (
    BriefItem,
    BriefSection,
    Briefing,
    Urgency,
    order_sections,
)

# -- 섹션 우선순위 (docs/04-DAILY-BRIEF.md §1) --------------------------------
RANK_CALENDAR = 1
RANK_UNFINISHED = 2
RANK_TODOS = 3
RANK_ISSUES = 4
RANK_CONTENT = 5
RANK_IDEAS = 6
RANK_PROJECTS = 7
RANK_NEWS = 8
RANK_HABITS = 9

# -- ZUN 브랜드 성장이 장기 목표이므로 공백이 길수록 위로 올라온다 -------------
CONTENT_GAP_NOTICE_DAYS = 3
CONTENT_GAP_ATTENTION_DAYS = 7
CONTENT_GAP_URGENT_DAYS = 14

#: 곧 시작하는 일정은 주의를 요한다.
IMMINENT_EVENT_WINDOW = timedelta(hours=1)

#: 한 섹션이 화면을 독차지하지 않게 한다. 브리핑은 목록이 아니라 요약이다.
MAX_TODOS = 8
MAX_ISSUES = 6
MAX_IDEAS = 5
MAX_PROJECTS = 5
MAX_NEWS = 5


def compose(
    *,
    now: datetime,
    projects: tuple[ProjectDigest, ...] = (),
    content: ContentDigest | None = None,
    events: tuple[CalendarEvent, ...] = (),
    habits: HabitDigest | None = None,
    news: tuple[NewsItem, ...] = (),
) -> Briefing:
    sections = [
        _calendar_section(events, now),
        _unfinished_section(projects),
        _todo_section(projects),
        _issue_section(projects),
        _content_section(content, now),
        _idea_section(content),
        _project_section(projects),
        _news_section(news),
        _habit_section(habits),
    ]
    return Briefing(
        day=now.date(),
        sections=order_sections(sections),
        generated_at=now,
    )


# -- 1. 오늘 일정 -------------------------------------------------------------


def _calendar_section(events: tuple[CalendarEvent, ...], now: datetime) -> BriefSection:
    items = []
    for event in sorted(events, key=lambda e: e.starts_at):
        if event.all_day:
            when = "종일"
            urgency = Urgency.INFO
        else:
            when = event.starts_at.strftime("%H:%M")
            remaining = event.starts_at - now
            urgency = (
                Urgency.ATTENTION
                if timedelta(0) <= remaining <= IMMINENT_EVENT_WINDOW
                else Urgency.NOTICE
            )
        detail = event.location if event.location else ""
        items.append(BriefItem(f"{when}  {event.title}", detail, urgency))
    return BriefSection("오늘 일정", tuple(items), RANK_CALENDAR)


# -- 2. 멈춰 있는 작업 --------------------------------------------------------


def _unfinished_section(projects: tuple[ProjectDigest, ...]) -> BriefSection:
    """커밋되지 않은 변경은 잊으면 잃는다."""
    items = [
        BriefItem(
            f"{project.name}에 커밋되지 않은 변경",
            f"{project.branch or '?'} · 마지막 커밋: {project.last_commit or '없음'}",
            Urgency.ATTENTION,
            f"junvis context {project.slug}",
        )
        for project in projects
        if project.dirty
    ]
    return BriefSection("멈춰 있는 작업", tuple(items), RANK_UNFINISHED)


# -- 3~4. 할 일과 이슈 --------------------------------------------------------


def _todo_section(projects: tuple[ProjectDigest, ...]) -> BriefSection:
    items = []
    for project in projects:
        for todo in project.open_todos:
            items.append(BriefItem(todo, project.name))
            if len(items) >= MAX_TODOS:
                return BriefSection("해야 할 작업", tuple(items), RANK_TODOS)
    return BriefSection("해야 할 작업", tuple(items), RANK_TODOS)


def _issue_section(projects: tuple[ProjectDigest, ...]) -> BriefSection:
    items = []
    for project in projects:
        for issue in project.open_issues:
            items.append(BriefItem(issue, project.name))
            if len(items) >= MAX_ISSUES:
                return BriefSection("열린 이슈", tuple(items), RANK_ISSUES)
    return BriefSection("열린 이슈", tuple(items), RANK_ISSUES)


# -- 5. ZUN 콘텐츠 ------------------------------------------------------------


def content_gap_urgency(days: int) -> Urgency:
    if days >= CONTENT_GAP_URGENT_DAYS:
        return Urgency.URGENT
    if days >= CONTENT_GAP_ATTENTION_DAYS:
        return Urgency.ATTENTION
    if days >= CONTENT_GAP_NOTICE_DAYS:
        return Urgency.NOTICE
    return Urgency.INFO


def _content_section(content: ContentDigest | None, now: datetime) -> BriefSection:
    if content is None:
        return BriefSection("ZUN 콘텐츠", (), RANK_CONTENT)

    items: list[BriefItem] = []

    if content.last_published_at is not None:
        gap = (now - content.last_published_at).days
        urgency = content_gap_urgency(gap)
        if urgency is not Urgency.INFO:
            items.append(
                BriefItem(
                    f"마지막 업로드 이후 {gap}일",
                    f"최근 30일 발행 {content.published_last_30d}건",
                    urgency,
                    "junvis reel",
                )
            )
    elif content.drafted or content.suggested:
        # 아직 한 번도 발행하지 않았는데 만들어 둔 것이 있다면 그것부터다.
        items.append(
            BriefItem("아직 발행한 콘텐츠가 없습니다", "", Urgency.NOTICE, "junvis content")
        )

    if content.drafted:
        first = content.drafted[0]
        items.append(
            BriefItem(
                f"발행 대기 중인 초안 {len(content.drafted)}건",
                first.subject,
                Urgency.NOTICE,
                f"junvis show {first.short_id}",
            )
        )

    return BriefSection("ZUN 콘텐츠", tuple(items), RANK_CONTENT)


# -- 6. 대기 중인 아이디어 ----------------------------------------------------


def _idea_section(content: ContentDigest | None) -> BriefSection:
    if content is None:
        return BriefSection("대기 중인 아이디어", (), RANK_IDEAS)
    items = tuple(
        BriefItem(line.subject, "", Urgency.INFO, f"junvis reel --id {line.short_id}")
        for line in content.suggested[:MAX_IDEAS]
    )
    return BriefSection("대기 중인 아이디어", items, RANK_IDEAS)


# -- 7. 진행 중인 프로젝트 ----------------------------------------------------


def _project_section(projects: tuple[ProjectDigest, ...]) -> BriefSection:
    items = tuple(
        BriefItem(
            project.name,
            project.purpose or (project.last_commit or ""),
            Urgency.INFO,
            f"junvis context {project.slug}",
        )
        for project in projects[:MAX_PROJECTS]
    )
    return BriefSection("진행 중인 프로젝트", items, RANK_PROJECTS)


# -- 8. AI 소식 ---------------------------------------------------------------


def _news_section(news: tuple[NewsItem, ...]) -> BriefSection:
    items = tuple(
        BriefItem(item.title, item.url, Urgency.INFO) for item in news[:MAX_NEWS]
    )
    return BriefSection("AI 소식", items, RANK_NEWS)


# -- 9. 작업 습관 (Trace에서) -------------------------------------------------


def _habit_section(habits: HabitDigest | None) -> BriefSection:
    if habits is None or habits.runs_last_7d == 0:
        return BriefSection("작업 습관", (), RANK_HABITS)

    items = [
        BriefItem(f"최근 7일 동안 {habits.runs_last_7d}번 작업했습니다")
    ]
    if habits.busiest_hour is not None:
        items.append(BriefItem(f"가장 활발한 시간대: {habits.busiest_hour}시"))
    if habits.top_tools:
        items.append(BriefItem(f"자주 쓴 기능: {', '.join(habits.top_tools)}"))
    if habits.failures_last_7d:
        items.append(
            BriefItem(
                f"실패한 작업 {habits.failures_last_7d}건",
                "",
                Urgency.NOTICE,
                "junvis doctor",
            )
        )
    return BriefSection("작업 습관", tuple(items), RANK_HABITS)
