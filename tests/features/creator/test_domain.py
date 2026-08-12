"""C2 완료 기준: 플랫폼 규칙과 상태 기계가 단위 테스트로 검증된다."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from junvis.features.creator.domain.errors import InvalidScript, InvalidStateTransition
from junvis.features.creator.domain.model import ContentIdea, ReelScript, Scene
from junvis.features.creator.domain.value_objects import (
    CAPTION_MAX_CHARS,
    HASHTAG_MAX_COUNT,
    BrandVoice,
    ContentFormat,
    ContentStatus,
    Hashtag,
)

NOW = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)


def script(**overrides) -> ReelScript:
    defaults = dict(
        hook="Claude Code로 3시간 만에 앱 하나",
        scenes=(
            Scene(1, "터미널 화면", "먼저 프로젝트를 만듭니다", 4.0),
            Scene(2, "브라우저 화면", "바로 동작합니다", 3.0),
        ),
        caption="이번에 만든 걸 공유합니다.",
        hashtags=Hashtag.many(["AI", "바이브코딩"]),
        broll=("키보드 클로즈업",),
        thumbnail_text="3시간 만에",
        comment_bait="어떤 앱부터 만들어볼래요?",
    )
    defaults.update(overrides)
    return ReelScript(**defaults)


# -- 해시태그 정규화 ---------------------------------------------------------


def test_hashtags_are_normalized_and_deduped() -> None:
    tags = Hashtag.many(["#AI", "ai", " AI ", "#바이브코딩", "claude code"])
    assert [t.value for t in tags] == ["ai", "바이브코딩", "claudecode"]
    assert str(tags[0]) == "#ai"


def test_hashtag_count_limit_is_enforced() -> None:
    with pytest.raises(InvalidScript):
        Hashtag.many([f"tag{n}" for n in range(HASHTAG_MAX_COUNT + 1)])


def test_unusable_hashtags_are_dropped_not_fatal() -> None:
    assert Hashtag.many(["###", "  ", "ai"]) == (Hashtag("ai"),)


# -- 대본 규칙 ---------------------------------------------------------------


def test_script_requires_hook_and_scenes() -> None:
    with pytest.raises(InvalidScript):
        script(hook="   ")
    with pytest.raises(InvalidScript):
        script(scenes=())


def test_caption_length_limit_is_the_platform_rule() -> None:
    script(caption="가" * CAPTION_MAX_CHARS)  # 딱 맞으면 통과
    with pytest.raises(InvalidScript):
        script(caption="가" * (CAPTION_MAX_CHARS + 1))


def test_empty_scene_is_rejected() -> None:
    with pytest.raises(InvalidScript):
        Scene(1, "  ", "  ")
    with pytest.raises(InvalidScript):
        Scene(1, "화면", "말", duration_seconds=0)


def test_total_duration() -> None:
    assert script().total_duration == 7.0


def test_markdown_contains_every_required_part() -> None:
    markdown = script().to_markdown("테스트 주제")
    for expected in [
        "테스트 주제",
        "## Hook",
        "## 장면 구성",
        "## B-roll 아이디어",
        "## 썸네일 문구",
        "## 캡션",
        "## 해시태그",
        "## 댓글 유도",
        "#ai",
    ]:
        assert expected in markdown


# -- 상태 기계 ---------------------------------------------------------------


def test_suggest_creates_event() -> None:
    idea = ContentIdea.suggest("ZUNVIS 만든 과정", source_project_slug="zunvis", now=NOW)
    events = idea.pull_events()

    assert idea.status is ContentStatus.SUGGESTED
    assert idea.script is None
    assert [type(e).topic for e in events] == ["content.suggested"]
    assert events[0].payload()["source_project_slug"] == "zunvis"


def test_empty_subject_is_rejected() -> None:
    with pytest.raises(InvalidScript):
        ContentIdea.suggest("   ")


def test_attach_script_moves_to_drafted() -> None:
    idea = ContentIdea.suggest("주제", now=NOW)
    idea.pull_events()

    idea.attach_script(script(), now=NOW)

    assert idea.status is ContentStatus.DRAFTED
    assert [type(e).topic for e in idea.pull_events()] == ["content.drafted"]


def test_cannot_publish_without_script() -> None:
    idea = ContentIdea.suggest("주제", now=NOW)
    with pytest.raises(InvalidStateTransition):
        idea.mark_published(now=NOW)


def test_publish_records_url_and_time() -> None:
    idea = ContentIdea.suggest("주제", now=NOW)
    idea.attach_script(script(), now=NOW)
    idea.pull_events()

    idea.mark_published("https://instagram.com/p/x", now=NOW)

    assert idea.status is ContentStatus.PUBLISHED
    assert idea.published_at == NOW
    assert [type(e).topic for e in idea.pull_events()] == ["content.published"]


def test_dismissed_idea_cannot_get_a_script() -> None:
    idea = ContentIdea.suggest("주제", now=NOW)
    idea.dismiss("관심 없음", now=NOW)
    with pytest.raises(InvalidStateTransition):
        idea.attach_script(script(), now=NOW)


def test_published_content_is_immutable() -> None:
    idea = ContentIdea.suggest("주제", now=NOW)
    idea.attach_script(script(), now=NOW)
    idea.mark_published(now=NOW)

    with pytest.raises(InvalidStateTransition):
        idea.attach_script(script(), now=NOW)
    with pytest.raises(InvalidStateTransition):
        idea.dismiss(now=NOW)


def test_performance_only_after_publishing() -> None:
    idea = ContentIdea.suggest("주제", now=NOW)
    idea.attach_script(script(), now=NOW)
    with pytest.raises(InvalidStateTransition):
        idea.record_performance("좋아요 300", now=NOW)

    idea.mark_published(now=NOW)
    idea.record_performance("좋아요 300", now=NOW)
    assert idea.performance_note == "좋아요 300"


# -- 브랜드 성향 -------------------------------------------------------------


def test_default_brand_voice_carries_the_brief() -> None:
    voice = BrandVoice.default_zun()
    assert "바이브 코딩" in voice.topics
    assert "Claude Code" in voice.topics
    assert "MCP" in voice.topics

    described = voice.describe()
    assert "다루는 주제" in described
    assert "쓰지 말 것" in described  # 낚시성 문구 금지가 프롬프트에 실린다


def test_with_topics_dedupes_and_keeps_order() -> None:
    voice = BrandVoice.default_zun().with_topics(["AI", " AI ", "Swift"])
    assert voice.topics == ("AI", "Swift")


def test_content_format_labels() -> None:
    assert ContentFormat.REELS.label == "릴스"
    assert ContentFormat.CAROUSEL.label == "캐러셀"
