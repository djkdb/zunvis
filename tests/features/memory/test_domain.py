"""P1 완료 기준: digest 압축 규칙이 순수 단위 테스트로 검증된다."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from junvis.features.memory.domain.errors import InvalidMemory
from junvis.features.memory.domain.model import (
    MAX_LINE_CHARS,
    MemoryEntry,
    MemoryHit,
    MemoryScope,
    digest,
    normalize,
)

NOW = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)


def entry(text: str, **kwargs) -> MemoryEntry:
    kwargs.setdefault("now", NOW)
    return MemoryEntry.create(text, **kwargs)


def hit(text: str, *, relevance: float = 1.0, **kwargs) -> MemoryHit:
    return MemoryHit(entry(text, **kwargs), relevance)


# -- 엔트리 ------------------------------------------------------------------


def test_creation_normalizes_whitespace() -> None:
    assert entry("  썸네일은   3단어  이하 ").text == "썸네일은 3단어 이하"


def test_blank_memory_is_rejected() -> None:
    with pytest.raises(InvalidMemory):
        entry("   ")


def test_tags_are_deduped() -> None:
    assert entry("x", tags=("a", "a", " b ", "")).tags == ("a", "b")


def test_normalize_ignores_punctuation_and_case() -> None:
    assert normalize("썸네일은, 3단어 이하!") == normalize("썸네일은 3단어 이하")


def test_recalled_increments_without_mutating() -> None:
    original = entry("x")
    updated = original.recalled(NOW)

    assert original.recall_count == 0  # 불변
    assert updated.recall_count == 1
    assert updated.last_recalled_at == NOW


def test_pin_toggles() -> None:
    assert entry("x").pin().pinned is True
    assert entry("x").pin(True).pin(False).pinned is False


# -- 점수 --------------------------------------------------------------------


def test_pinned_always_outranks() -> None:
    pinned = hit("고정된 규칙", relevance=0.1, pinned=True)
    relevant = hit("아주 관련 있는 최신 기억", relevance=1.5)

    assert pinned.score(NOW) > relevant.score(NOW)


def test_recent_beats_old_at_equal_relevance() -> None:
    fresh = MemoryHit(entry("새 기억"), 1.0)
    old = MemoryHit(
        MemoryEntry.create("옛 기억", now=NOW - timedelta(days=365)), 1.0
    )
    assert fresh.score(NOW) > old.score(NOW)


def test_frequently_recalled_rises_but_does_not_dominate() -> None:
    """한 번 자주 쓰인 기억이 영원히 1위면 새 기억이 올라올 자리가 없다."""
    familiar = MemoryHit(entry("자주 쓰인 것").recalled(NOW), 1.0)
    for _ in range(50):
        familiar = MemoryHit(familiar.entry.recalled(NOW), 1.0)

    much_more_relevant = hit("훨씬 관련 있는 것", relevance=3.0)
    assert much_more_relevant.score(NOW) > familiar.score(NOW)


# -- digest 압축 (핵심) ------------------------------------------------------


def test_digest_renders_bullets() -> None:
    text = digest([hit("썸네일은 3단어 이하"), hit("과장하지 말 것")], budget_chars=200, now=NOW)
    assert text == "- 썸네일은 3단어 이하\n- 과장하지 말 것"


def test_digest_puts_pinned_first() -> None:
    text = digest(
        [hit("보통 기억", relevance=2.0), hit("고정된 규칙", pinned=True, relevance=0.1)],
        budget_chars=200,
        now=NOW,
    )
    assert text.splitlines()[0] == "- 고정된 규칙"


def test_digest_dedupes_same_fact_written_differently() -> None:
    text = digest(
        [hit("썸네일은 3단어 이하"), hit("썸네일은, 3단어 이하!")],
        budget_chars=500,
        now=NOW,
    )
    assert len(text.splitlines()) == 1


def test_digest_respects_the_budget() -> None:
    hits = [hit(f"규칙 번호 {n}번을 지킬 것") for n in range(50)]
    text = digest(hits, budget_chars=100, now=NOW)

    assert len(text) <= 100
    assert text  # 예산이 작아도 몇 줄은 들어간다


def test_digest_skips_a_long_entry_but_keeps_shorter_ones() -> None:
    """하나가 안 들어간다고 거기서 멈추지 않는다."""
    hits = [
        hit("가" * 300, relevance=3.0),  # 가장 관련 있지만 너무 김
        hit("짧은 규칙", relevance=1.0),
    ]
    text = digest(hits, budget_chars=60, now=NOW)
    assert "짧은 규칙" in text


def test_digest_truncates_an_overlong_line() -> None:
    text = digest([hit("나" * 500)], budget_chars=1000, now=NOW)
    assert len(text) <= MAX_LINE_CHARS + 4
    assert text.endswith("…")


def test_digest_caps_the_number_of_lines() -> None:
    hits = [hit(f"규칙 {n}") for n in range(100)]
    text = digest(hits, budget_chars=100_000, now=NOW, max_lines=5)
    assert len(text.splitlines()) == 5


def test_digest_of_nothing_is_empty() -> None:
    assert digest([], budget_chars=500, now=NOW) == ""
    assert digest([hit("x")], budget_chars=0, now=NOW) == ""


def test_scope_labels() -> None:
    assert MemoryScope.CONTENT.label == "콘텐츠"
    assert MemoryScope.PROJECT.label == "프로젝트"
