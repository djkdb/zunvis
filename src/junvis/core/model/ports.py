"""ModelPort — JUNVIS가 LLM을 만나는 유일한 지점.

도메인과 유스케이스는 Ollama도 Claude도 모른다. 여기 선언된 형태만 안다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from junvis.core.domain.errors import JunvisError


class ModelError(JunvisError):
    """모델 호출 실패. 로컬 서버가 꺼져 있는 것도 여기로 온다."""


class ModelRole(str, Enum):
    """무엇에 쓰는 모델인가.

    구체 모델 이름을 유스케이스에 박아 넣지 않기 위한 간접층이다.
    "분류에는 작은 모델, 창작에는 큰 모델"이라는 정책이 한 곳에 모인다.
    """

    FAST = "fast"
    DEEP = "deep"


@dataclass(frozen=True)
class ModelRequest:
    prompt: str
    system: str = ""
    role: ModelRole = ModelRole.FAST
    temperature: float = 0.7
    #: JSON Schema를 주면 구조화 출력을 요구한다.
    #: 프롬프트로 "JSON만 주세요"라고 비는 대신 런타임이 강제하게 한다.
    schema: dict[str, Any] | None = None
    max_tokens: int | None = None


@dataclass(frozen=True)
class ModelResponse:
    text: str
    model: str
    tokens: int = 0
    latency_ms: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


class ModelPort(Protocol):
    def complete(self, request: ModelRequest) -> ModelResponse: ...
