"""대화에서 오래 갈 사실만 뽑아 기억한다.

Mem0의 2단계 구조를 개념만 가져왔다(docs/10 §3). 라이브러리는 쓰지 않는다 —
벡터 스토어와 임베딩까지 딸려 오는데 우리는 SQLite+FTS5로 충분하다.

## 왜 2단계인가

**1단계 · 추출.** 대화를 통째로 넣고 "오래 갈 사실"만 뽑는다. 핵심은 프롬프트
본문이 아니라 **예시**다. 잡담에 빈 목록을 돌려주도록 가르친다. 이것이 없으면
"안녕하세요"까지 기억이 되고, 잡음이 신호를 덮는다.

**2단계 · 조정.** 뽑은 사실을 기존 기억과 나란히 놓고 무엇을 할지 정한다.
이 단계가 없으면 "Ollama를 쓴다"가 나중에 "Claude를 쓴다"로 바뀌어도 **둘 다
남는다.** 사람의 생각이 바뀌는 것을 기억이 따라가지 못한다.

## 왜 작은 모델만 쓰는가

대화 한 번에 모델 호출이 둘 늘어난다. 여기에 `claude -p` 를 부르면 답한 뒤
10초를 더 기다리게 된다 — 판정기에서 이미 겪은 실수다. 작은 로컬 모델로
충분한 일이고, 그것이 없으면 **자동 기억을 조용히 포기한다.**
"""

from __future__ import annotations

import json
import logging

from junvis.core.model.ports import ModelError, ModelPort, ModelRequest, ModelRole
from junvis.core.trace.recorder import TraceRecorder
from junvis.core.usecase import TracedUseCase
from junvis.features.memory.application.dto import MemoryView
from junvis.features.memory.domain.model import MemoryScope

logger = logging.getLogger(__name__)

#: 한 번의 대화에서 이보다 많이 뽑히면 잡음이다.
MAX_FACTS = 5
#: 조정할 때 견줄 기존 기억 수. 많이 주면 작은 모델이 헤맨다.
MAX_CANDIDATES = 8

EXTRACT_SYSTEM = """너는 대화에서 **오래 갈 사실**만 골라내는 정리자다.

무엇을 뽑는가: 취향과 선호, 결정과 그 이유, 도구·기술 선택, 계획과 목표,
일하는 방식, 사람·프로젝트에 대한 사실.

무엇을 뽑지 않는가: 인사, 잡담, 지금 이 순간에만 유효한 것("오늘 날씨"),
질문 자체, 네가 한 말.

JSON 객체 하나만 낸다. 뽑을 것이 없으면 빈 목록이다. 이것이 보통이다.

예시:
입력: ZUN: 안녕 / JUNVIS: 안녕하세요
출력: {"facts": []}

입력: ZUN: 지금 몇 시야 / JUNVIS: 세 시입니다
출력: {"facts": []}

입력: ZUN: 릴스 썸네일은 세 단어 넘어가면 안 읽히더라 / JUNVIS: 기억하겠습니다
출력: {"facts": ["릴스 썸네일 문구는 세 단어 이하로 한다"]}

입력: ZUN: 앞으로 Ollama 말고 Claude 쓸래 / JUNVIS: 그렇게 하겠습니다
출력: {"facts": ["로컬 모델 대신 Claude를 쓴다"]}
"""

RECONCILE_SYSTEM = """너는 기억을 관리한다. 새 사실과 기존 기억을 견줘 각
사실마다 하나를 고른다.

- ADD    : 기존에 없는 새 정보다
- UPDATE : 기존 기억을 대체한다. 무엇을 대체하는지 id를 준다
- NONE   : 이미 있거나 담아둘 값어치가 없다

사람의 생각은 바뀐다. 새 사실이 기존 기억과 **모순되면 UPDATE**다. 둘 다
남기지 마라.

JSON 객체 하나만 낸다.

예시:
기존 기억: [{"id": "a1", "text": "로컬 모델로 Ollama를 쓴다"}]
새 사실: ["로컬 모델 대신 Claude를 쓴다"]
출력: {"decisions": [{"event": "UPDATE", "id": "a1", "text": "Claude를 쓴다"}]}

기존 기억: [{"id": "b2", "text": "릴스 썸네일은 세 단어 이하"}]
새 사실: ["릴스 썸네일 문구는 세 단어 이하로 한다"]
출력: {"decisions": [{"event": "NONE"}]}
"""

_FACTS_SCHEMA = {
    "type": "object",
    "properties": {"facts": {"type": "array", "items": {"type": "string"}}},
    "required": ["facts"],
}

_DECISIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "event": {"type": "string", "enum": ["ADD", "UPDATE", "NONE"]},
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["event"],
            },
        }
    },
    "required": ["decisions"],
}


class LearnFromDialogue(TracedUseCase):
    def __init__(
        self,
        model: ModelPort,
        remember,
        recall,
        forget,
        *,
        tracer: TraceRecorder | None = None,
    ) -> None:
        super().__init__(tracer)
        self._model = model
        self._remember = remember
        self._recall = recall
        self._forget = forget

    def __call__(self, question: str, answer: str) -> tuple[MemoryView, ...]:
        if not question.strip():
            return ()

        with self.trace("memory.learn_from_dialogue") as handle:
            facts = self._extract(question, answer)
            if not facts:
                # 보통은 여기서 끝난다. 대화 대부분은 남길 것이 없다.
                return ()

            learned = self._apply(self._decide(facts))
            if handle is not None:
                handle.annotate(facts=len(facts), learned=len(learned))
            return learned

    # -- 1단계 ---------------------------------------------------------------

    def _extract(self, question: str, answer: str) -> list[str]:
        payload = self._ask(
            EXTRACT_SYSTEM,
            f"ZUN: {question}\nJUNVIS: {answer}",
            _FACTS_SCHEMA,
        )
        facts = payload.get("facts") if payload else None
        if not isinstance(facts, list):
            return []
        cleaned = [str(fact).strip() for fact in facts if str(fact).strip()]
        return cleaned[:MAX_FACTS]

    # -- 2단계 ---------------------------------------------------------------

    def _decide(self, facts: list[str]) -> list[dict]:
        existing = self._similar(facts)
        if not existing:
            # 견줄 것이 없으면 두 번째 호출을 아낀다. 전부 새 것이다.
            return [{"event": "ADD", "text": fact} for fact in facts]

        payload = self._ask(
            RECONCILE_SYSTEM,
            "기존 기억: "
            + json.dumps(existing, ensure_ascii=False)
            + "\n새 사실: "
            + json.dumps(facts, ensure_ascii=False),
            _DECISIONS_SCHEMA,
        )
        decisions = payload.get("decisions") if payload else None
        if not isinstance(decisions, list):
            # 조정에 실패하면 그냥 넣는다. 기억을 못 남기는 것보다 낫다.
            return [{"event": "ADD", "text": fact} for fact in facts]
        return [item for item in decisions if isinstance(item, dict)]

    def _similar(self, facts: list[str]) -> list[dict]:
        found: dict[str, str] = {}
        for fact in facts:
            try:
                for hit in self._recall(fact, limit=3):
                    found[hit.id] = hit.text
            except Exception as exc:  # pragma: no cover - 방어적
                logger.debug("회상 실패: %s", exc)
            if len(found) >= MAX_CANDIDATES:
                break
        return [{"id": key, "text": text} for key, text in list(found.items())[:MAX_CANDIDATES]]

    def _apply(self, decisions: list[dict]) -> tuple[MemoryView, ...]:
        learned: list[MemoryView] = []
        for decision in decisions:
            event = str(decision.get("event", "")).upper()
            text = str(decision.get("text", "")).strip()
            if event == "UPDATE":
                self._drop(str(decision.get("id", "")))
            if event in ("ADD", "UPDATE") and text:
                learned.append(
                    self._remember(
                        text, scope=MemoryScope.USER, source="event:conversation"
                    )
                )
        return tuple(learned)

    def _drop(self, memory_id: str) -> None:
        if not memory_id:
            return
        try:
            self._forget(memory_id)
        except Exception as exc:
            # 지우지 못해도 새 사실은 남긴다. 둘 다 있는 편이 없는 것보다 낫다.
            logger.debug("기억을 지우지 못했습니다(%s): %s", memory_id, exc)

    # -- 모델 ---------------------------------------------------------------

    def _ask(self, system: str, prompt: str, schema: dict) -> dict | None:
        try:
            response = self._model.complete(
                ModelRequest(
                    prompt=prompt,
                    system=system,
                    role=ModelRole.FAST,
                    temperature=0.1,  # 사실 추출에 창의성은 해롭다
                    schema=schema,
                )
            )
            return json.loads(response.text)
        except (ModelError, json.JSONDecodeError, ValueError) as exc:
            # 모델이 없으면 자동 기억을 조용히 포기한다. 대화는 이미 끝났고
            # 사용자는 기다리고 있지 않다.
            logger.debug("자동 기억 실패: %s", exc)
            return None
