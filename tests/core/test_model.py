"""C1 완료 기준: Echo로 결정적 테스트, Ollama는 HTTP 계층만 스텁."""

from __future__ import annotations

import pytest

from junvis.core.model.echo import EchoAdapter
from junvis.core.model.ollama import DEFAULT_MODELS, OllamaAdapter, resolve_model
from junvis.core.model.ports import ModelError, ModelRequest, ModelRole


# -- Echo --------------------------------------------------------------------


def test_echo_returns_responses_in_order_then_repeats_the_last() -> None:
    model = EchoAdapter(["첫째", "둘째"])
    assert [model.complete(ModelRequest(prompt="x")).text for _ in range(3)] == [
        "첫째",
        "둘째",
        "둘째",  # 바닥나면 마지막을 반복한다
    ]


def test_echo_records_requests() -> None:
    model = EchoAdapter()
    model.complete(ModelRequest(prompt="안녕", role=ModelRole.DEEP))
    assert model.calls[0].prompt == "안녕"
    assert model.calls[0].role is ModelRole.DEEP


def test_echo_can_simulate_failure() -> None:
    with pytest.raises(ModelError):
        EchoAdapter(fail_with="모델 죽음").complete(ModelRequest(prompt="x"))


# -- Ollama: 모델 선택 --------------------------------------------------------


def test_default_models_are_defined_for_every_role() -> None:
    assert set(DEFAULT_MODELS) == set(ModelRole)


def test_env_var_overrides_model(monkeypatch) -> None:
    monkeypatch.setenv("JUNVIS_MODEL_DEEP", "qwen3:32b")
    assert resolve_model(ModelRole.DEEP) == "qwen3:32b"
    monkeypatch.delenv("JUNVIS_MODEL_DEEP")
    assert resolve_model(ModelRole.DEEP) == DEFAULT_MODELS[ModelRole.DEEP]


def test_explicit_models_win_over_env(monkeypatch) -> None:
    monkeypatch.setenv("JUNVIS_MODEL_FAST", "무시될모델")
    adapter = OllamaAdapter(models={ModelRole.FAST: "지정모델", ModelRole.DEEP: "d"})
    assert adapter.model_for(ModelRole.FAST) == "지정모델"


# -- Ollama: 요청 형태 --------------------------------------------------------


class StubOllama(OllamaAdapter):
    """HTTP만 갈아끼운다. 요청 조립과 응답 해석이 검증 대상이다."""

    def __init__(self, payload: dict, **kwargs) -> None:
        super().__init__(**kwargs)
        self.payload = payload
        self.sent: list[tuple[str, dict]] = []

    def _post(self, path: str, body: dict) -> dict:
        self.sent.append((path, body))
        return self.payload


def ok_payload(text: str = '{"ok": true}') -> dict:
    return {
        "message": {"content": text},
        "eval_count": 40,
        "prompt_eval_count": 60,
        "done_reason": "stop",
    }


def test_request_body_shape() -> None:
    model = StubOllama(ok_payload(), models={ModelRole.FAST: "f", ModelRole.DEEP: "d"})

    model.complete(
        ModelRequest(
            prompt="사용자 입력",
            system="시스템 지시",
            role=ModelRole.DEEP,
            temperature=0.3,
            schema={"type": "object"},
            max_tokens=512,
        )
    )

    path, body = model.sent[0]
    assert path == "/api/chat"
    assert body["model"] == "d"
    assert body["stream"] is False
    assert body["messages"] == [
        {"role": "system", "content": "시스템 지시"},
        {"role": "user", "content": "사용자 입력"},
    ]
    assert body["options"] == {"temperature": 0.3, "num_predict": 512}
    # 스키마를 그대로 넘긴다 — "JSON으로만 답하세요"라고 빌지 않는다
    assert body["format"] == {"type": "object"}


def test_system_message_is_omitted_when_empty() -> None:
    model = StubOllama(ok_payload())
    model.complete(ModelRequest(prompt="x"))
    assert len(model.sent[0][1]["messages"]) == 1


def test_format_is_omitted_without_schema() -> None:
    model = StubOllama(ok_payload())
    model.complete(ModelRequest(prompt="x"))
    assert "format" not in model.sent[0][1]


def test_token_count_sums_prompt_and_completion() -> None:
    response = StubOllama(ok_payload()).complete(ModelRequest(prompt="x"))
    assert response.tokens == 100
    assert response.meta["done_reason"] == "stop"


def test_empty_response_is_an_error() -> None:
    with pytest.raises(ModelError):
        StubOllama(ok_payload("   ")).complete(ModelRequest(prompt="x"))


def test_connection_failure_gives_an_actionable_message() -> None:
    # 아무도 듣고 있지 않은 포트. 프록시를 타지 않으므로 즉시 거부된다.
    adapter = OllamaAdapter("http://127.0.0.1:1", timeout=2)
    assert adapter.is_available() is False
    with pytest.raises(ModelError, match="ollama serve"):
        adapter.complete(ModelRequest(prompt="x"))


def test_installed_models_is_empty_when_unreachable() -> None:
    assert OllamaAdapter("http://127.0.0.1:1", timeout=2).installed_models() == []


def test_ollama_keeps_the_model_resident() -> None:
    """5분 유휴 후 재적재 비용이 판정기 타임아웃을 부른다.

    판정기는 발화마다 돈다. 그 차이가 "반응하지 않는 비서"를 만든다.
    """
    import json
    from unittest.mock import patch

    from junvis.core.model.ollama import KEEP_ALIVE, OllamaAdapter
    from junvis.core.model.ports import ModelRequest

    sent = {}

    def capture(self, path, body):
        sent.update(body)
        return {"message": {"content": "네"}, "model": "test"}

    with patch.object(OllamaAdapter, "_post", capture):
        OllamaAdapter().complete(ModelRequest(prompt="안녕"))

    assert sent["keep_alive"] == KEEP_ALIVE
    assert json.dumps(sent)  # 직렬화 가능해야 실제로 나간다
