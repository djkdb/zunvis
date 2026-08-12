"""회상과 주입.

`RecallMemories`는 사람이 보는 것, `BuildDigest`는 모델에게 주는 것이다.
둘을 나눈 이유가 이 Context의 핵심이다(docs/06-MEMORY.md §1).
"""

from __future__ import annotations

from junvis.core.policy.engine import PolicyEngine
from junvis.core.ports import ClockPort, SystemClock, UnitOfWorkPort
from junvis.core.trace.recorder import TraceRecorder
from junvis.core.usecase import TracedUseCase
from junvis.features.memory.application.dto import MemoryView
from junvis.features.memory.domain.model import MemoryScope, Recall, digest
from junvis.features.memory.domain.repository import MemoryRepository

#: 프롬프트에 실을 기본 예산(문자). 토큰으로 치면 대략 150.
DEFAULT_DIGEST_CHARS = 600


class RecallMemories(TracedUseCase):
    def __init__(
        self,
        repository: MemoryRepository,
        unit_of_work: UnitOfWorkPort,
        *,
        policy: PolicyEngine | None = None,
        clock: ClockPort | None = None,
        tracer: TraceRecorder | None = None,
    ) -> None:
        super().__init__(tracer)
        self._repository = repository
        self._uow = unit_of_work
        self._policy = policy
        self._clock = clock or SystemClock()

    def __call__(
        self,
        query: str = "",
        *,
        scope: MemoryScope | None = None,
        subject: str = "",
        limit: int = 20,
        count_recall: bool = True,
    ) -> list[MemoryView]:
        with self.trace("memory.recall", query=query) as handle:
            if self._policy is not None:
                self._policy.guard("memory.recall", query)

            hits = self._repository.search(
                Recall(query=query, scope=scope, subject=subject, limit=limit)
            )
            now = self._clock.now()
            ordered = sorted(hits, key=lambda hit: hit.score(now), reverse=True)

            if count_recall and ordered:
                # 자주 쓰이는 기억이 위로 올라오도록 회상 통계를 남긴다.
                with self._uow():
                    for hit in ordered:
                        self._repository.update(hit.entry.recalled(now))

            if handle is not None:
                handle.annotate(hits=len(ordered))
            return [MemoryView.of(hit.entry, hit.score(now)) for hit in ordered]


class BuildDigest(TracedUseCase):
    """모델에게 줄 몇 줄로 압축한다.

    회상 통계를 남기지 않는다(`count_recall=False`). 프롬프트 조립은
    사용자가 그 기억을 쓴 사건이 아니다 — 세면 통계가 부풀기만 한다.
    """

    def __init__(
        self,
        repository: MemoryRepository,
        *,
        clock: ClockPort | None = None,
        tracer: TraceRecorder | None = None,
    ) -> None:
        super().__init__(tracer)
        self._repository = repository
        self._clock = clock or SystemClock()

    def __call__(
        self,
        query: str = "",
        *,
        scope: MemoryScope | None = None,
        subject: str = "",
        budget_chars: int = DEFAULT_DIGEST_CHARS,
        limit: int = 30,
    ) -> str:
        hits = self._repository.search(
            Recall(query=query, scope=scope, subject=subject, limit=limit)
        )
        return digest(hits, budget_chars=budget_chars, now=self._clock.now())


class ListMemories(TracedUseCase):
    def __init__(
        self,
        repository: MemoryRepository,
        *,
        policy: PolicyEngine | None = None,
        tracer: TraceRecorder | None = None,
    ) -> None:
        super().__init__(tracer)
        self._repository = repository
        self._policy = policy

    def __call__(self, *, limit: int = 100) -> list[MemoryView]:
        with self.trace("memory.recall", kind="list"):
            if self._policy is not None:
                self._policy.guard("memory.recall")
            return [MemoryView.of(entry) for entry in self._repository.all(limit=limit)]
