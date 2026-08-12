"""P3 완료 기준: 실제 SQLite로 회상 품질을 확인한다."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from junvis.features.memory.domain.model import MemoryEntry, MemoryScope, Recall
from junvis.features.memory.infrastructure.sqlite_repository import (
    SqliteMemoryRepository,
)

NOW = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)


@pytest.fixture()
def repository(db) -> SqliteMemoryRepository:
    return SqliteMemoryRepository(db)


def add(repository, text: str, **kwargs) -> MemoryEntry:
    kwargs.setdefault("now", NOW)
    entry = MemoryEntry.create(text, **kwargs)
    repository.add(entry)
    return entry


# -- 왕복 --------------------------------------------------------------------


def test_roundtrip(repository) -> None:
    original = add(
        repository,
        "썸네일 문구는 3단어 이하로",
        scope=MemoryScope.CONTENT,
        tags=("썸네일", "규칙"),
        pinned=True,
    )

    loaded = repository.get(original.id)

    assert loaded.text == original.text
    assert loaded.scope is MemoryScope.CONTENT
    assert loaded.tags == ("썸네일", "규칙")
    assert loaded.pinned is True
    assert loaded.created_at == NOW


def test_missing_returns_none(repository) -> None:
    assert repository.get("없는아이디") is None


def test_update_persists_recall_stats(repository) -> None:
    original = add(repository, "기억")
    repository.update(original.recalled(NOW))

    reloaded = repository.get(original.id)
    assert reloaded.recall_count == 1
    assert reloaded.last_recalled_at == NOW


def test_remove(repository) -> None:
    entry = add(repository, "지울 것")
    assert repository.remove(entry.id) is True
    assert repository.get(entry.id) is None
    assert repository.remove(entry.id) is False


def test_all_puts_pinned_first(repository) -> None:
    add(repository, "보통 기억")
    add(repository, "고정된 기억", pinned=True)

    assert repository.all()[0].text == "고정된 기억"


# -- 중복 방지 ---------------------------------------------------------------


def test_find_similar_matches_normalized_text(repository) -> None:
    add(repository, "썸네일은 3단어 이하")

    found = repository.find_similar(
        MemoryEntry.create("썸네일은, 3단어 이하!", now=NOW).normalized
    )
    assert found is not None


def test_find_similar_returns_none_for_new_facts(repository) -> None:
    add(repository, "썸네일은 3단어 이하")
    assert repository.find_similar("완전히 다른 사실") is None


# -- 검색 --------------------------------------------------------------------


def test_search_finds_by_keyword(repository) -> None:
    add(repository, "썸네일 문구는 3단어 이하로")
    add(repository, "Ollama를 기본 모델로 쓴다")

    hits = repository.search(Recall(query="썸네일"))
    assert [h.entry.text for h in hits] == ["썸네일 문구는 3단어 이하로"]


def test_search_matches_tags(repository) -> None:
    add(repository, "어떤 규칙", tags=("훅",))
    assert repository.search(Recall(query="훅"))


def test_search_is_prefix_matching(repository) -> None:
    add(repository, "Supabase를 쓴다")
    assert repository.search(Recall(query="Supa"))


def test_search_survives_fts_syntax_in_user_input(repository) -> None:
    add(repository, "어떤 기억")
    for hostile in ['"', "AND OR", "*", "(((", '"unclosed']:
        repository.search(Recall(query=hostile))  # 예외가 나지 않으면 통과


def test_empty_query_browses_the_scope(repository) -> None:
    """콘텐츠 생성처럼 "이 스코프의 규칙을 전부 달라"는 요청이 흔하다."""
    add(repository, "콘텐츠 규칙", scope=MemoryScope.CONTENT)
    add(repository, "사용자 선호", scope=MemoryScope.USER)

    hits = repository.search(Recall(scope=MemoryScope.CONTENT))
    assert [h.entry.text for h in hits] == ["콘텐츠 규칙"]


def test_scope_filter_applies_to_keyword_search_too(repository) -> None:
    add(repository, "규칙 하나", scope=MemoryScope.CONTENT)
    add(repository, "규칙 둘", scope=MemoryScope.USER)

    hits = repository.search(Recall(query="규칙", scope=MemoryScope.USER))
    assert [h.entry.text for h in hits] == ["규칙 둘"]


def test_subject_narrows_project_memories(repository) -> None:
    add(repository, "Supabase를 쓴다", scope=MemoryScope.PROJECT, subject="zunvis")
    add(repository, "Firebase를 쓴다", scope=MemoryScope.PROJECT, subject="other")

    hits = repository.search(Recall(scope=MemoryScope.PROJECT, subject="zunvis"))
    assert [h.entry.text for h in hits] == ["Supabase를 쓴다"]


def test_relevance_is_normalized_within_the_result_set(repository) -> None:
    """bm25 절대값은 질의마다 달라 그대로 쓰면 최근성 보정과 섞이지 않는다."""
    add(repository, "썸네일 썸네일 썸네일 규칙")
    add(repository, "썸네일 하나만 언급하는 긴 문장 하나 둘 셋 넷 다섯")

    hits = repository.search(Recall(query="썸네일"))
    relevances = [h.relevance for h in hits]

    assert len(hits) == 2
    assert max(relevances) <= 1.5
    assert min(relevances) >= 0.5
    assert relevances[0] >= relevances[1]  # 순위 순서와 일치


def test_single_result_gets_full_relevance(repository) -> None:
    add(repository, "유일한 기억")
    assert repository.search(Recall(query="유일한"))[0].relevance == 1.5


def test_limit_is_respected(repository) -> None:
    for index in range(10):
        add(repository, f"기억 {index}")
    assert len(repository.search(Recall(limit=3))) == 3
