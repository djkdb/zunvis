"""음성 명령을 기존 기능으로 잇는 라우터.

`voice`가 아니라 조립 루트에 있는 이유: 라우터는 `brief`·`project_brain`·
`creator`를 모두 알아야 하는데, feature끼리는 서로를 임포트하지 않기
때문이다(계약 10번). 여러 Context를 아는 것은 조립 루트의 일이다.

**LLM 라우팅을 쓰지 않는다.** 음성은 오인식이 잦은 입력이다. 여기에 LLM
라우팅까지 얹으면 왜 그렇게 동작했는지 설명할 수 없는 층이 두 개가 된다.
"명령인가 아닌가"만 모델에게 묻고, 무엇을 할지는 읽을 수 있는 규칙으로 둔다.
(docs/05-VOICE.md §3)
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

from junvis.core.domain.errors import JunvisError
from junvis.features.brief.application.use_cases.compose_briefing import ComposeBriefing
from junvis.features.creator.application.use_cases.generate_content import GenerateContent
from junvis.features.creator.application.use_cases.queries import ListContent
from junvis.features.project_brain.application.use_cases.queries import ListProjects

logger = logging.getLogger(__name__)

#: 브리핑을 읽어줄 때 몇 항목까지 말할지. 음성은 길면 아무도 안 듣는다.
SPOKEN_BRIEF_ITEMS = 3
SPOKEN_PROJECTS = 3

UNKNOWN_RESPONSE = "아직 그건 못 합니다. 브리핑, 프로젝트, 릴스를 말해보세요."


def _squash(text: str) -> str:
    """띄어쓰기를 지운다.

    한국어 STT가 "릴스"를 "릴 스"로, "브리핑"을 "브리 핑"으로 내놓는다.
    도메인의 `squash`와 글자는 같지만 하는 일이 다르다 — 저쪽은 에코를
    판정하고 이쪽은 명령을 고른다. 합치면 한쪽을 고칠 때 다른 쪽이
    조용히 바뀐다.
    """
    return "".join(text.lower().split())


@dataclass(frozen=True)
class Route:
    name: str
    keywords: tuple[str, ...]
    run: Callable[[str], str]
    #: 사용자에게 보여줄 말투 그대로의 예시.
    example: str = ""

    def matches(self, squashed: str) -> bool:
        return any(_squash(keyword) in squashed for keyword in self.keywords)


class VoiceCommandRouter:
    def __init__(
        self,
        *,
        compose_brief: ComposeBriefing,
        list_projects: ListProjects,
        list_content: ListContent,
        generate_content: GenerateContent,
    ) -> None:
        self._compose_brief = compose_brief
        self._list_projects = list_projects
        self._list_content = list_content
        self._generate_content = generate_content
        # 순서가 곧 우선순위다. 먼저 걸리는 규칙이 이긴다.
        self._routes = (
            Route("brief", ("브리핑", "브리프", "오늘", "brief"), self._brief, "오늘 브리핑"),
            Route("content", ("릴스", "캐러셀", "콘텐츠", "reel"), self._content, "릴스 만들어줘"),
            Route("projects", ("프로젝트", "project"), self._projects, "프로젝트 목록"),
        )

    def examples(self) -> tuple[str, ...]:
        """규칙에서 직접 뽑는다. 안내와 실제가 어긋날 수 없다."""
        return tuple(route.example for route in self._routes)

    def handle(self, command: str) -> str:
        squashed = _squash(command)
        for route in self._routes:
            if route.matches(squashed):
                try:
                    return route.run(command)
                except JunvisError as exc:
                    logger.debug("음성 명령 실패(%s): %s", route.name, exc)
                    return f"{route.name} 처리 중 문제가 생겼습니다."
        return UNKNOWN_RESPONSE

    # -- 각 경로 -------------------------------------------------------------

    def _brief(self, _command: str) -> str:
        briefing = self._compose_brief()
        if briefing.is_empty:
            return "오늘 챙길 것은 없습니다."
        lines = [f"{briefing.day.month}월 {briefing.day.day}일 브리핑입니다."]
        for section in briefing.sections[:SPOKEN_BRIEF_ITEMS]:
            lines.append(f"{section.title}, {section.items[0].text}.")
        return " ".join(lines)

    def _projects(self, _command: str) -> str:
        summaries = self._list_projects()
        if not summaries:
            # 빈손으로 끝내지 않는다. 다음에 뭘 하면 되는지 말해 준다.
            return "아직 등록된 프로젝트가 없습니다. 터미널에서 junvis add 로 등록하세요."
        names = ", ".join(s.name for s in summaries[:SPOKEN_PROJECTS])
        if len(summaries) > SPOKEN_PROJECTS:
            return f"프로젝트 {len(summaries)}개가 있습니다. 최근 것은 {names}입니다."
        return f"프로젝트는 {names}입니다."

    def _content(self, command: str) -> str:
        """"릴스 만들자" → 대기 중인 제안을 채우거나 들은 주제로 새로 만든다."""
        subject = _extract_subject(command)
        if subject:
            detail = self._generate_content(subject=subject)
            return f"{detail.summary.subject} 기획을 만들었습니다. 훅은, {detail.summary.hook}"

        pending = self._list_content(status="suggested", limit=1)
        if not pending:
            return "만들 주제를 말해주세요."
        detail = self._generate_content(idea_id=pending[0].id)
        return f"{detail.summary.subject} 기획을 만들었습니다. 훅은, {detail.summary.hook}"


#: 명령에서 주제를 뽑을 때 걷어낼 상투어.
_FILLER = (
    "릴스", "캐러셀", "콘텐츠", "reel",
    "만들어줘", "만들자", "만들어", "하나", "좀", "해줘", "주제로", "주제",
)


def _extract_subject(command: str) -> str:
    """"릴스 하나 만들자" → 빈 문자열, "MCP 릴스 만들어줘" → "MCP".

    상투어도 띄어서 들린다. "릴 스 만들어 줘"에서 걷어내지 못하면 그것이
    통째로 릴스 **주제**가 된다 — 조용히 엉뚱한 기획을 만드는 쪽이
    못 알아듣는 것보다 나쁘다.
    """
    text = command
    for filler in _FILLER:
        text = _loose(filler).sub(" ", text)
    return " ".join(text.split()).strip(" ,.!?~")


def _loose(token: str) -> re.Pattern[str]:
    return re.compile(r"\s*".join(re.escape(ch) for ch in token if not ch.isspace()))
