"""Personal Memory의 도메인.

핵심은 저장이 아니라 **주입**이다. 회상 결과를 그대로 프롬프트에 부으면
로컬 소형 모델이 무너진다. 그래서 회상(`recall`)과 주입(`digest`)을
다른 일로 나눈다.
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from junvis.core.domain.event import utcnow
from junvis.features.memory.domain.errors import InvalidMemory

#: 한 기억이 예산을 독차지하지 않도록 한 줄 상한을 둔다.
MAX_LINE_CHARS = 180
#: digest에 넣을 최대 줄 수. 이보다 많으면 모델이 앞부분을 놓친다.
MAX_DIGEST_LINES = 12

#: 점수 가중치. 관련도가 기본이고 최근성과 회상 빈도가 보정한다.
RECENCY_HALF_LIFE = timedelta(days=30)
RECENCY_WEIGHT = 0.5
RECALL_WEIGHT = 0.2
PINNED_BOOST = 1000.0  # 고정된 기억은 언제나 먼저


class MemoryScope(str, Enum):
    """Mem0의 User/Session/Agent 분리에서 가져오되 우리 도메인 언어로 바꿨다."""

    USER = "user"
    PROJECT = "project"
    CONTENT = "content"

    @property
    def label(self) -> str:
        return {"user": "사용자", "project": "프로젝트", "content": "콘텐츠"}[self.value]


def normalize(text: str) -> str:
    """중복 판정용 정규화. 표현만 다른 같은 사실을 두 번 넣지 않기 위해."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w가-힣\s]", "", text.lower())).strip()


@dataclass(frozen=True)
class MemoryEntry:
    id: str
    text: str
    scope: MemoryScope = MemoryScope.USER
    subject: str = ""  # 프로젝트 slug 등, 스코프 안에서의 대상
    tags: tuple[str, ...] = ()
    source: str = "user"  # user | event:<topic>
    pinned: bool = False
    created_at: datetime = field(default_factory=utcnow)
    last_recalled_at: datetime | None = None
    recall_count: int = 0

    @staticmethod
    def create(
        text: str,
        *,
        scope: MemoryScope = MemoryScope.USER,
        subject: str = "",
        tags: tuple[str, ...] = (),
        source: str = "user",
        pinned: bool = False,
        now: datetime | None = None,
    ) -> MemoryEntry:
        cleaned = " ".join(text.split())
        if not cleaned:
            raise InvalidMemory("빈 기억은 남길 수 없습니다")
        return MemoryEntry(
            id=uuid.uuid4().hex,
            text=cleaned,
            scope=scope,
            subject=subject.strip(),
            tags=tuple(dict.fromkeys(t.strip() for t in tags if t.strip())),
            source=source,
            pinned=pinned,
            created_at=now or utcnow(),
        )

    @property
    def normalized(self) -> str:
        return normalize(self.text)

    def recalled(self, now: datetime) -> MemoryEntry:
        """회상될 때마다 쓰임새가 쌓인다. 자주 쓰이는 기억이 위로 올라온다."""
        return MemoryEntry(
            id=self.id,
            text=self.text,
            scope=self.scope,
            subject=self.subject,
            tags=self.tags,
            source=self.source,
            pinned=self.pinned,
            created_at=self.created_at,
            last_recalled_at=now,
            recall_count=self.recall_count + 1,
        )

    def pin(self, pinned: bool = True) -> MemoryEntry:
        return MemoryEntry(
            id=self.id,
            text=self.text,
            scope=self.scope,
            subject=self.subject,
            tags=self.tags,
            source=self.source,
            pinned=pinned,
            created_at=self.created_at,
            last_recalled_at=self.last_recalled_at,
            recall_count=self.recall_count,
        )


@dataclass(frozen=True)
class Recall:
    """회상 질의."""

    query: str = ""
    scope: MemoryScope | None = None
    subject: str = ""
    limit: int = 20


@dataclass(frozen=True)
class MemoryHit:
    entry: MemoryEntry
    relevance: float = 1.0

    def score(self, now: datetime) -> float:
        """관련도 + 최근성 + 회상 빈도. 고정된 기억은 항상 먼저."""
        if self.entry.pinned:
            return PINNED_BOOST + self.relevance

        age = max((now - self.entry.created_at).total_seconds(), 0.0)
        half_life = RECENCY_HALF_LIFE.total_seconds()
        recency = math.pow(0.5, age / half_life) if half_life else 0.0

        # 회상 횟수는 로그로 눌러 담는다. 한 번 자주 쓰인 기억이 영원히
        # 1위를 차지하면 새 기억이 올라올 자리가 없다.
        familiarity = math.log1p(self.entry.recall_count)

        return self.relevance + RECENCY_WEIGHT * recency + RECALL_WEIGHT * familiarity


def digest(
    hits: list[MemoryHit],
    *,
    budget_chars: int,
    now: datetime | None = None,
    max_lines: int = MAX_DIGEST_LINES,
) -> str:
    """회상 결과를 프롬프트에 넣을 몇 줄로 압축한다.

    이 함수가 없으면 기억이 쌓일수록 프롬프트가 부풀고, 로컬 소형 모델이
    앞부분을 놓치기 시작한다. 기억은 많을수록 좋지만 주입은 적을수록 좋다.
    """
    if budget_chars <= 0 or not hits:
        return ""

    moment = now or utcnow()
    ordered = sorted(hits, key=lambda hit: hit.score(moment), reverse=True)

    lines: list[str] = []
    seen: set[str] = set()
    remaining = budget_chars

    for hit in ordered:
        if len(lines) >= max_lines:
            break
        key = hit.entry.normalized
        if not key or key in seen:
            continue
        text = hit.entry.text
        if len(text) > MAX_LINE_CHARS:
            text = text[: MAX_LINE_CHARS - 1].rstrip() + "…"
        line = f"- {text}"
        if len(line) + 1 > remaining:
            continue  # 이건 안 들어가지만 더 짧은 다음 기억은 들어갈 수 있다
        seen.add(key)
        lines.append(line)
        remaining -= len(line) + 1

    return "\n".join(lines)
