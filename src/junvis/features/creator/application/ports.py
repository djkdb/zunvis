"""creator가 필요로 하는 바깥 세계의 계약."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from junvis.core.ports import ClockPort, SystemClock, UnitOfWorkPort
from junvis.features.creator.domain.model import ReelScript
from junvis.features.creator.domain.value_objects import BrandVoice, ContentFormat

__all__ = [
    "ClockPort",
    "SystemClock",
    "UnitOfWorkPort",
    "GenerationRequest",
    "ScriptGeneratorPort",
    "ProjectContextPort",
]


@dataclass(frozen=True)
class GenerationRequest:
    subject: str
    content_format: ContentFormat
    brand_voice: BrandVoice
    project_context: str | None = None
    direction: str = ""


class ScriptGeneratorPort(Protocol):
    """대본 생성기.

    LLM 호출·프롬프트 조립·JSON 파싱은 전부 이 뒤에 숨는다. 유스케이스는
    "요청을 주면 ReelScript가 나온다"만 안다. 덕분에 Fake 생성기로
    유스케이스를 전부 검증할 수 있다.
    """

    def generate(self, request: GenerationRequest) -> ReelScript: ...


class ProjectContextPort(Protocol):
    """프로젝트 컨텍스트를 읽는 통로.

    `creator`는 `project_brain`을 임포트하지 않는다. 조립 루트가
    `LoadProjectContext`를 이 자리에 끼운다(docs/03-CREATOR-MODE.md §1).
    """

    def get_context(self, slug: str, *, budget_tokens: int = 800) -> str | None:
        """모르는 프로젝트면 None. 없다고 콘텐츠 생성이 실패하면 안 된다."""
