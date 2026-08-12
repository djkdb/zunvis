"""도구 명세 — MCP SDK로부터 독립된 표현.

`ToolSpec`은 특정 feature의 소유물이 아니라 **인터페이스 계층의 공통 어휘**다.
어느 한 feature에 두면 다른 feature가 그것을 쓰려고 그 feature 전체를
임포트하게 되고, Bounded Context 경계가 무너진다. (import-linter 계약 6번이
실제로 이 실수를 잡아냈다.)

SDK 타입을 여기 들이지 않는 것이 핵심이다. feature는 명세만 만들고,
SDK에 묶는 일은 조립 루트(apps/mcp_server)가 한다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """모델이 읽을 텍스트와, 기계가 읽을 구조화 데이터."""

    text: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[Mapping[str, Any]], ToolResult]
    #: 읽기 전용 도구는 호스트가 확인 없이 부를 수 있다.
    read_only: bool = True
