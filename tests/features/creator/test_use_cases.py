"""C3 완료 기준: Fake 생성기만으로 전 유스케이스를 검증한다."""

from __future__ import annotations

from contextlib import nullcontext

import pytest

from junvis.core.eventbus.bus import EventBus
from junvis.features.creator.application.use_cases.generate_content import GenerateContent
from junvis.features.creator.application.use_cases.lifecycle import (
    DismissContent,
    MarkPublished,
    UpdateBrandVoice,
)
from junvis.features.creator.application.use_cases.queries import (
    GetBrandVoice,
    GetContent,
    ListContent,
)
from junvis.features.creator.application.use_cases.suggest import SuggestForProject
from junvis.features.creator.domain.errors import ContentNotFound, InvalidStateTransition
from junvis.features.creator.domain.value_objects import ContentFormat
from tests.features.creator.fakes import (
    FakeGenerator,
    FakeProjectContext,
    InMemoryBrandVoiceStore,
    InMemoryContentRepository,
)
from tests.features.fakes import FixedClock


@pytest.fixture()
def repo() -> InMemoryContentRepository:
    return InMemoryContentRepository()


@pytest.fixture()
def bus() -> EventBus:
    return EventBus()


@pytest.fixture()
def generator() -> FakeGenerator:
    return FakeGenerator()


@pytest.fixture()
def brand() -> InMemoryBrandVoiceStore:
    return InMemoryBrandVoiceStore()


@pytest.fixture()
def context() -> FakeProjectContext:
    return FakeProjectContext()


@pytest.fixture()
def generate(repo, brand, generator, bus, context) -> GenerateContent:
    return GenerateContent(
        repo, brand, generator, bus, nullcontext,
        project_context=context, clock=FixedClock(),
    )


# -- 생성 --------------------------------------------------------------------


def test_generate_from_subject_produces_full_package(generate) -> None:
    detail = generate(subject="Claude Code로 앱 만들기")

    summary = detail.summary
    assert summary.status == "drafted"
    assert summary.hook
    assert summary.scene_count == 2
    assert summary.duration_seconds == 7.0
    assert summary.hashtags == ("#ai", "#바이브코딩")
    # 브리프가 요구한 9개 구성요소가 마크다운에 전부 있다
    for part in ["Hook", "장면 구성", "B-roll", "썸네일 문구", "캡션", "해시태그", "댓글 유도"]:
        assert part in detail.markdown


def test_generate_publishes_both_events(generate, bus) -> None:
    seen = []
    bus.subscribe("content.*", lambda env: seen.append(env.topic), name="spy")

    generate(subject="주제")

    # 새로 만들면 제안과 초안이 함께 기록된다
    assert seen == ["content.suggested", "content.drafted"]


def test_generate_uses_brand_voice(generate, generator) -> None:
    generate(subject="주제")
    voice = generator.requests[0].brand_voice
    assert "바이브 코딩" in voice.topics


def test_generate_pulls_project_context_when_asked(generate, generator, context) -> None:
    generate(subject="주제", project_slug="zunvis")
    assert context.asked == ["zunvis"]
    assert "개인 AI OS" in generator.requests[0].project_context


def test_generate_works_without_project(generate, generator, context) -> None:
    """주제만 가지고 만드는 릴스도 1급 시민이다."""
    generate(subject="주제")
    assert context.asked == []
    assert generator.requests[0].project_context is None


def test_unknown_project_does_not_break_generation(repo, brand, generator, bus) -> None:
    use_case = GenerateContent(
        repo, brand, generator, bus, nullcontext,
        project_context=FakeProjectContext(context=None), clock=FixedClock(),
    )
    assert use_case(subject="주제", project_slug="없는프로젝트").summary.status == "drafted"


def test_generate_into_existing_suggestion(generate, repo) -> None:
    suggestion = SuggestForProject(repo, EventBus(), nullcontext, clock=FixedClock())(
        "zunvis", "ZUNVIS"
    )

    detail = generate(idea_id=suggestion.id)

    assert detail.summary.id == suggestion.id
    assert detail.summary.status == "drafted"
    assert len(repo.items) == 1  # 새로 만들지 않고 그 제안을 채운다


def test_generate_requires_subject_or_id(generate) -> None:
    with pytest.raises(ValueError):
        generate()


