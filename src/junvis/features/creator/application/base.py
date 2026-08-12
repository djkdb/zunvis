"""creator 유스케이스 공통 기반."""

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
        if self._tracer is None:
            yield None
            return
        with self._tracer.record(request, **context) as handle:
            yield handle
