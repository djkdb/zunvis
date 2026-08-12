"""도구 선별 — 컨텍스트 오염 대책.

1단계 분석에서 MCP의 가장 큰 단점으로 꼽은 것이 "도구가 많아지면 모든 도구
정의를 프롬프트에 넣을 수 없다"였다. `isair/jarvis`의 해법(임베딩 기반 관련도
필터)을 차용하되, 기본 구현은 **토큰 겹침**으로 한다.

임베딩을 쓰려면 임베딩 모델이 떠 있어야 하는데, 도구 하나 고르자고 요구하기엔
무겁다. 포트 뒤에 두었으므로 품질이 아쉬우면 교체한다.
"""

from __future__ import annotations

import re
from typing import Protocol

from junvis.core.mcp.catalog import ExternalTool

_WORD = re.compile(r"[a-z0-9가-힣]+")

#: 한 요청에 주입할 기본 도구 수. 설계 §5.3의 N=12를 따른다.
DEFAULT_LIMIT = 12


def tokenize(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


class ToolRankerPort(Protocol):
    def rank(
        self, query: str, tools: list[ExternalTool], *, limit: int = DEFAULT_LIMIT
    ) -> list[ExternalTool]: ...


class TokenOverlapRanker:
    """질의 토큰과 도구 이름·설명의 겹침으로 순위를 매긴다.

    이름에서 겹치는 것이 설명에서 겹치는 것보다 강한 신호다.
    """

    NAME_WEIGHT = 3.0
    DESCRIPTION_WEIGHT = 1.0

    def rank(
        self, query: str, tools: list[ExternalTool], *, limit: int = DEFAULT_LIMIT
    ) -> list[ExternalTool]:
        if not query.strip():
            # 질의가 없으면 순서를 바꿀 근거가 없다. 안정적인 순서로 자른다.
            return sorted(tools, key=lambda t: t.qualified_name)[:limit]

        wanted = tokenize(query)
        scored = []
        for index, tool in enumerate(tools):
            name_hits = len(wanted & tokenize(tool.name))
            desc_hits = len(wanted & tokenize(tool.description))
            score = name_hits * self.NAME_WEIGHT + desc_hits * self.DESCRIPTION_WEIGHT
            if score > 0:
                # index를 함께 실어 같은 점수의 순서를 결정적으로 만든다.
                scored.append((-score, index, tool))
        return [tool for _, _, tool in sorted(scored)][:limit]
