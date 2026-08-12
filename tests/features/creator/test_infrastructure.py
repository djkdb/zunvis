"""C4 완료 기준: SQLite 왕복 + 프롬프트 조립 + JSON 파싱."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from junvis.core.model.echo import EchoAdapter
from junvis.core.model.ports import ModelError, ModelRole
from junvis.features.creator.application.ports import GenerationRequest
from junvis.features.creator.domain.errors import InvalidScript
from junvis.features.creator.domain.model import ContentIdea
from junvis.features.creator.domain.value_objects import (
    BrandVoice,
    ContentFormat,
    ContentStatus,
    IdeaId,
)
from junvis.features.creator.infrastructure.script_generator import (
    SCRIPT_SCHEMA,
    LlmScriptGenerator,
)
from junvis.features.creator.infrastructure.sqlite_repository import (
    SqliteBrandVoiceStore,
    SqliteContentRepository,
)
from tests.features.creator.fakes import sample_script

NOW = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)


@pytest.fixture()
def repository(db) -> SqliteContentRepository:
    return SqliteContentRepository(db)


def drafted(subject: str = "주제", slug: str | None = "zunvis") -> ContentIdea:
    idea = ContentIdea.suggest(subject, source_project_slug=slug, now=NOW)
    idea.attach_script(sample_script(), now=NOW)
    idea.pull_events()
    return idea


# -- 저장소 왕복 -------------------------------------------------------------


def test_roundtrip_preserves_the_whole_script(repository) -> None:
    original = drafted()
    repository.save(original)

    loaded = repository.get(original.id)

    assert loaded is not None
    assert loaded.subject == original.subject
    assert loaded.status is ContentStatus.DRAFTED
    assert loaded.source_project_slug == "zunvis"
    assert loaded.script.hook == original.script.hook
    assert loaded.script.total_duration == original.script.total_duration
    assert [s.narration for s in loaded.script.scenes] == [
        s.narration for s in original.script.scenes
    ]
    assert [t.value for t in loaded.script.hashtags] == ["ai", "바이브코딩"]
    assert loaded.script.broll == original.script.broll
    assert loaded.script.comment_bait == original.script.comment_bait


def test_suggestion_without_script_roundtrips(repository) -> None:
    idea = ContentIdea.suggest("아직 대본 없음", now=NOW)
    repository.save(idea)
    assert repository.get(idea.id).script is None


def test_save_is_an_upsert(repository) -> None:
    idea = drafted()
    repository.save(idea)
    idea.mark_published("https://x/1", now=NOW)
    repository.save(idea)

    assert len(repository.list()) == 1
    reloaded = repository.get(idea.id)
    assert reloaded.status is ContentStatus.PUBLISHED
    assert reloaded.published_url == "https://x/1"
    assert reloaded.published_at == NOW


def test_missing_returns_none(repository) -> None:
    assert repository.get(IdeaId("없음")) is None


def test_list_filters_and_limits(repository) -> None:
    repository.save(drafted("초안"))
    repository.save(ContentIdea.suggest("제안", now=NOW))

    assert len(repository.list()) == 2
    assert len(repository.list(status=ContentStatus.DRAFTED)) == 1
    assert len(repository.list(limit=1)) == 1


def test_find_by_project(repository) -> None:
    repository.save(drafted("A", slug="zunvis"))
    repository.save(drafted("B", slug="other"))

    assert [i.subject for i in repository.find_by_project("zunvis")] == ["A"]
    assert repository.find_by_project("없는프로젝트") == []


# -- 브랜드 성향 저장소 ------------------------------------------------------


def test_brand_voice_defaults_to_zun_before_any_save(db) -> None:
    store = SqliteBrandVoiceStore(db)
    assert "바이브 코딩" in store.get().topics


def test_brand_voice_roundtrip(db) -> None:
    store = SqliteBrandVoiceStore(db)
    store.save(BrandVoice(topics=("Swift",), tone="담백", audience="개발자"))

    loaded = store.get()
    assert loaded.topics == ("Swift",)
    assert loaded.tone == "담백"


def test_brand_voice_stays_a_single_row(db) -> None:
    store = SqliteBrandVoiceStore(db)
    store.save(BrandVoice(topics=("A",)))
    store.save(BrandVoice(topics=("B",)))

    assert db.query_one("SELECT COUNT(*) AS c FROM brand_voice")["c"] == 1
    assert store.get().topics == ("B",)


# -- LLM 대본 생성기 ---------------------------------------------------------

VALID_PAYLOAD = {
    "hook": "3시간 만에 앱 하나",
    "scenes": [
        {"visual": "터미널", "narration": "시작합니다", "duration_seconds": 4},
        {"visual": "브라우저", "narration": "동작합니다", "duration_seconds": 3},
    ],
    "broll": ["키보드 클로즈업"],
    "caption": "만든 걸 공유합니다.",
    "hashtags": ["#AI", "바이브코딩", "AI"],
    "thumbnail_text": "3시간 만에",
    "comment_bait": "뭐부터 만들래요?",
}


def request(**overrides) -> GenerationRequest:
    defaults = dict(
        subject="Claude Code로 앱 만들기",
        content_format=ContentFormat.REELS,
        brand_voice=BrandVoice.default_zun(),
    )
    defaults.update(overrides)
    return GenerationRequest(**defaults)


def test_generator_parses_valid_response() -> None:
    generator = LlmScriptGenerator(EchoAdapter.returning_json(VALID_PAYLOAD))

    script = generator.generate(request())

    assert script.hook == "3시간 만에 앱 하나"
    assert len(script.scenes) == 2
    assert script.total_duration == 7.0
    # 해시태그는 도메인 규칙대로 정규화·중복 제거된다
    assert [t.value for t in script.hashtags] == ["ai", "바이브코딩"]


def test_generator_survives_code_fences() -> None:
    """스키마를 강제해도 모델이 코드펜스를 두르는 경우가 있다."""
    fenced = "```json\n" + json.dumps(VALID_PAYLOAD, ensure_ascii=False) + "\n```"
    script = LlmScriptGenerator(EchoAdapter([fenced])).generate(request())
    assert script.hook == "3시간 만에 앱 하나"


def test_generator_renumbers_scenes() -> None:
    """모델이 준 순서 번호를 믿지 않는다."""
    payload = dict(VALID_PAYLOAD)
    payload["scenes"] = [
        {"visual": "A", "narration": "가", "duration_seconds": 2, "order": 99},
        {"visual": "B", "narration": "나", "duration_seconds": 2, "order": 99},
    ]
    script = LlmScriptGenerator(EchoAdapter.returning_json(payload)).generate(request())
    assert [s.order for s in script.scenes] == [1, 2]


def test_generator_drops_empty_scenes_but_keeps_the_rest() -> None:
    payload = dict(VALID_PAYLOAD)
    payload["scenes"] = [
        {"visual": "", "narration": "", "duration_seconds": 3},
        {"visual": "쓸모 있는 장면", "narration": "내용", "duration_seconds": 3},
    ]
    script = LlmScriptGenerator(EchoAdapter.returning_json(payload)).generate(request())
    assert len(script.scenes) == 1


def test_generator_rejects_response_with_no_usable_scene() -> None:
    payload = dict(VALID_PAYLOAD)
    payload["scenes"] = [{"visual": "", "narration": "", "duration_seconds": 3}]
    with pytest.raises(InvalidScript):
        LlmScriptGenerator(EchoAdapter.returning_json(payload)).generate(request())


def test_generator_rejects_missing_hook() -> None:
    payload = dict(VALID_PAYLOAD)
    payload["hook"] = ""
    with pytest.raises(InvalidScript):
        LlmScriptGenerator(EchoAdapter.returning_json(payload)).generate(request())


def test_generator_rejects_non_json() -> None:
    with pytest.raises(ModelError):
        LlmScriptGenerator(EchoAdapter(["죄송합니다, 도와드릴 수 없습니다"])).generate(request())


def test_generator_rejects_json_that_is_not_an_object() -> None:
    with pytest.raises(ModelError):
        LlmScriptGenerator(EchoAdapter(["[1, 2, 3]"])).generate(request())


def test_generator_clamps_absurd_durations() -> None:
    payload = dict(VALID_PAYLOAD)
    payload["scenes"] = [
        {"visual": "A", "narration": "가", "duration_seconds": 0},
        {"visual": "B", "narration": "나", "duration_seconds": "숫자아님"},
    ]
    script = LlmScriptGenerator(EchoAdapter.returning_json(payload)).generate(request())
    assert all(s.duration_seconds > 0 for s in script.scenes)


# -- 프롬프트 조립 -----------------------------------------------------------


def test_prompt_carries_brand_voice_and_schema() -> None:
    model = EchoAdapter.returning_json(VALID_PAYLOAD)
    LlmScriptGenerator(model).generate(request())

    sent = model.calls[0]
    assert sent.role is ModelRole.DEEP  # 창작은 큰 모델
    assert sent.schema == SCRIPT_SCHEMA  # 구조화 출력을 런타임이 강제한다
    assert "바이브 코딩" in sent.prompt
    assert "쓰지 말 것" in sent.prompt  # 낚시성 문구 금지가 실제로 전달된다
    assert "릴스" in sent.prompt or "9:16" in sent.prompt


def test_prompt_includes_project_context_with_a_warning() -> None:
    model = EchoAdapter.returning_json(VALID_PAYLOAD)
    LlmScriptGenerator(model).generate(
        request(project_context="# zunvis\n목적: 개인 AI OS")
    )

    prompt = model.calls[0].prompt
    assert "개인 AI OS" in prompt
    assert "추측하지 말고" in prompt  # 사실만 쓰라는 지시가 함께 간다


def test_carousel_gets_a_different_guide() -> None:
    model = EchoAdapter.returning_json(VALID_PAYLOAD)
    LlmScriptGenerator(model).generate(request(content_format=ContentFormat.CAROUSEL))
    assert "카드" in model.calls[0].prompt


def test_direction_is_passed_through() -> None:
    model = EchoAdapter.returning_json(VALID_PAYLOAD)
    LlmScriptGenerator(model).generate(request(direction="초보자 대상으로"))
    assert "초보자 대상으로" in model.calls[0].prompt
