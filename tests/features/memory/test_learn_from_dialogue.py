"""대화에서 오래 갈 사실만 뽑는다 (Mem0의 2단계, docs/10 §3)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from junvis.core.model.ports import ModelError, ModelResponse
from junvis.features.memory.application.use_cases.learn_from_dialogue import (
    LearnFromDialogue,
)


@dataclass
class ScriptedModel:
    """호출 순서대로 답을 돌려준다. 1단계 추출, 2단계 조정."""

    answers: list[str] = field(default_factory=list)
    raises: Exception | None = None
    calls: list = field(default_factory=list)

    def complete(self, request):
        self.calls.append(request)
        if self.raises is not None:
            raise self.raises
        body = self.answers.pop(0) if self.answers else '{"facts": []}'
        return ModelResponse(text=body, model="scripted")


@dataclass
class FakeHit:
    id: str
    text: str


class FakeMemory:
    def __init__(self, existing: list[FakeHit] | None = None) -> None:
        self.existing = existing or []
        self.remembered: list[str] = []
        self.forgotten: list[str] = []

    def remember(self, text, *, scope=None, source="", **_kw):
        self.remembered.append(text)
        return text

    def recall(self, query, limit=3):
        return self.existing[:limit]

    def forget(self, memory_id):
        self.forgotten.append(memory_id)
        return memory_id


def build(model, memory: FakeMemory) -> LearnFromDialogue:
    return LearnFromDialogue(model, memory.remember, memory.recall, memory.forget)


def facts(*items) -> str:
    return json.dumps({"facts": list(items)}, ensure_ascii=False)


def decisions(*items) -> str:
    return json.dumps({"decisions": list(items)}, ensure_ascii=False)


# -- 1단계: 잡음을 거른다 ------------------------------------------------------


def test_chatter_is_not_remembered() -> None:
    """이것이 자동 기억의 열쇠다. 다 저장하면 잡음이 신호를 덮는다."""
    model = ScriptedModel([facts()])
    memory = FakeMemory()

    assert build(model, memory)("안녕", "안녕하세요") == ()
    assert memory.remembered == []


def test_a_durable_fact_is_remembered() -> None:
    model = ScriptedModel([facts("릴스 썸네일 문구는 세 단어 이하로 한다")])
    memory = FakeMemory()

    build(model, memory)("썸네일은 세 단어 넘으면 안 읽혀", "기억하겠습니다")

    assert memory.remembered == ["릴스 썸네일 문구는 세 단어 이하로 한다"]


def test_an_empty_question_costs_nothing() -> None:
    model = ScriptedModel()

    assert build(model, FakeMemory())("  ", "답") == ()
    assert model.calls == []


def test_too_many_facts_are_capped() -> None:
    """한 번의 대화에서 열 개가 나오면 그건 잡음이다."""
    model = ScriptedModel([facts(*[f"사실{i}" for i in range(20)])])
    memory = FakeMemory()

    build(model, memory)("질문", "답")

    assert len(memory.remembered) == 5


# -- 2단계: 생각이 바뀌면 따라간다 ---------------------------------------------


def test_a_changed_mind_replaces_the_old_memory() -> None:
    """이 단계가 없으면 "Ollama를 쓴다"와 "Claude를 쓴다"가 둘 다 남는다."""
    model = ScriptedModel(
        [
            facts("로컬 모델 대신 Claude를 쓴다"),
            decisions({"event": "UPDATE", "id": "a1", "text": "Claude를 쓴다"}),
        ]
    )
    memory = FakeMemory([FakeHit("a1", "로컬 모델로 Ollama를 쓴다")])

    build(model, memory)("이제 Claude 쓸래", "그렇게 하겠습니다")

    assert memory.forgotten == ["a1"]
    assert memory.remembered == ["Claude를 쓴다"]


def test_a_duplicate_is_dropped() -> None:
    model = ScriptedModel(
        [facts("릴스 썸네일은 세 단어 이하"), decisions({"event": "NONE"})]
    )
    memory = FakeMemory([FakeHit("b2", "릴스 썸네일 문구는 세 단어 이하로 한다")])

    build(model, memory)("썸네일 세 단어", "네")

    assert memory.remembered == []
    assert memory.forgotten == []


def test_with_nothing_to_compare_the_second_call_is_skipped() -> None:
    """견줄 것이 없으면 전부 새 것이다. 호출 하나를 아낀다."""
    model = ScriptedModel([facts("Claude를 쓴다")])
    memory = FakeMemory()

    build(model, memory)("질문", "답")

    assert len(model.calls) == 1
    assert memory.remembered == ["Claude를 쓴다"]


# -- 실패해도 대화를 방해하지 않는다 -------------------------------------------


def test_a_dead_model_is_silent() -> None:
    """대화는 이미 끝났고 사용자는 기다리고 있지 않다."""
    model = ScriptedModel(raises=ModelError("Ollama 없음"))

    assert build(model, FakeMemory())("질문", "답") == ()


def test_broken_json_is_survived() -> None:
    model = ScriptedModel(["이건 JSON이 아니다"])

    assert build(model, FakeMemory())("질문", "답") == ()


def test_a_failed_reconciliation_still_saves() -> None:
    """조정에 실패해도 기억을 못 남기는 것보다 넣는 편이 낫다."""
    model = ScriptedModel([facts("Claude를 쓴다"), "망가진 응답"])
    memory = FakeMemory([FakeHit("a1", "Ollama를 쓴다")])

    build(model, memory)("질문", "답")

    assert memory.remembered == ["Claude를 쓴다"]


def test_a_failed_forget_still_saves_the_new_fact() -> None:
    model = ScriptedModel(
        [facts("Claude를 쓴다"), decisions({"event": "UPDATE", "id": "없음", "text": "Claude를 쓴다"})]
    )
    memory = FakeMemory([FakeHit("a1", "Ollama를 쓴다")])
    memory.forget = lambda _id: (_ for _ in ()).throw(RuntimeError("없는 기억"))

    build(model, memory)("질문", "답")

    assert memory.remembered == ["Claude를 쓴다"]


def test_extraction_uses_the_fast_role() -> None:
    """여기에 큰 모델을 부르면 답한 뒤 10초를 더 기다리게 된다."""
    from junvis.core.model.ports import ModelRole

    model = ScriptedModel([facts("무언가")])
    build(model, FakeMemory())("질문", "답")

    assert model.calls[0].role is ModelRole.FAST
    assert model.calls[0].temperature < 0.3  # 사실 추출에 창의성은 해롭다
