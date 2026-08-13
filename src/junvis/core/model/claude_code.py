"""Claude Code CLI를 두뇌로 쓴다.

`claude -p` 는 대화 한 번을 비대화식으로 처리하고 stdout으로 답을 준다.
이미 깔려 있고 이미 로그인돼 있으므로 **API 키도 Ollama도 필요 없다.**
로컬 소형 모델과는 답변 품질이 비교가 되지 않는다.

## 왜 stdin으로 보내는가

프롬프트에는 문맥이 실려 길고, 따옴표·개행·한글이 섞인다. 인자로 넘기면
셸 이스케이프와 길이 제한에 걸린다. stdin에는 그런 것이 없다.

## 왜 파일을 고칠 수 있는 도구를 막는가

음성은 오인식이 잦은 입력이다. "자비스 그거 지워줘"가 잘못 들리면 무엇이
지워질지 알 수 없다. 말로 시작된 작업이 조용히 파일을 고치면 안 된다.
읽기 도구는 남겨 둔다 — 그것은 되돌릴 것이 없다.

## 왜 JUNVIS 홈에서 실행하는가

사용자의 프로젝트 폴더에서 돌리면 그쪽 세션 기록과 섞인다. 남의 작업 상태를
건드리지 않는다.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from junvis.core.model.ports import (
    ModelError,
    ModelRequest,
    ModelResponse,
    ModelRole,
)

logger = logging.getLogger(__name__)

BINARY_ENV = "JUNVIS_CLAUDE_BIN"
MODEL_ENV = "JUNVIS_CLAUDE_MODEL"
DEFAULT_BINARY = "claude"

#: 되돌릴 수 없는 것들. 말 한마디로 파일이 바뀌면 안 된다.
FORBIDDEN_TOOLS = ("Bash", "Edit", "Write", "NotebookEdit")

#: Claude는 생각한다. 짧게 자르면 답 대신 침묵을 받는다.
DEFAULT_TIMEOUT = 90


class ClaudeCodeAdapter:
    def __init__(
        self,
        *,
        binary: str | None = None,
        model: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        cwd: Path | None = None,
    ) -> None:
        self._binary = binary or os.environ.get(BINARY_ENV) or DEFAULT_BINARY
        self._model = model or os.environ.get(MODEL_ENV) or ""
        self._timeout = timeout
        self._cwd = cwd

    # -- ModelPort ----------------------------------------------------------

    def complete(self, request: ModelRequest) -> ModelResponse:
        prompt = request.prompt
        if request.schema is not None:
            prompt = f"{prompt}\n\n{_json_instruction(request.schema)}"

        text = self._run(prompt, request.system)
        if request.schema is not None:
            text = _first_json_object(text)
        return ModelResponse(text=text, model=self._model or "claude-code")

    def model_for(self, role: ModelRole) -> str:
        return self._model or "claude-code"

    def is_available(self) -> bool:
        return shutil.which(self._binary) is not None

    def installed_models(self) -> list[str]:
        """Ollama처럼 목록을 세지 않는다. 있으면 그냥 된다."""
        return [self.model_for(ModelRole.FAST)] if self.is_available() else []

    # -- 내부 ---------------------------------------------------------------

    def command(self) -> list[str]:
        argv = [self._binary, "-p", "--output-format", "text"]
        if self._model:
            argv += ["--model", self._model]
        argv += ["--disallowed-tools", *FORBIDDEN_TOOLS]
        return argv

    def _run(self, prompt: str, system: str) -> str:
        if not self.is_available():
            raise ModelError(
                f"{self._binary} 를 찾지 못했습니다.\n"
                "  Claude Code를 설치하고 로그인하세요: https://claude.com/claude-code"
            )

        argv = self.command()
        if system:
            argv += ["--append-system-prompt", system]

        try:
            result = subprocess.run(
                argv,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                cwd=str(self._cwd) if self._cwd else None,
            )
        except subprocess.TimeoutExpired as exc:
            raise ModelError(f"Claude가 {self._timeout}초 안에 답하지 않았습니다.") from exc
        except OSError as exc:
            raise ModelError(f"Claude를 실행하지 못했습니다: {exc}") from exc

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise ModelError(f"Claude가 실패했습니다: {detail[:400]}")

        answer = (result.stdout or "").strip()
        if not answer:
            raise ModelError("Claude가 빈 답을 돌려줬습니다.")
        return answer


def _json_instruction(schema: dict) -> str:
    """구조화 출력이 없으므로 프롬프트로 요구한다.

    Ollama 어댑터는 런타임이 스키마를 강제하지만 CLI에는 그 통로가 없다.
    대신 받은 뒤에 검사한다 — 비는 것보다 확인하는 쪽이 낫다.
    """
    return (
        "아래 JSON 스키마에 맞는 JSON 객체 **하나만** 출력하세요. "
        "설명도 코드펜스도 붙이지 마세요.\n"
        f"{json.dumps(schema, ensure_ascii=False)}"
    )


def _first_json_object(text: str) -> str:
    """코드펜스와 앞뒤 설명을 걷어내고 JSON 객체 하나를 꺼낸다."""
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    try:
        json.loads(stripped)
        return stripped
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    if start < 0:
        raise ModelError(f"Claude의 답에서 JSON을 찾지 못했습니다: {text[:200]}")

    # 중괄호를 세어 짝이 맞는 곳까지 자른다. 문자열 안의 괄호는 세지 않는다.
    depth, in_string, escaped = 0, False, False
    for index in range(start, len(stripped)):
        char = stripped[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return stripped[start : index + 1]
    raise ModelError(f"Claude의 JSON이 끝나지 않았습니다: {text[:200]}")
