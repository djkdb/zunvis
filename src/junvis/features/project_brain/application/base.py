"""유스케이스 공통 기반.

M5 완료 기준("모든 유스케이스 실행이 Trace 1건 생성")을 진입점마다
반복 구현하지 않고 여기서 한 번에 만족시킨다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from junvis.core.trace.recorder import TraceHandle, TraceRecorder


class TracedUseCase:
    def __init__(self, tracer: TraceRecorder | None = None) -> None:
        self._tracer = tracer

    @contextmanager
    def trace(self, request: str, **context: Any) -> Iterator[TraceHandle | None]:
        """Trace 기록기가 없으면(단위 테스트) 조용히 통과한다."""
        if self._tracer is None:
            yield None
            return
        with self._tracer.record(request, **context) as handle:
            yield handle
