"""creator 유스케이스가 주고받는 자료구조."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from junvis.features.creator.domain.model import ContentIdea


@dataclass(frozen=True)
class ContentSummary:
    id: str
    subject: str
    content_format: str
    status: str
    source_project_slug: str | None
    hook: str | None
    scene_count: int
    duration_seconds: float
    hashtags: tuple[str, ...]
    published_url: str | None
    updated_at: datetime

    @classmethod
    def of(cls, idea: ContentIdea) -> ContentSummary:
        script = idea.script
        return cls(
            id=idea.id.value,
            subject=idea.subject,
            content_format=idea.content_format.value,
            status=idea.status.value,
            source_project_slug=idea.source_project_slug,
            hook=script.hook if script else None,
            scene_count=len(script.scenes) if script else 0,
            duration_seconds=script.total_duration if script else 0.0,
            hashtags=tuple(str(tag) for tag in script.hashtags) if script else (),
            published_url=idea.published_url,
            updated_at=idea.updated_at,
        )


@dataclass(frozen=True)
class ContentDetail:
    """전체 대본까지 포함한 표현. 조회 시에만 만든다."""

    summary: ContentSummary
    markdown: str

    @classmethod
    def of(cls, idea: ContentIdea) -> ContentDetail:
        markdown = (
            idea.script.to_markdown(idea.subject)
            if idea.script
            else f"# {idea.subject}\n\n(아직 대본이 없습니다 — 제안 상태)"
        )
        return cls(summary=ContentSummary.of(idea), markdown=markdown)
