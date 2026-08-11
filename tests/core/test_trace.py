"""M5 완료 기준: 모든 유스케이스 실행이 Trace 1건을 남긴다."""

from __future__ import annotations

from contextlib import nullcontext

import pytest

from junvis.core.eventbus.bus import EventBus
from junvis.core.trace.model import Outcome
from junvis.core.trace.recorder import TraceRecorder
from junvis.core.trace.store import SqliteTraceStore
from junvis.features.project_brain.application.dto import RegisterProjectCommand
from junvis.features.project_brain.application.use_cases.register_project import (
    RegisterProject,
)
from tests.features.fakes import FakeGit, FixedClock, InMemoryProjectRepository


@pytest.fixture()
def store(db) -> SqliteTraceStore:
    return SqliteTraceStore(db)


def test_successful_run_is_recorded(store) -> None:
    recorder = TraceRecorder(store)
    with recorder.record("테스트 요청", model="qwen3:4b") as handle:
        handle.set_plan("계획")
        handle.add_tokens(120, cost=0.0)
        with handle.tool("git.read", path="/x"):
            pass

    trace = store.recent()[0]
    assert trace.request == "테스트 요청"
    assert trace.outcome is Outcome.OK
    assert trace.model == "qwen3:4b"
    assert trace.tokens == 120
    assert [c.name for c in trace.tool_calls] == ["git.read"]
    assert trace.tool_calls[0].ok is True


def test_failure_is_recorded_and_reraised(store) -> None:
    recorder = TraceRecorder(store)
    with pytest.raises(RuntimeError):
        with recorder.record("실패하는 요청"):
            raise RuntimeError("터짐")

    trace = store.recent()[0]
    assert trace.outcome is Outcome.ERROR
    assert "터짐" in trace.context["error"]


def test_failing_tool_call_is_recorded(store) -> None:
    recorder = TraceRecorder(store)
    with pytest.raises(ValueError):
        with recorder.record("요청") as handle:
            with handle.tool("github.issues"):
                raise ValueError("네트워크 없음")

    call = store.recent()[0].tool_calls[0]
    assert call.ok is False
    assert "네트워크 없음" in call.error


def test_trace_completed_event_is_published(store) -> None:
    bus = EventBus()
    seen = []
    bus.subscribe("trace.completed", lambda env: seen.append(env.payload))

    with TraceRecorder(store, bus).record("요청"):
        pass

    assert seen[0]["outcome"] == "ok"
    assert seen[0]["request"] == "요청"


def test_store_failure_does_not_break_the_work(db) -> None:
    """기록이 실패해도 본 작업은 성공해야 한다."""

    class BrokenStore:
        def save(self, trace):
            raise RuntimeError("디스크 꽉참")

        def recent(self, limit=20):
            return []

    result = []
    with TraceRecorder(BrokenStore()).record("요청"):
        result.append("작업 완료")

    assert result == ["작업 완료"]


def test_use_case_execution_produces_a_trace(store) -> None:
    """M5의 실제 판정: 유스케이스를 한 번 부르면 Trace가 한 건 생긴다."""
    use_case = RegisterProject(
        InMemoryProjectRepository(),
        EventBus(),
        nullcontext,
        git=FakeGit(),
        clock=FixedClock(),
        tracer=TraceRecorder(store),
    )

    use_case(RegisterProjectCommand(slug="zunvis", name="ZUNVIS"))

    traces = store.recent()
    assert len(traces) == 1
    assert traces[0].request == "project.register"
    assert traces[0].context["slug"] == "zunvis"
    assert traces[0].outcome is Outcome.OK
