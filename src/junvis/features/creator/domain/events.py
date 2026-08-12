"""creator가 발행하는 도메인 이벤트."""

from __future__ import annotations

from dataclasses import dataclass

from junvis.core.domain.event import DomainEvent


@dataclass(frozen=True, kw_only=True)
class ContentSuggested(DomainEvent):
    """새 프로젝트를 감지해 콘텐츠를 제안했다 — 브리프의 'Content Assistant'."""

    topic = "content.suggested"

    idea_id: str
    subject: str
    content_format: str
    source_project_slug: str | None = None


@dataclass(frozen=True, kw_only=True)
class ContentDrafted(DomainEvent):
    topic = "content.drafted"

    idea_id: str
    subject: str
    content_format: str
    scene_count: int


@dataclass(frozen=True, kw_only=True)
class ContentPublished(DomainEvent):
    topic = "content.published"

    idea_id: str
    subject: str
    url: str | None = None


@dataclass(frozen=True, kw_only=True)
class ContentDismissed(DomainEvent):
    topic = "content.dismissed"

    idea_id: str
    subject: str
    reason: str = ""
