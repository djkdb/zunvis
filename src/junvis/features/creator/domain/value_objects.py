"""creator의 값 객체.

플랫폼 규칙(Instagram 상한 등)이 여기 산다. 모델이 무엇을 뱉든
도메인을 통과하지 못하면 저장되지 않는다.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from junvis.features.creator.domain.errors import InvalidScript

#: Instagram 실제 상한. 우리가 정한 숫자가 아니라 플랫폼이 정한 숫자다.
CAPTION_MAX_CHARS = 2200
HASHTAG_MAX_COUNT = 30

_HASHTAG_CLEAN = re.compile(r"[^0-9a-z_가-힣]+")


class ContentFormat(str, Enum):
    REELS = "reels"
    CAROUSEL = "carousel"

    @property
    def label(self) -> str:
        return {"reels": "릴스", "carousel": "캐러셀"}[self.value]


class ContentStatus(str, Enum):
    """상태 기계.

    SUGGESTED ──accept──▶ DRAFTED ──publish──▶ PUBLISHED
        │                    │
        └──dismiss──▶ DISMISSED ◀──dismiss──┘
    """

    SUGGESTED = "suggested"
    DRAFTED = "drafted"
    PUBLISHED = "published"
    DISMISSED = "dismissed"


@dataclass(frozen=True, order=True)
class IdeaId:
    value: str

    @staticmethod
    def new() -> IdeaId:
        return IdeaId(uuid.uuid4().hex)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Hashtag:
    """`#` 없이 소문자로 저장하고, 출력할 때만 `#`를 붙인다."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise InvalidScript("빈 해시태그는 쓸 수 없습니다")

    @staticmethod
    def parse(raw: str) -> Hashtag | None:
        cleaned = _HASHTAG_CLEAN.sub("", raw.strip().lstrip("#").lower())
        return Hashtag(cleaned) if cleaned else None

    @staticmethod
    def many(values: Iterable[str]) -> tuple[Hashtag, ...]:
        """정규화 → 중복 제거 → 상한 검사. 순서는 입력 순서를 유지한다."""
        seen: dict[str, Hashtag] = {}
        for raw in values:
            tag = Hashtag.parse(raw)
            if tag is not None:
                seen.setdefault(tag.value, tag)
        if len(seen) > HASHTAG_MAX_COUNT:
            raise InvalidScript(
                f"해시태그는 {HASHTAG_MAX_COUNT}개까지입니다 (받은 값: {len(seen)}개)"
            )
        return tuple(seen.values())

    def __str__(self) -> str:
        return f"#{self.value}"


@dataclass(frozen=True)
class BrandVoice:
    """ZUN 브랜드의 성향.

    브리프의 콘텐츠 성향을 기본값으로 심는다. 발행 기록이 쌓이면
    여기에 되먹이는 것이 다음 단계다.
    """

    topics: tuple[str, ...] = ()
    tone: str = ""
    audience: str = ""
    banned_phrases: tuple[str, ...] = field(default=())

    @staticmethod
    def default_zun() -> BrandVoice:
        return BrandVoice(
            topics=(
                "AI",
                "바이브 코딩",
                "Claude Code",
                "MCP",
                "개발 생산성",
                "새로운 웹앱",
                "개발 브이로그",
                "프로젝트 제작기",
            ),
            tone="담백하고 직설적. 과장 없이 실제로 만든 것을 보여준다.",
            audience="AI로 무언가를 만들어보고 싶은 개발자와 예비 개발자",
            banned_phrases=("충격", "미쳤다", "이것만 알면", "1분 만에 마스터"),
        )

    def with_topics(self, topics: Iterable[str]) -> BrandVoice:
        cleaned = tuple(dict.fromkeys(t.strip() for t in topics if t and t.strip()))
        return BrandVoice(cleaned, self.tone, self.audience, self.banned_phrases)

    def describe(self) -> str:
        """프롬프트에 넣을 형태. 문자열 조립은 인프라가 아니라 여기서 한다 —
        무엇이 브랜드를 규정하는지가 도메인 지식이기 때문이다."""
        lines = []
        if self.topics:
            lines.append(f"다루는 주제: {', '.join(self.topics)}")
        if self.audience:
            lines.append(f"대상 시청자: {self.audience}")
        if self.tone:
            lines.append(f"톤: {self.tone}")
        if self.banned_phrases:
            lines.append(f"쓰지 말 것: {', '.join(self.banned_phrases)}")
        return "\n".join(lines)
