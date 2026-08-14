"""규칙이 못 알아들은 말에 사람처럼 답한다.

## 왜 조립 루트에 있는가

대화는 `project_brain`·`memory`·`creator`를 **전부** 알아야 한다. feature끼리는
서로를 임포트하지 않으므로(계약 8·10·11번) 여러 Context를 아는 일은 조립 루트의
몫이다. 라우터가 여기 있는 것과 같은 이유다.

## 규칙을 버린 것이 아니다

`docs/05-VOICE.md §3`은 "무엇을 실행할지 LLM에게 묻지 않는다"고 적었고 그 이유는
지금도 유효하다. 음성은 오인식이 잦아서, 실행되는 동작이 모델 판단에 좌우되면
왜 그렇게 됐는지 설명할 수 없다.

그래서 **순서를 지킨다.** 아는 명령은 여전히 규칙이 결정론적으로 실행한다.
모델은 규칙이 아무것도 못 잡았을 때만, 그것도 **말로 답하기 위해서만** 부른다.
브리핑을 실행할지 릴스를 만들지는 여전히 모델이 정하지 않는다.

이 구분이 무너지면 "왜 갑자기 이걸 실행했지?"를 설명할 수 없는 시스템이 된다.

## 근거 없는 말을 하지 않는다

프로젝트·기억·브랜드 성향을 프롬프트에 넣는다. 아무것도 모르는 채로 답하면
그럴듯한 거짓말을 하고, 그것이 개인 비서에서는 가장 나쁜 실패다.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass

from junvis.core.domain.event import DomainEvent
from junvis.core.eventbus.bus import EventBus
from junvis.core.model.ports import ModelError, ModelPort, ModelRequest, ModelRole

logger = logging.getLogger(__name__)

#: 문맥으로 들고 갈 왕복 수. 길면 로컬 소형 모델이 앞을 잊고 헤맨다.
HISTORY_TURNS = 6

#: 프롬프트에 실을 상한. 로컬 모델의 컨텍스트는 좁다.
MAX_PROJECTS = 8
MEMORY_BUDGET = 600

#: 두뇌가 죽었을 때. 조용히 실패하지 않고 무엇이 문제인지 말한다.
#: 무엇을 쓰고 있는지 모르면서 "ollama serve 하세요"라고 하면 틀린 안내다.
OFFLINE_ANSWER = "지금은 대화를 못 합니다. 터미널에서 junvis setup 을 실행해 보세요."

SYSTEM = """너는 JUNVIS, ZUN의 개인 AI 비서다.

ZUN은 개발자이고 인스타그램에서 개발 콘텐츠를 만든다. 주제는 AI, 바이브 코딩,
Claude Code, MCP, 개발 생산성, 새 웹앱, 개발 브이로그, 프로젝트 제작기다.
너의 역할은 CTO이자 콘텐츠 매니저이자 프로젝트 매니저다.

규칙:
- 한국어로, 친근한 반말이 아니라 편한 존댓말로 답한다.
- **말로 듣는 답이다.** 두세 문장으로 짧게. 목록이나 마크다운을 쓰지 않는다.
- 아래 '아는 것'에 없는 사실을 지어내지 않는다. 모르면 모른다고 한다.
- 조언은 ZUN의 장기 목표(개발, 프로젝트, ZUN 브랜드 성장)를 기준으로 고른다.
- ZUN이 원하는 것을 네가 바로 실행할 수 있는 말이 아래에 있으면, 그 말을
  그대로 알려준다. 예: "그건 '오늘 브리핑'이라고 하시면 바로 됩니다."
