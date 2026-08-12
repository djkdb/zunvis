"""게이트 4 — 소형 로컬 모델로 "진짜 명령인가"를 판정한다.

`ModelRole.FAST`를 쓰는 것이 핵심이다. 이 판정에 큰 모델을 부르면 말
한마디마다 몇 초씩 기다리게 되고, 그러면 음성 인터페이스의 의미가 없다.
"""

from __future__ import annotations

import json
import logging

from junvis.core.model.ports import ModelPort, ModelRequest, ModelRole

logger = logging.getLogger(__name__)

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_command": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["is_command"],
}

SYSTEM_PROMPT = """너는 음성 비서의 입력 필터다.
사용자가 비서에게 **직접 지시한 말**인지, 아니면 옆 사람과의 대화·혼잣말·
잡음이 잘못 인식된 것인지 판정한다.
확실하지 않으면 명령으로 본다 — 사용자를 무시하는 것이 더 나쁜 실패다.
반드시 요청된 JSON 스키마로만 답한다."""

PROMPT_TEMPLATE = """다음 발화가 비서에게 내린 명령인가?

발화: {text}

명령의 예: "오늘 브리핑", "프로젝트 목록 보여줘", "릴스 하나 만들자"
명령이 아닌 예: "어 잠깐만", "그러니까 내 말은", "음...", 의미 없는 음절"""


class LlmIntentJudge:
    def __init__(self, model: ModelPort, *, role: ModelRole = ModelRole.FAST) -> None:
        self._model = model
        self._role = role

    def is_command(self, text: str) -> bool:
        response = self._model.complete(
            ModelRequest(
                system=SYSTEM_PROMPT,
                prompt=PROMPT_TEMPLATE.format(text=text),
                role=self._role,
                temperature=0.0,  # 판정은 결정적이어야 한다
                schema=JUDGE_SCHEMA,
            )
        )
        return self._parse(response.text)

    @staticmethod
    def _parse(raw: str) -> bool:
        """읽을 수 없는 응답은 '명령이다'로 본다.

        사용자를 무시하는 것이 잘못 실행하는 것보다 나쁜 실패다.
        실행 자체는 PolicyEngine이 다시 막는다.
        """
        text = raw.strip()
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else text
            if text.startswith("json"):
                text = text[4:]
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.debug("Intent Judge 응답을 읽지 못함: %r", raw[:120])
            return True
        if not isinstance(data, dict) or "is_command" not in data:
            return True
        return bool(data["is_command"])
