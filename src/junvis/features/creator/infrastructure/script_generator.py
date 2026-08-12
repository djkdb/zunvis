"""LLM으로 대본을 생성한다.

프롬프트 조립과 JSON 파싱은 **모델에 종속된 관심사**이므로 인프라에 산다.
유스케이스는 `ScriptGeneratorPort`만 알고, 테스트는 Fake 생성기를 쓴다.

구조화 출력은 Ollama의 `format`에 JSON Schema를 넘겨 얻는다. "JSON으로만
답하세요"라고 프롬프트로 비는 방식은 작은 로컬 모델에서 자주 깨진다.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from junvis.core.model.ports import ModelError, ModelPort, ModelRequest, ModelRole
from junvis.features.creator.application.ports import GenerationRequest
from junvis.features.creator.domain.errors import InvalidScript
from junvis.features.creator.domain.model import ReelScript, Scene
from junvis.features.creator.domain.value_objects import (
    HASHTAG_MAX_COUNT,
    ContentFormat,
    Hashtag,
)

logger = logging.getLogger(__name__)

#: 모델에게 요구하는 출력 형태. 도메인의 9개 구성요소와 1:1로 대응한다.
SCRIPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "hook": {"type": "string"},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "visual": {"type": "string"},
                    "narration": {"type": "string"},
                    "duration_seconds": {"type": "number"},
                },
                "required": ["visual", "narration", "duration_seconds"],
            },
        },
        "broll": {"type": "array", "items": {"type": "string"}},
        "caption": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "thumbnail_text": {"type": "string"},
        "comment_bait": {"type": "string"},
    },
    "required": [
        "hook",
        "scenes",
        "broll",
        "caption",
        "hashtags",
        "thumbnail_text",
        "comment_bait",
    ],
}

SYSTEM_PROMPT = """너는 개발자 브랜드의 숏폼 콘텐츠 기획자다.
과장이나 낚시 없이, 실제로 만든 것을 보여주는 방식으로 기획한다.
반드시 한국어로 쓴다. 요청된 JSON 스키마에 정확히 맞춰 답한다."""

FORMAT_GUIDE = {
    ContentFormat.REELS: (
        "형식: 인스타그램 릴스 (세로 9:16, 20~45초).\n"
        "- Hook은 첫 3초 안에 끝나야 하고, 보는 사람이 멈출 이유를 준다\n"
        "- 장면은 4~8개. 각 장면은 화면에 무엇이 보이는지(visual)와 무슨 말을 하는지(narration)를 나눈다\n"
        "- 화면 녹화·터미널·에디터처럼 실제 작업 장면을 적극 활용한다"
    ),
    ContentFormat.CAROUSEL: (
        "형식: 인스타그램 캐러셀 (정사각 1:1, 5~10장).\n"
        "- Hook은 1번 카드에 들어갈 문장이다\n"
        "- 각 장면 = 카드 한 장. visual은 카드에 들어갈 그림/코드, narration은 카드 본문\n"
        "- duration_seconds는 카드당 읽는 데 걸리는 시간으로 잡는다"
    ),
}


class LlmScriptGenerator:
    def __init__(self, model: ModelPort, *, role: ModelRole = ModelRole.DEEP) -> None:
        self._model = model
        self._role = role

    def generate(self, request: GenerationRequest) -> ReelScript:
        response = self._model.complete(
            ModelRequest(
                system=SYSTEM_PROMPT,
                prompt=self._build_prompt(request),
                role=self._role,
                temperature=0.8,  # 창작이므로 결정적일 필요가 없다
                schema=SCRIPT_SCHEMA,
            )
        )
        return self._parse(response.text)

    # -- 프롬프트 -----------------------------------------------------------

    def _build_prompt(self, request: GenerationRequest) -> str:
        parts = [
            f"주제: {request.subject}",
            "",
            FORMAT_GUIDE[request.content_format],
            "",
            "브랜드 성향:",
            request.brand_voice.describe(),
        ]
        if request.project_context:
            parts += [
                "",
                "이 콘텐츠가 다루는 프로젝트의 실제 정보 "
                "(추측하지 말고 여기 있는 사실만 쓸 것):",
                request.project_context,
            ]
        if request.direction:
            parts += ["", f"추가 지시: {request.direction}"]
        parts += [
            "",
            f"해시태그는 {HASHTAG_MAX_COUNT}개 이하로, '#' 없이 단어만 배열에 담는다.",
            "썸네일 문구는 5단어 이내로 짧게.",
            "댓글 유도 문구는 시청자가 실제로 답할 수 있는 구체적인 질문으로.",
        ]
        return "\n".join(parts)

    # -- 파싱 ---------------------------------------------------------------

    def _parse(self, text: str) -> ReelScript:
        data = self._load_json(text)
        scenes = self._parse_scenes(data.get("scenes"))
        try:
            return ReelScript(
                hook=str(data.get("hook", "")).strip(),
                scenes=scenes,
                caption=str(data.get("caption", "")).strip(),
                hashtags=Hashtag.many(self._string_list(data.get("hashtags"))),
                broll=tuple(self._string_list(data.get("broll"))),
                thumbnail_text=str(data.get("thumbnail_text", "")).strip(),
                comment_bait=str(data.get("comment_bait", "")).strip(),
            )
        except InvalidScript:
            # 도메인 규칙 위반은 그대로 올린다. 유효하지 않은 대본을 저장하느니
            # 실패하는 편이 낫다.
            raise

    @staticmethod
    def _load_json(text: str) -> dict[str, Any]:
        """스키마를 강제했어도 모델이 코드펜스를 두르는 경우가 있다."""
        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = candidate.split("```")[1]
            if candidate.startswith("json"):
                candidate = candidate[4:]
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise ModelError(f"모델 응답을 JSON으로 읽지 못했습니다: {text[:200]}") from exc
        if not isinstance(data, dict):
            raise ModelError("모델이 객체가 아닌 값을 돌려줬습니다")
        return data

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _parse_scenes(value: Any) -> tuple[Scene, ...]:
        if not isinstance(value, list):
            raise InvalidScript("장면 목록이 없습니다")
        scenes: list[Scene] = []
        for index, raw in enumerate(value, start=1):
            if not isinstance(raw, dict):
                continue
            try:
                duration = float(raw.get("duration_seconds", 3.0))
            except (TypeError, ValueError):
                duration = 3.0
            visual = str(raw.get("visual", "")).strip()
            narration = str(raw.get("narration", "")).strip()
            if not visual and not narration:
                continue  # 빈 장면은 조용히 버린다
            scenes.append(
                Scene(
                    order=len(scenes) + 1,  # 모델이 준 번호를 믿지 않고 다시 매긴다
                    visual=visual,
                    narration=narration,
                    duration_seconds=max(duration, 0.5),
                )
            )
        if not scenes:
            raise InvalidScript("쓸 수 있는 장면이 하나도 없습니다")
        return tuple(scenes)
