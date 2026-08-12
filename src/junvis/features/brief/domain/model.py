"""Daily Brief의 도메인.

여기 있는 것은 데이터가 아니라 **조립 규칙**이다. Briefing은 애그리게이트가
아니라 매번 새로 계산되는 읽기 모델이므로 저장하지 않는다
(docs/04-DAILY-BRIEF.md §0-1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import IntEnum


class Urgency(IntEnum):
    INFO = 0
    NOTICE = 1
    ATTENTION = 2
    URGENT = 3

    @property
    def marker(self) -> str:
        return {
            Urgency.INFO: "",
            Urgency.NOTICE: "·",
            Urgency.ATTENTION: "!",
            Urgency.URGENT: "!!",
        }[self]


@dataclass(frozen=True)
class BriefItem:
    text: str
    detail: str = ""
    urgency: Urgency = Urgency.INFO
    action: str = ""  # 바로 칠 수 있는 명령

    def render(self) -> str:
        marker = f"{self.urgency.marker} " if self.urgency.marker else ""
        line = f"- {marker}{self.text}"
        if self.detail:
            line += f"\n    {self.detail}"
        if self.action:
            line += f"\n    → {self.action}"
        return line


@dataclass(frozen=True)
class BriefSection:
    title: str
    items: tuple[BriefItem, ...]
    #: 낮을수록 먼저. docs/04-DAILY-BRIEF.md §1의 표가 이 값의 근거다.
    rank: int

    @property
    def peak_urgency(self) -> Urgency:
        return max((item.urgency for item in self.items), default=Urgency.INFO)

    #: 승격 폭. 1.0이 아니라 1.5인 이유: 정확히 1이면 바로 위 섹션과 값이
    #: 같아져 원래 순위로 동점이 갈리고, 결국 아무것도 올라오지 않는다.
    PROMOTION = 1.5

    @property
    def effective_rank(self) -> float:
        """URGENT 항목이 있으면 바로 위 섹션보다 앞으로 올라온다.

        장기 목표(ZUN 브랜드 성장 등)가 오늘의 잡무를 이기는 유일한 통로다.
        """
        if self.peak_urgency is Urgency.URGENT:
            return self.rank - self.PROMOTION
        return float(self.rank)

    def render(self) -> str:
        body = "\n".join(item.render() for item in self.items)
        return f"## {self.title}\n{body}"


@dataclass(frozen=True)
class Briefing:
    day: date
    sections: tuple[BriefSection, ...] = field(default=())
    generated_at: datetime | None = None

    @property
    def is_empty(self) -> bool:
        return not self.sections

    @property
    def peak_urgency(self) -> Urgency:
        return max(
            (section.peak_urgency for section in self.sections), default=Urgency.INFO
        )

    def headline(self) -> str:
        """알림 한 줄. 가장 위 섹션의 첫 항목이 오늘의 요점이다."""
        if self.is_empty:
            return "오늘 챙길 것이 없습니다."
        top = self.sections[0]
        return f"{top.title}: {top.items[0].text}"

    def to_markdown(self) -> str:
        header = f"# {self.day.isoformat()} 브리핑"
        if self.is_empty:
            return f"{header}\n\n오늘 챙길 것이 없습니다."
        return "\n\n".join([header, *(s.render() for s in self.sections)])


def order_sections(sections: list[BriefSection]) -> tuple[BriefSection, ...]:
    """빈 섹션을 버리고 우선순위대로 세운다.

    정렬 키가 `rank`가 아니라 `effective_rank`인 것이 핵심이다 —
    무엇이 급한지가 순서를 바꾼다.
    """
    filled = [section for section in sections if section.items]
    return tuple(sorted(filled, key=lambda s: (s.effective_rank, s.rank)))
