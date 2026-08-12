"""EchoAdapter — 테스트가 LLM에 의존하지 않게 만드는 장치.

설계 §8: "LLM 응답에 의존하는 테스트는 만들지 않는다. 모델은 항상
EchoAdapter로 대체한다." 테스트가 모델 품질에 따라 흔들리면 그것은
테스트가 아니라 관찰이다.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from junvis.core.model.ports import ModelError, ModelRequest, ModelResponse


class EchoAdapter:
    """미리 정한 응답을 순서대로 돌려준다.

    `responses`가 바닥나면 마지막 응답을 계속 반복한다 — 테스트가
    호출 횟수를 정확히 맞추느라 깨지지 않도록.
    """

    def __init__(
        self,
        responses: list[str] | None = None,
        *,
        model: str = "echo",
        on_call: Callable[[ModelRequest], None] | None = None,
        fail_with: str | None = None,
    ) -> None:
        self._responses = list(responses or ["echo"])
        self._model = model
        self._on_call = on_call
        self._fail_with = fail_with
        self.calls: list[ModelRequest] = []

    @classmethod
    def returning_json(cls, payload: object, **kwargs) -> EchoAdapter:
        return cls([json.dumps(payload, ensure_ascii=False)], **kwargs)

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        if self._on_call is not None:
            self._on_call(request)
        if self._fail_with is not None:
            raise ModelError(self._fail_with)
        text = self._responses[min(len(self.calls) - 1, len(self._responses) - 1)]
        return ModelResponse(text=text, model=self._model, tokens=len(text) // 4)
