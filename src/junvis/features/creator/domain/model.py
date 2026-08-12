"""creator의 애그리게이트.

`ContentIdea`가 루트다. 대본은 통째로 교체되는 불변 값이며,
상태 전이는 전부 여기를 통과한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from junvis.core.domain.event import DomainEvent, utcnow
from junvis.features.creator.domain.errors import InvalidScript, InvalidStateTransition
from junvis.features.creator.domain.events import (
    ContentDismissed,
    ContentDrafted,
    ContentPublished,
    ContentSuggested,
)
from junvis.features.creator.domain.value_objects import (
    CAPTION_MAX_CHARS,
    ContentFormat,
    ContentStatus,
    Hashtag,
    IdeaId,
)


@dataclass(frozen=True)
class Scene:
    order: int
    visual: str
    narration: str
    duration_seconds: float = 3.0

    def __post_init__(self) -> None:
        if not self.visual.strip() and not self.narration.strip():
            raise InvalidScript(f"{self.order}번 장면이 비어 있습니다")
        if self.duration_seconds <= 0:
            raise InvalidScript(f"{self.order}번 장면의 길이가 0 이하입니다")


@dataclass(frozen=True)
class ReelScript:
    """브리프가 요구한 9개 구성요소 중 대본에 해당하는 전부.

    (주제는 `ContentIdea.subject`가 들고 있다.)
    """

    hook: str
    scenes: tuple[Scene, ...]
    caption: str
    hashtags: tuple[Hashtag, ...] = ()
    broll: tuple[str, ...] = ()
    thumbnail_text: str = ""
    comment_bait: str = ""

    def __post_init__(self) -> None:
        if not self.hook.strip():
            raise InvalidScript("Hook이 없습니다. 첫 3초가 없으면 릴스가 아닙니다")
        if not self.scenes:
            raise InvalidScript("장면이 하나도 없습니다")
        if len(self.caption) > CAPTION_MAX_CHARS:
            raise InvalidScript(
                f"캡션이 {CAPTION_MAX_CHARS}자를 넘습니다 (현재 {len(self.caption)}자)"
            )

    @property
    def total_duration(self) -> float:
        return round(sum(scene.duration_seconds for scene in self.scenes), 1)

    def hashtag_line(self) -> str:
        return " ".join(str(tag) for tag in self.hashtags)

    def to_markdown(self, subject: str) -> str:
        lines = [
            f"# {subject}",
            f"\n## Hook\n{self.hook}",
            f"\n## 장면 구성 (총 {self.total_duration}초)",
        ]
        for scene in self.scenes:
            lines.append(
                f"{scene.order}. [{scene.duration_seconds}초] {scene.visual}\n"
                f"   > {scene.narration}"
            )
        if self.broll:
            lines.append("\n## B-roll 아이디어")
            lines.extend(f"- {idea}" for idea in self.broll)
        if self.thumbnail_text:
            lines.append(f"\n## 썸네일 문구\n{self.thumbnail_text}")
        lines.append(f"\n## 캡션\n{self.caption}")
        if self.hashtags:
            lines.append(f"\n## 해시태그\n{self.hashtag_line()}")
        if self.comment_bait:
            lines.append(f"\n## 댓글 유도\n{self.comment_bait}")
        return "\n".join(lines)


@dataclass
class ContentIdea:
    """애그리게이트 루트."""

    id: IdeaId
    subject: str
    content_format: ContentFormat = ContentFormat.REELS
    status: ContentStatus = ContentStatus.SUGGESTED
    source_project_slug: str | None = None
    script: ReelScript | None = None
    published_url: str | None = None
    performance_note: str = ""
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    published_at: datetime | None = None
    _events: list[DomainEvent] = field(default_factory=list, repr=False, compare=False)

    # -- 생성 ---------------------------------------------------------------

    @classmethod
    def suggest(
        cls,
        subject: str,
        *,
        content_format: ContentFormat = ContentFormat.REELS,
        source_project_slug: str | None = None,
        now: datetime | None = None,
        idea_id: IdeaId | None = None,
    ) -> ContentIdea:
        """아직 대본이 없는 제안. `project.registered`를 듣고 만들어진다."""
        cleaned = subject.strip()
        if not cleaned:
            raise InvalidScript("주제가 비어 있습니다")
        moment = now or utcnow()
        idea = cls(
            id=idea_id or IdeaId.new(),
            subject=cleaned,
            content_format=content_format,
            status=ContentStatus.SUGGESTED,
            source_project_slug=source_project_slug,
            created_at=moment,
            updated_at=moment,
        )
        idea._record(
            ContentSuggested(
                idea_id=idea.id.value,
                subject=idea.subject,
                content_format=content_format.value,
                source_project_slug=source_project_slug,
            )
        )
        return idea

    # -- 전이 ---------------------------------------------------------------

    def attach_script(self, script: ReelScript, *, now: datetime | None = None) -> None:
        if self.status is ContentStatus.DISMISSED:
            raise InvalidStateTransition("버린 아이디어에는 대본을 붙일 수 없습니다")
        if self.status is ContentStatus.PUBLISHED:
            raise InvalidStateTransition("이미 발행된 콘텐츠는 고칠 수 없습니다")
        self.script = script
        self.status = ContentStatus.DRAFTED
        self.updated_at = now or utcnow()
        self._record(
            ContentDrafted(
                idea_id=self.id.value,
                subject=self.subject,
                content_format=self.content_format.value,
                scene_count=len(script.scenes),
            )
        )

    def dismiss(self, reason: str = "", *, now: datetime | None = None) -> None:
        if self.status is ContentStatus.PUBLISHED:
            raise InvalidStateTransition("발행된 콘텐츠는 버릴 수 없습니다")
        self.status = ContentStatus.DISMISSED
        self.updated_at = now or utcnow()
        self._record(
            ContentDismissed(idea_id=self.id.value, subject=self.subject, reason=reason)
        )

    def mark_published(
        self, url: str | None = None, *, now: datetime | None = None
    ) -> None:
        """대본 없이 발행할 수 없다 — 도메인 불변식."""
        if self.script is None:
            raise InvalidStateTransition("대본이 없는 콘텐츠는 발행할 수 없습니다")
        if self.status is ContentStatus.DISMISSED:
            raise InvalidStateTransition("버린 아이디어는 발행할 수 없습니다")
        moment = now or utcnow()
        self.status = ContentStatus.PUBLISHED
        self.published_url = url
        self.published_at = moment
        self.updated_at = moment
        self._record(
            ContentPublished(idea_id=self.id.value, subject=self.subject, url=url)
        )

    def record_performance(self, note: str, *, now: datetime | None = None) -> None:
        """발행 후 반응. 브랜드 성향 학습의 원재료가 된다."""
        if self.status is not ContentStatus.PUBLISHED:
            raise InvalidStateTransition("발행되지 않은 콘텐츠의 성과는 기록할 수 없습니다")
        self.performance_note = note.strip()
        self.updated_at = now or utcnow()

    # -- 이벤트 -------------------------------------------------------------

    def _record(self, event: DomainEvent) -> None:
        self._events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        events, self._events = list(self._events), []
        return events
