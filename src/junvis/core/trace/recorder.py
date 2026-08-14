"""TraceRecorder — 유스케이스를 감싸 Trace 1건을 남긴다."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from junvis.core.eventbus.bus import EventBus
from junvis.core.redact import redact
from junvis.core.trace.model import Outcome, ToolCall, Trace, TraceCompleted, TraceStore


class TraceHandle:
    """진행 중인 실행에 사실을 덧붙이는 손잡이."""

    def __init__(self, trace: Trace) -> None:
        self._trace = trace

    @property
    def id(self) -> str:
        return self._trace.id

    def set_plan(self, plan: str) -> None:
        self._trace.plan = plan

    def set_model(self, model: str) -> None:
        self._trace.model = model

    def add_tokens(self, tokens: int, cost: float = 0.0) -> None:
        self._trace.tokens += tokens
        self._trace.cost += cost

    def annotate(self, **context: Any) -> None:
        self._trace.context.update(_clean(context))

    @contextmanager
    def tool(self, name: str, **arguments: Any) -> Iterator[ToolCall]:
        """도구 호출 1건을 계측한다. 실패해도 기록은 남는다."""
        call = ToolCall(name=name, arguments=arguments)
        started = time.perf_counter()
        try:
            yield call
        except Exception as exc:
            call.ok = False
            call.error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            call.latency_ms = int((time.perf_counter() - started) * 1000)
            self._trace.tool_calls.append(call)


class TraceRecorder:
    def __init__(self, store: TraceStore, bus: EventBus | None = None) -> None:
        self._store = store
        self._bus = bus

    @contextmanager
    def record(
        self, request: str, *, model: str | None = None, **context: Any
    ) -> Iterator[TraceHandle]:
        # 비밀은 남기기 **전에** 지운다. 한 번 들어가면 백업에도 실린다.
        trace = Trace(request=request, model=model, context=_clean(context))
        handle = TraceHandle(trace)
        started = time.perf_counter()
        try:
            yield handle
        except Exception as exc:
            trace.outcome = Outcome.ERROR
            trace.context["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            trace.latency_ms = int((time.perf_counter() - started) * 1000)
            # 기록 실패가 본 작업을 무너뜨리면 안 된다.
            try:
                self._store.save(trace)
                if self._bus is not None:
                    self._bus.publish(
                        TraceCompleted(
                            trace_id=trace.id,
                            request=trace.request,
                            outcome=trace.outcome.value,
                            model=trace.model,
                            latency_ms=trace.latency_ms,
                            tool_names=tuple(c.name for c in trace.tool_calls),
                        )
                    )
            except Exception:  # pragma: no cover - 방어적
                pass


def _clean(context: dict[str, Any]) -> dict[str, Any]:
    """Trace의 문자열 값에서 비밀을 지운다(docs/10 §6).

    Trace는 **모든 유스케이스의 입력**을 남긴다. 프로젝트 경로, 릴스 주제,
    음성 명령이 전부 지나간다. 그중 하나에 토큰이 섞이면 그대로 저장된다.
    """
    return {
        key: redact(value) if isinstance(value, str) else value
        for key, value in context.items()
    }
