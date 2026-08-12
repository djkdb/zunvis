"""P2 완료 기준: 저장소 위에서 전 유스케이스가 동작한다."""

from __future__ import annotations

import pytest

from junvis.core.eventbus.bus import EventBus
from junvis.features.memory.application.use_cases.queries import (
    BuildDigest,
    ListMemories,
    RecallMemories,
)
from junvis.features.memory.application.use_cases.remember import (
    ForgetFact,
    PinFact,
    RememberFact,
)
from junvis.features.memory.domain.errors import MemoryNotFound
from junvis.features.memory.domain.model import MemoryScope
from junvis.features.memory.infrastructure.sqlite_repository import (
    SqliteMemoryRepository,
)
from tests.features.fakes import FixedClock


@pytest.fixture()
def repository(db) -> SqliteMemoryRepository:
    return SqliteMemoryRepository(db)


@pytest.fixture()
def bus() -> EventBus:
    return EventBus()


@pytest.fixture()
def remember(repository, bus, db) -> RememberFact:
    return RememberFact(repository, bus, db.transaction, clock=FixedClock())


# -- 기억하기 ---------------------------------------------------------------


def test_remember_stores_and_publishes(remember, bus) -> None:
    seen = []
    bus.subscribe("memory.remembered", lambda e: seen.append(e.payload))

    view = remember("Ollama를 기본 모델로 쓴다")

    assert view.text == "Ollama를 기본 모델로 쓴다"
    assert seen[0]["scope"] == "user"


def test_same_fact_is_not_stored_twice(remember, repository) -> None:
    """이벤트 학습이 같은 문장을 반복해서 만들어낼 수 있다."""
    first = remember("썸네일은 3단어 이하")
    second = remember("썸네일은, 3단어 이하!")

    assert first.id == second.id
    assert len(repository.all()) == 1


def test_re_remembering_with_pin_upgrades_it(remember, repository) -> None:
    remember("썸네일은 3단어 이하")
    view = remember("썸네일은 3단어 이하", pinned=True)

    assert view.pinned is True
    assert repository.get(view.id).pinned is True


def test_duplicate_does_not_publish_again(remember, bus) -> None:
    seen = []
    bus.subscribe("memory.remembered", lambda e: seen.append(e.payload))

    remember("같은 사실")
    remember("같은 사실")

    assert len(seen) == 1


# -- 회상 --------------------------------------------------------------------


def test_recall_counts_usage(remember, repository, db) -> None:
    remember("Supabase를 쓴다")
    recall = RecallMemories(repository, db.transaction, clock=FixedClock())

    recall("Supabase")

    assert repository.all()[0].recall_count == 1


def test_recall_can_skip_counting(remember, repository, db) -> None:
    remember("Supabase를 쓴다")
    RecallMemories(repository, db.transaction, clock=FixedClock())(
        "Supabase", count_recall=False
    )
    assert repository.all()[0].recall_count == 0


def test_recall_returns_scored_views(remember, repository, db) -> None:
    remember("고정 규칙", pinned=True)
    remember("보통 규칙")

    views = RecallMemories(repository, db.transaction, clock=FixedClock())("규칙")

    assert views[0].pinned is True  # 점수 순 정렬
    assert views[0].score > views[1].score


def test_list_shows_everything(remember, repository) -> None:
    remember("하나")
    remember("둘")
    assert len(ListMemories(repository)()) == 2


# -- digest ------------------------------------------------------------------


def test_digest_narrows_by_scope(remember, repository) -> None:
    remember("콘텐츠 규칙입니다", scope=MemoryScope.CONTENT)
    remember("사용자 선호입니다", scope=MemoryScope.USER)

    text = BuildDigest(repository, clock=FixedClock())(scope=MemoryScope.CONTENT)

    assert "콘텐츠 규칙입니다" in text
    assert "사용자 선호입니다" not in text


def test_digest_does_not_count_as_recall(remember, repository) -> None:
    """프롬프트 조립은 사용자가 그 기억을 쓴 사건이 아니다."""
    remember("규칙")
    BuildDigest(repository, clock=FixedClock())()
    assert repository.all()[0].recall_count == 0


def test_digest_of_empty_memory_is_empty(repository) -> None:
    assert BuildDigest(repository, clock=FixedClock())() == ""


# -- 고정·삭제 ---------------------------------------------------------------


def test_pin_and_unpin(remember, repository, db) -> None:
    view = remember("규칙")
    pin = PinFact(repository, db.transaction)

    assert pin(view.id).pinned is True
    assert pin(view.id, False).pinned is False


def test_forget_removes_and_publishes(remember, repository, bus, db) -> None:
    view = remember("지울 것")
    seen = []
    bus.subscribe("memory.forgotten", lambda e: seen.append(e.payload))

    ForgetFact(repository, bus, db.transaction)(view.id)

    assert repository.all() == []
    assert seen[0]["text"] == "지울 것"


def test_forget_unknown_raises(repository, bus, db) -> None:
    with pytest.raises(MemoryNotFound):
        ForgetFact(repository, bus, db.transaction)("없는아이디")


def test_pin_unknown_raises(repository, db) -> None:
    with pytest.raises(MemoryNotFound):
        PinFact(repository, db.transaction)("없는아이디")