def test_generate_with_unknown_id_raises(generate) -> None:
    with pytest.raises(ContentNotFound):
        generate(idea_id="없는아이디")


def test_carousel_format_is_passed_through(generate, generator) -> None:
    generate(subject="주제", content_format=ContentFormat.CAROUSEL)
    assert generator.requests[0].content_format is ContentFormat.CAROUSEL


def test_generation_failure_saves_nothing(repo, brand, bus, context) -> None:
    failing = FakeGenerator(fail=RuntimeError("모델 죽음"))
    use_case = GenerateContent(
        repo, brand, failing, bus, nullcontext,
        project_context=context, clock=FixedClock(),
    )
    with pytest.raises(RuntimeError):
        use_case(subject="주제")
    assert repo.items == {}


# -- 제안 (Content Assistant) -------------------------------------------------


def test_suggest_creates_one_idea_per_project(repo, bus) -> None:
    suggest = SuggestForProject(repo, bus, nullcontext, clock=FixedClock())

    first = suggest("zunvis", "ZUNVIS")
    second = suggest("zunvis", "ZUNVIS")

    assert first is not None
    assert second is None  # 다시 등록해도 제안이 쌓이지 않는다
    assert len(repo.items) == 1
    assert first.subject == "ZUNVIS 만든 과정"


# -- 생애주기 ----------------------------------------------------------------


def test_dismiss(generate, repo, bus) -> None:
    detail = generate(subject="주제")
    seen = []
    bus.subscribe("content.dismissed", lambda e: seen.append(e.payload), name="d")

    summary = DismissContent(repo, bus, nullcontext, clock=FixedClock())(
        detail.summary.id, "방향이 안 맞음"
    )

    assert summary.status == "dismissed"
    assert seen[0]["reason"] == "방향이 안 맞음"


def test_mark_published(generate, repo, bus) -> None:
    detail = generate(subject="주제")
    summary = MarkPublished(repo, bus, nullcontext, clock=FixedClock())(
        detail.summary.id, "https://instagram.com/p/x"
    )
    assert summary.status == "published"
    assert summary.published_url == "https://instagram.com/p/x"


def test_cannot_publish_a_bare_suggestion(repo, bus) -> None:
    suggestion = SuggestForProject(repo, bus, nullcontext, clock=FixedClock())(
        "zunvis", "ZUNVIS"
    )
    with pytest.raises(InvalidStateTransition):
        MarkPublished(repo, bus, nullcontext, clock=FixedClock())(suggestion.id)


# -- 조회 --------------------------------------------------------------------


def test_list_filters_by_status(generate, repo, bus) -> None:
    generate(subject="초안이 될 것")
    SuggestForProject(repo, bus, nullcontext, clock=FixedClock())("zunvis", "ZUNVIS")

    listing = ListContent(repo)
    assert len(listing()) == 2
    assert len(listing(status="drafted")) == 1
    assert len(listing(status="suggested")) == 1


def test_get_returns_markdown(generate, repo) -> None:
    detail = generate(subject="주제")
    assert "## Hook" in GetContent(repo)(detail.summary.id).markdown


def test_get_suggestion_says_it_has_no_script(repo, bus) -> None:
    suggestion = SuggestForProject(repo, bus, nullcontext, clock=FixedClock())(
        "zunvis", "ZUNVIS"
    )
    assert "아직 대본이 없습니다" in GetContent(repo)(suggestion.id).markdown


# -- 브랜드 성향 -------------------------------------------------------------


def test_update_brand_voice_only_touches_given_fields(brand) -> None:
    original = GetBrandVoice(brand)()
    updated = UpdateBrandVoice(brand)(tone="더 담백하게")

    assert updated.tone == "더 담백하게"
    assert updated.topics == original.topics  # 주지 않은 것은 그대로
    assert updated.banned_phrases == original.banned_phrases


def test_updated_brand_voice_reaches_the_generator(brand, repo, generator, bus) -> None:
    UpdateBrandVoice(brand)(topics=["Swift", "macOS"])
    use_case = GenerateContent(
        repo, brand, generator, bus, nullcontext, clock=FixedClock()
    )

    use_case(subject="주제")

    assert generator.requests[0].brand_voice.topics == ("Swift", "macOS")
