"""기억을 남기고, 고정하고, 지운다."""

from __future__ import annotations

from junvis.core.eventbus.bus import EventBus
from junvis.core.policy.engine import PolicyEngine
from junvis.core.ports import ClockPort, SystemClock, UnitOfWorkPort
from junvis.core.trace.recorder import TraceRecorder
from junvis.features.memory.application.base import TracedUseCase
from junvis.features.memory.application.dto import MemoryView
from junvis.features.memory.domain.errors import MemoryNotFound
from junvis.features.memory.domain.events import MemoryForgotten, MemoryRemembered
from junvis.features.memory.domain.model import MemoryEntry, MemoryScope
from junvis.features.memory.domain.repository import MemoryRepository


class RememberFact(TracedUseCase):
    def __init__(
        self,
        repository: MemoryRepository,
        bus: EventBus,
        unit_of_work: UnitOfWorkPort,
        *,
        policy: PolicyEngine | None = None,
        clock: ClockPort | None = None,
        tracer: TraceRecorder | None = None,
    ) -> None:
        super().__init__(tracer)
        self._repository = repository
        self._bus = bus
        self._uow = unit_of_work
        self._policy = policy
        self._clock = clock or SystemClock()

    def __call__(
        self,
        text: str,
        *,
        scope: MemoryScope = MemoryScope.USER,
        subject: str = "",
        tags: tuple[str, ...] = (),
        source: str = "user",
        pinned: bool = False,
    ) -> MemoryView:
        """같은 사실을 두 번 저장하지 않는다.

        이벤트 학습이 같은 문장을 반복해서 만들어낼 수 있고, 사용자도
        같은 말을 다시 할 수 있다. 중복이 쌓이면 digest가 그것만으로 찬다.
        """
        with self.trace("memory.remember", scope=scope.value) as handle:
            if self._policy is not None:
                self._policy.guard("memory.remember", subject or scope.value)

            entry = MemoryEntry.create(
                text,
                scope=scope,
                subject=subject,
                tags=tags,
                source=source,
                pinned=pinned,
                now=self._clock.now(),
            )
            existing = self._repository.find_similar(entry.normalized)
            if existing is not None:
                if handle is not None:
                    handle.annotate(deduplicated=True)
                # 이미 아는 사실이면 고정 여부만 강화한다.
                if pinned and not existing.pinned:
                    with self._uow():
                        self._repository.update(existing.pin())
                    return MemoryView.of(existing.pin())
                return MemoryView.of(existing)

            with self._uow():
                self._repository.add(entry)
                self._bus.publish(
                    MemoryRemembered(
                        memory_id=entry.id,
                        text=entry.text,
                        scope=entry.scope.value,
                        source=entry.source,
                    )
                )
            return MemoryView.of(entry)


class ForgetFact(TracedUseCase):
    """삭제는 사용자가 명시적으로 한다. 조용히 사라지는 기억은 신뢰를 잃는다."""

    def __init__(
        self,
        repository: MemoryRepository,
        bus: EventBus,
        unit_of_work: UnitOfWorkPort,
        *,
        policy: PolicyEngine | None = None,
        tracer: TraceRecorder | None = None,
    ) -> None:
        super().__init__(tracer)
        self._repository = repository
        self._bus = bus
        self._uow = unit_of_work
        self._policy = policy

    def __call__(self, memory_id: str) -> MemoryView:
        with self.trace("memory.forget", memory_id=memory_id):
            if self._policy is not None:
                self._policy.guard("memory.forget", memory_id)
            entry = self._repository.get(memory_id)
            if entry is None:
                raise MemoryNotFound(f"없는 기억입니다: {memory_id}")
            with self._uow():
                self._repository.remove(memory_id)
                self._bus.publish(
                    MemoryForgotten(memory_id=entry.id, text=entry.text)
                )
            return MemoryView.of(entry)


class PinFact(TracedUseCase):
    def __init__(
        self,
        repository: MemoryRepository,
        unit_of_work: UnitOfWorkPort,
        *,
        policy: PolicyEngine | None = None,
        tracer: TraceRecorder | None = None,
    ) -> None:
        super().__init__(tracer)
        self._repository = repository
        self._uow = unit_of_work
        self._policy = policy

    def __call__(self, memory_id: str, pinned: bool = True) -> MemoryView:
        with self.trace("memory.pin", memory_id=memory_id):
            if self._policy is not None:
                self._policy.guard("memory.pin", memory_id)
            entry = self._repository.get(memory_id)
            if entry is None:
                raise MemoryNotFound(f"없는 기억입니다: {memory_id}")
            updated = entry.pin(pinned)
            with self._uow():
                self._repository.update(updated)
            return MemoryView.of(updated)
