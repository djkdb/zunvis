"""feature 사이를 잇는 어댑터.

`creator`는 `project_brain`을 임포트하지 않는다. 둘은 여기, 조립 루트에서
만난다. 이 파일이 없다면 두 Context가 직접 결합했을 것이다.
"""

from __future__ import annotations

import logging

from junvis.core.domain.errors import JunvisError
from junvis.features.project_brain.application.use_cases.load_context import (
    LoadProjectContext,
)

logger = logging.getLogger(__name__)


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
