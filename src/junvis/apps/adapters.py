"""feature 사이를 잇는 어댑터.

`creator`는 `project_brain`을 임포트하지 않는다. 둘은 여기, 조립 루트에서
만난다. 이 파일이 없다면 두 Context가 직접 결합했을 것이다.
"""

from __future__ import annotations

import logging

from datetime import datetime

from junvis.core.domain.errors import JunvisError
from junvis.features.brief.domain.digests import ContentDigest, ContentLine, ProjectDigest
from junvis.features.creator.application.use_cases.queries import GetBrandVoice, ListContent
from junvis.features.project_brain.application.use_cases.load_context import (
    LoadProjectContext,
)
from junvis.features.project_brain.application.use_cases.queries import ListProjects

logger = logging.getLogger(__name__)

#: 콘텐츠 집계에 쓸 조회 상한. 개인 규모에서 이보다 많을 일은 없다.
CONTENT_SCAN_LIMIT = 200
RECENT_PUBLISH_WINDOW_DAYS = 30


class ProjectContextAdapter:
    """`ProjectContextPort` 자리에 `LoadProjectContext`를 끼운다."""

    def __init__(self, load_context: LoadProjectContext) -> None:
        self._load_context = load_context

    def get_context(self, slug: str, *, budget_tokens: int = 800) -> str | None:
        """모르는 프로젝트는 None을 돌려준다.

        콘텐츠 생성은 프로젝트 정보가 없어도 성립해야 한다. 주제만 가지고
        만드는 릴스도 1급 시민이다.
        """
        try:
            return self._load_context(slug, budget_tokens=budget_tokens).to_markdown()
        except JunvisError as exc:
            logger.debug("프로젝트 컨텍스트를 읽지 못함(%s): %s", slug, exc)
            return None


class ProjectDigestAdapter:
    """`brief`의 `ProjectDigestPort` 자리에 `project_brain`을 끼운다."""

    def __init__(self, list_projects: ListProjects) -> None:
        self._list_projects = list_projects

    def recent(self, limit: int = 10) -> tuple[ProjectDigest, ...]:
        return tuple(
            ProjectDigest(
                slug=summary.slug,
                name=summary.name,
                purpose=summary.purpose,
                branch=summary.branch,
                dirty=summary.dirty,
                last_commit=summary.last_commit,
                last_commit_at=summary.last_commit_at,
                open_todos=summary.open_todos,
                open_issues=summary.open_issues,
                updated_at=summary.updated_at,
            )
            for summary in self._list_projects()[:limit]
        )


class ContentDigestAdapter:
    """`brief`의 `ContentDigestPort` 자리에 `creator`를 끼운다."""

    def __init__(self, list_content: ListContent) -> None:
        self._list_content = list_content

    def digest(self, now: datetime) -> ContentDigest:
        items = self._list_content(limit=CONTENT_SCAN_LIMIT)
        published = [
            item
            for item in items
            if item.status == "published" and item.published_at is not None
        ]
        return ContentDigest(
            suggested=tuple(
                ContentLine(item.id, item.subject)
                for item in items
                if item.status == "suggested"
            ),
            drafted=tuple(
                ContentLine(item.id, item.subject)
                for item in items
                if item.status == "drafted"
            ),
            last_published_at=(
                max(item.published_at for item in published) if published else None
            ),
            published_last_30d=sum(
                1
                for item in published
                if (now - item.published_at).days <= RECENT_PUBLISH_WINDOW_DAYS
            ),
            has_ever_published=bool(published),
        )


class BrandInterestsAdapter:
    """뉴스를 거를 관심 주제로 ZUN 브랜드 주제를 그대로 쓴다."""

    def __init__(self, get_brand_voice: GetBrandVoice) -> None:
        self._get_brand_voice = get_brand_voice

    def topics(self) -> tuple[str, ...]:
        return tuple(self._get_brand_voice().topics)
