"""creator application 테스트용 Fake."""

from __future__ import annotations

from junvis.features.creator.application.ports import GenerationRequest
from junvis.features.creator.domain.model import ContentIdea, ReelScript, Scene
from junvis.features.creator.domain.repository import BrandVoiceStore, ContentRepository
from junvis.features.creator.domain.value_objects import (
    BrandVoice,
    ContentStatus,
    Hashtag,
    IdeaId,
)


def sample_script() -> ReelScript:
    return ReelScript(
        hook="Claude Code로 3시간 만에 앱 하나",
        scenes=(
            Scene(1, "터미널", "프로젝트를 만듭니다", 4.0),
            Scene(2, "브라우저", "동작합니다", 3.0),
        ),
        caption="이번에 만든 걸 공유합니다.",
        hashtags=Hashtag.many(["AI", "바이브코딩"]),
        broll=("키보드 클로즈업",),
        thumbnail_text="3시간 만에",
        comment_bait="어떤 앱부터 만들어볼래요?",
    )


class InMemoryContentRepository(ContentRepository):
    def __init__(self) -> None:
        self.items: dict[str, ContentIdea] = {}

    def save(self, idea: ContentIdea) -> None:
        self.items[idea.id.value] = idea

    def get(self, idea_id: IdeaId) -> ContentIdea | None:
        return self.items.get(idea_id.value)

    def list(
        self, *, status: ContentStatus | None = None, limit: int = 50
    ) -> list[ContentIdea]:
        items = sorted(self.items.values(), key=lambda i: i.updated_at, reverse=True)
        if status is not None:
            items = [i for i in items if i.status is status]
        return items[:limit]

    def find_by_project(self, slug: str) -> list[ContentIdea]:
        return [i for i in self.items.values() if i.source_project_slug == slug]


class InMemoryBrandVoiceStore(BrandVoiceStore):
    def __init__(self, voice: BrandVoice | None = None) -> None:
        self.voice = voice

    def get(self) -> BrandVoice:
        return self.voice or BrandVoice.default_zun()

    def save(self, voice: BrandVoice) -> None:
        self.voice = voice


class FakeGenerator:
    """LLM을 부르지 않는 대본 생성기. 요청을 기록해 검증에 쓴다."""

    def __init__(self, script: ReelScript | None = None, *, fail: Exception | None = None):
        self.script = script or sample_script()
        self.fail = fail
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> ReelScript:
        self.requests.append(request)
        if self.fail is not None:
            raise self.fail
        return self.script


class FakeProjectContext:
    def __init__(self, context: str | None = "# zunvis\n\n## 목적\n개인 AI OS") -> None:
        self.context = context
        self.asked: list[str] = []

    def get_context(self, slug: str, *, budget_tokens: int = 800) -> str | None:
        self.asked.append(slug)
        return self.context
