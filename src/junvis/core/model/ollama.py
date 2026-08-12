"""Ollama 어댑터 — 로컬 우선 원칙의 실제 구현.

새 의존성을 넣지 않는다. `ollama` 파이썬 패키지 대신 urllib을 쓴다.
필요한 것은 POST 하나뿐이고, 의존성 하나를 줄이면 macOS에서 설치가
하나 쉬워진다.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

from junvis.core.model.ports import ModelError, ModelRequest, ModelResponse, ModelRole

logger = logging.getLogger(__name__)

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_TIMEOUT = 120  # 로컬 창작 생성은 느릴 수 있다

#: 실제로 존재하는 Ollama 태그를 기본값으로 둔다. 환경변수로 바꾼다.
DEFAULT_MODELS: dict[ModelRole, str] = {
    ModelRole.FAST: "llama3.2:3b",
    ModelRole.DEEP: "qwen2.5:14b",
}
MODEL_ENV_VARS: dict[ModelRole, str] = {
    ModelRole.FAST: "JUNVIS_MODEL_FAST",
    ModelRole.DEEP: "JUNVIS_MODEL_DEEP",
}

#: 프록시를 타지 않는 오프너. 로컬 서버에 나가는 요청이 회사·에이전트
#: 프록시로 새면 연결이 되지 않거나 느려진다.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def resolve_model(role: ModelRole) -> str:
    return os.environ.get(MODEL_ENV_VARS[role]) or DEFAULT_MODELS[role]


class OllamaAdapter:
    def __init__(
        self,
        host: str | None = None,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        models: dict[ModelRole, str] | None = None,
    ) -> None:
        self._host = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")
        self._timeout = timeout
        self._models = models or {role: resolve_model(role) for role in ModelRole}

    def model_for(self, role: ModelRole) -> str:
        return self._models[role]

    def complete(self, request: ModelRequest) -> ModelResponse:
        model = self.model_for(request.role)
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})

        options: dict[str, object] = {"temperature": request.temperature}
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens

        body: dict[str, object] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        if request.schema is not None:
            # Ollama의 구조화 출력. 스키마를 그대로 넘기면 문법적으로 유효한
            # JSON이 보장된다(내용의 타당성은 도메인이 따로 검증한다).
            body["format"] = request.schema

        started = time.perf_counter()
        payload = self._post("/api/chat", body)
        latency_ms = int((time.perf_counter() - started) * 1000)

        text = (payload.get("message") or {}).get("content", "")
        if not isinstance(text, str) or not text.strip():
            raise ModelError(f"{model}이 빈 응답을 돌려줬습니다")

        return ModelResponse(
            text=text,
            model=model,
            tokens=int(payload.get("eval_count", 0))
            + int(payload.get("prompt_eval_count", 0)),
            latency_ms=latency_ms,
            meta={"done_reason": payload.get("done_reason", "")},
        )

    def is_available(self) -> bool:
        """Ollama가 떠 있는지. `junvis doctor`가 쓴다."""
        try:
            self._send(
                urllib.request.Request(f"{self._host}/api/tags", method="GET"),
                timeout=2,  # 점검은 빨리 끝나야 한다
            )
        except ModelError:
            return False
        return True

    def installed_models(self) -> list[str]:
        try:
            payload = self._get("/api/tags")
        except ModelError:
            return []
        return [str(m.get("name", "")) for m in payload.get("models", [])]

    # -- HTTP ---------------------------------------------------------------

    def _post(self, path: str, body: dict[str, object]) -> dict:
        request = urllib.request.Request(
            f"{self._host}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return self._send(request)

    def _get(self, path: str) -> dict:
        return self._send(urllib.request.Request(f"{self._host}{path}", method="GET"))

    def _send(self, request: urllib.request.Request, *, timeout: int | None = None) -> dict:
        try:
            # Ollama는 항상 로컬이다. 시스템 프록시를 타면 안 된다.
            with _OPENER.open(request, timeout=timeout or self._timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ModelError(f"Ollama가 {exc.code}를 돌려줬습니다: {exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ModelError(
                f"Ollama에 연결하지 못했습니다({self._host}). "
                "`ollama serve`가 떠 있는지 확인하세요."
            ) from exc
        except json.JSONDecodeError as exc:
            raise ModelError("Ollama 응답을 해석하지 못했습니다") from exc