"""


@dataclass(frozen=True)
class Turn:
    question: str
    answer: str


@dataclass(frozen=True, kw_only=True)
class ConversationHappened(DomainEvent):
    """대화 한 번이 끝났다.

    조립 루트에 있는 이유는 라우터와 같다 — 대화는 여러 Context에 걸쳐 있어
    어느 feature의 사건도 아니다.

    이 이벤트는 **비동기로** 소비된다. 여기 붙는 것(자동 기억)이 모델을
    두 번 더 부르는데, 그걸 동기로 하면 답을 듣고 나서 또 기다리게 된다.
    """

    topic = "conversation.happened"
    question: str
    answer: str


class Conversation:
    def __init__(
        self,
        model: ModelPort,
        *,
        list_projects=None,
        digest=None,
        get_brand_voice=None,
        commands: tuple[str, ...] = (),
        bus: EventBus | None = None,
        history_turns: int = HISTORY_TURNS,
    ) -> None:
        self._model = model
        self._list_projects = list_projects
        self._digest = digest
        self._get_brand_voice = get_brand_voice
        self._commands = commands
        self._bus = bus
        self._history: deque[Turn] = deque(maxlen=history_turns)

    def __call__(self, question: str) -> str:
        return self.answer(question)

    def answer(self, question: str) -> str:
        question = question.strip()
        if not question:
            return ""
        try:
            response = self._model.complete(
                ModelRequest(
                    prompt=self._prompt(question),
                    system=self._system(),
                    role=ModelRole.FAST,  # 말이 끊기면 대화가 아니다
                    temperature=0.6,
                )
            )
        except ModelError as exc:
            # 왜 안 되는지는 어댑터가 안다. 그 말을 그대로 전한다.
            logger.debug("대화 실패: %s", exc)
            return f"{OFFLINE_ANSWER}\n  ({exc})"

        text = _spoken(response.text)
        if not text:
            return OFFLINE_ANSWER
        self._history.append(Turn(question, text))
        if self._bus is not None:
            self._bus.publish(ConversationHappened(question=question, answer=text))
        return text

    def forget(self) -> None:
        self._history.clear()

    # -- 프롬프트 ------------------------------------------------------------

    def _system(self) -> str:
        if not self._commands:
            return SYSTEM
        listed = ", ".join(f'"{command}"' for command in self._commands)
        return f"{SYSTEM}\n네가 바로 실행할 수 있는 말: {listed}\n"

    def _prompt(self, question: str) -> str:
        parts = []
        known = self._known()
        if known:
            parts.append(f"# 아는 것\n{known}")
        if self._history:
            parts.append("# 방금까지의 대화\n" + self._recent())
        parts.append(f"# ZUN의 말\n{question}")
        return "\n\n".join(parts)

    def _known(self) -> str:
        """지금 답에 필요한 사실들. 하나가 실패해도 나머지는 싣는다."""
        blocks = [
            self._safe(self._projects_block, "프로젝트"),
            self._safe(self._memory_block, "기억"),
            self._safe(self._brand_block, "브랜드"),
        ]
        return "\n".join(block for block in blocks if block)

    @staticmethod
    def _safe(build, label: str) -> str:
        try:
            return build()
        except Exception as exc:
            # 문맥 한 조각이 없다고 대화를 못 하게 하지 않는다.
            logger.debug("%s 문맥을 싣지 못했습니다: %s", label, exc)
            return ""

    def _projects_block(self) -> str:
        if self._list_projects is None:
            return ""
        summaries = self._list_projects()
        if not summaries:
            return "등록된 프로젝트가 없다. (junvis scan 으로 등록할 수 있다)"

        lines = ["ZUN의 프로젝트:"]
        for summary in summaries[:MAX_PROJECTS]:
            bits = [summary.name]
            if summary.tech_stack:
                bits.append("/".join(summary.tech_stack[:4]))
            if summary.last_commit:
                bits.append(f"최근 커밋 {summary.last_commit}")
            if summary.dirty:
                bits.append("커밋 안 한 변경 있음")
            lines.append("- " + " · ".join(bits))
        if len(summaries) > MAX_PROJECTS:
            lines.append(f"- 그 외 {len(summaries) - MAX_PROJECTS}개")
        return "\n".join(lines)

    def _memory_block(self) -> str:
        if self._digest is None:
            return ""
        text = self._digest(budget=MEMORY_BUDGET)
        return f"ZUN이 기억시킨 것:\n{text}" if text else ""

    def _brand_block(self) -> str:
        if self._get_brand_voice is None:
            return ""
        voice = self._get_brand_voice()
        tone = getattr(voice, "tone", "")
        return f"ZUN 브랜드 톤: {tone}" if tone else ""

    def _recent(self) -> str:
        return "\n".join(
            f"ZUN: {turn.question}\nJUNVIS: {turn.answer}" for turn in self._history
        )


def _spoken(text: str) -> str:
    """읽어줄 수 있는 형태로 다듬는다.

    모델은 부탁해도 마크다운을 쓴다. 목록 기호와 별표가 그대로 스피커로
    나가면 "별표 별표 브리핑"이 된다.
    """
    lines = []
    for raw in text.strip().splitlines():
        line = raw.strip().lstrip("-*•#").strip()
        line = line.replace("**", "").replace("`", "")
        if line:
            lines.append(line)
    return " ".join(lines).strip()
