"""대화 — 규칙이 못 잡은 말을 받는다."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from junvis.apps.conversation import OFFLINE_ANSWER, Conversation
from junvis.core.model.ports import ModelError, ModelResponse


@dataclass
class FakeModel:
    answer: str = "그렇게 하시면 좋겠습니다."
    raises: Exception | None = None
    calls: list = field(default_factory=list)

    def complete(self, request):
        self.calls.append(request)
        if self.raises is not None:
            raise self.raises
        return ModelResponse(text=self.answer, model="fake")


@dataclass(frozen=True)
class FakeSummary:
    name: str
    tech_stack: tuple[str, ...] = ()
    last_commit: str | None = None
    dirty: bool = False


@pytest.fixture()
def model() -> FakeModel:
    return FakeModel()


def test_it_answers(model) -> None:
    assert Conversation(model).answer("뭐부터 할까") == "그렇게 하시면 좋겠습니다."


def test_a_blank_question_costs_nothing(model) -> None:
    assert Conversation(model).answer("   ") == ""
    assert model.calls == []


def test_projects_are_in_the_prompt(model) -> None:
    """근거 없이 답하면 그럴듯한 거짓말을 한다."""
    conversation = Conversation(
        model,
        list_projects=lambda: [FakeSummary("릴스 편집기", ("Python",), "a1b2c3d", True)],
    )

    conversation.answer("요즘 뭐 하고 있었지")

    prompt = model.calls[0].prompt
    assert "릴스 편집기" in prompt
    assert "Python" in prompt
    assert "커밋 안 한 변경 있음" in prompt


def test_memories_are_in_the_prompt(model) -> None:
    conversation = Conversation(model, digest=lambda budget: "썸네일 문구는 3단어 이하로")

    conversation.answer("썸네일 어떻게 할까")

    assert "썸네일 문구는 3단어 이하로" in model.calls[0].prompt


def test_history_is_carried(model) -> None:
    """"그거 자세히" 가 통하려면 앞을 알아야 한다."""
    conversation = Conversation(model)
    conversation.answer("릴스 주제 뭐가 좋을까")

    conversation.answer("그거 자세히")

    assert "릴스 주제 뭐가 좋을까" in model.calls[1].prompt
    assert "그렇게 하시면 좋겠습니다" in model.calls[1].prompt


def test_history_is_bounded(model) -> None:
    """로컬 소형 모델은 문맥이 길면 앞을 잊고 헤맨다."""
    conversation = Conversation(model, history_turns=2)
    for index in range(5):
        conversation.answer(f"질문{index}")

    prompt = model.calls[-1].prompt
    assert "질문3" in prompt
    assert "질문0" not in prompt


def test_a_broken_context_does_not_stop_the_answer(model) -> None:
    """문맥 한 조각이 없다고 대화를 못 하게 하지 않는다."""

    def explode():
        raise RuntimeError("저장소가 잠겼다")

    conversation = Conversation(model, list_projects=explode)

    assert conversation.answer("안녕") == "그렇게 하시면 좋겠습니다."


def test_a_dead_model_says_so(model) -> None:
    """조용히 실패하면 사용자는 자기 말이 안 들린 줄 안다."""
    model.raises = ModelError("연결 거부")

    answer = Conversation(model).answer("안녕")

    assert OFFLINE_ANSWER in answer
    # 왜 안 되는지는 어댑터가 안다. 그 말이 사라지면 사용자는 헤맨다.
    assert "연결 거부" in answer


def test_markdown_is_stripped_for_speech(model) -> None:
    """별표가 그대로 스피커로 나가면 "별표 별표 브리핑"이 된다."""
    model.answer = "- **첫째** 항목\n- `둘째` 항목"

    assert Conversation(model).answer("뭐 해야 해") == "첫째 항목 둘째 항목"


def test_the_system_prompt_knows_who_it_serves(model) -> None:
    Conversation(model).answer("안녕")

    system = model.calls[0].system
    assert "ZUN" in system
    assert "두세 문장" in system
