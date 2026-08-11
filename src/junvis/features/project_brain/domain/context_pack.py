"""Context Pack — 에이전트에게 주입할 압축된 컨텍스트 묶음.

무엇을 먼저 넣을지는 **도메인 규칙**이지 프롬프트 문자열 편집이 아니다.
그래서 이 결정이 인프라나 인터페이스가 아니라 도메인에 산다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from junvis.features.project_brain.domain.value_objects import TokenBudget

ELLIPSIS = "\n…(예산 초과로 생략)"

#: 잘라 넣을 바에야 통째로 빼는 게 나은 최소 길이.
MIN_BODY_CHARS = 120

#: 제목 마크업과 줄바꿈이 차지하는 대략적 비용.
SECTION_OVERHEAD = 6


@dataclass(frozen=True)
class ContextSection:
    title: str
    body: str

    @property
    def cost(self) -> int:
        return len(self.title) + len(self.body) + SECTION_OVERHEAD


@dataclass(frozen=True)
class ContextPack:
    slug: str
    name: str
    generated_at: datetime
    sections: tuple[ContextSection, ...]
    budget: TokenBudget
    truncated: bool

    @property
    def estimated_tokens(self) -> int:
        total = sum(section.cost for section in self.sections)
        return total // TokenBudget.CHARS_PER_TOKEN

    def to_markdown(self) -> str:
        lines = [f"# {self.name} ({self.slug})"]
        for section in self.sections:
            lines.append(f"\n## {section.title}\n{section.body}")
        if self.truncated:
            lines.append(f"\n> 컨텍스트가 {self.budget.tokens} 토큰 예산에서 잘렸습니다.")
        return "\n".join(lines)


def build_pack(
    *,
    slug: str,
    name: str,
    generated_at: datetime,
    candidates: list[tuple[str, str]],
    budget: TokenBudget,
) -> ContextPack:
    """우선순위 순서대로 예산이 허용하는 만큼 채운다.

    예산이 바닥나면 그 지점에서 **멈춘다**. 뒤쪽의 작은 섹션을 끼워 넣어
    앞선 섹션을 밀어내지 않는다 — 우선순위가 곧 계약이기 때문이다.
    """
    remaining = budget.chars
    sections: list[ContextSection] = []
    truncated = False

    for title, body in candidates:
        text = body.strip()
        if not text:
            continue
        section = ContextSection(title, text)
        if section.cost <= remaining:
            sections.append(section)
            remaining -= section.cost
            continue

        room = remaining - len(title) - SECTION_OVERHEAD - len(ELLIPSIS)
        if room >= MIN_BODY_CHARS:
            sections.append(ContextSection(title, text[:room] + ELLIPSIS))
        truncated = True
        break

    return ContextPack(
        slug=slug,
        name=name,
        generated_at=generated_at,
        sections=tuple(sections),
        budget=budget,
        truncated=truncated,
    )
