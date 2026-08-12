"""발화 하나를 판정하고 필요하면 실행한다."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from junvis.core.eventbus.bus import EventBus
from junvis.core.trace.recorder import TraceRecorder
from junvis.features.voice.application.ports import (
    CommandHandlerPort,
    IntentJudgePort,
    PresencePort,
    TextToSpeechPort,
)
from junvis.features.voice.domain.events import (
    VoiceCommandReceived,
    VoiceUtteranceIgnored,
)
from junvis.features.voice.domain.model import (
    GateDecision,
    ListenerState,
    Presence,
    Utterance,
    WakeWordConfig,
    gate,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceOutcome:
    decision: GateDecision
    command: str = ""
    response: str = ""
    state: ListenerState = ListenerState()

    @property
    def acted(self) -> bool:
        return self.decision.is_act


class HandleUtterance:
    """게이트 1~4를 통과시키고, 통과하면 실행하고 말한다.

    상태를 들고 있지 않고 **받아서 새 상태를 돌려준다.** 덕분에 창이
    언제 열리고 닫히는지를 실제 시계 없이 검증할 수 있다.
    """

    def __init__(
        self,
        judge: IntentJudgePort,
        handler: CommandHandlerPort,
        tts: TextToSpeechPort,
        bus: EventBus,
        *,
        config: WakeWordConfig | None = None,
        tracer: TraceRecorder | None = None,
        presence: PresencePort | None = None,
    ) -> None:
        self._judge = judge
        self._handler = handler
        self._tts = tts
        self._bus = bus
        self._config = config or WakeWordConfig()
        self._tracer = tracer
        self._presence = presence

    def __call__(self, utterance: Utterance, state: ListenerState) -> VoiceOutcome:
        decision = gate(utterance, self._config, state)
        if not decision.is_act:
            return self._ignore(utterance, decision, state)

        followed_up = not self._config.contains_wake_word(utterance)
        command = self._config.strip_wake_word(utterance)
        if not command:
            # "자비스"만 부른 경우. 명령이 아니라 부름이다.
            return self._respond(utterance, command="", answer="네?", state=state)

        if not self._judged_as_command(command):
            return self._ignore(utterance, GateDecision.IGNORE_NOT_A_COMMAND, state)

        self._bus.publish(
            VoiceCommandReceived(
                text=command, raw_text=utterance.text, followed_up=followed_up
            )
        )
        return self._execute(utterance, command, state)

    # -- 내부 ---------------------------------------------------------------

    def _judged_as_command(self, command: str) -> bool:
        """판정이 실패하면 통과시킨다.

        모델이 죽었다고 사용자의 말을 전부 무시하는 것보다, 실행하고
        틀리는 편이 낫다. 실행 자체는 PolicyEngine이 다시 막는다.
        """
        try:
            return self._judge.is_command(command)
        except Exception as exc:
            logger.debug("Intent Judge 실패, 통과시킴: %s", exc)
            return True

    def _show(self, presence: Presence, text: str = "") -> None:
        """장식이 명령을 죽이지 않게 한다. 화면은 언제든 없을 수 있다."""
        if self._presence is None:
            return
        try:
            self._presence.show(presence, text)
        except Exception as exc:  # pragma: no cover - 방어적
            logger.debug("상태 표시 실패: %s", exc)

    def _execute(
        self, utterance: Utterance, command: str, state: ListenerState
    ) -> VoiceOutcome:
        self._show(Presence.THINKING, command)
        if self._tracer is None:
            answer = self._run(command)
        else:
            with self._tracer.record("voice.command", command=command) as handle:
                answer = self._run(command)
                handle.annotate(response_length=len(answer))
        return self._respond(utterance, command=command, answer=answer, state=state)

    def _run(self, command: str) -> str:
        try:
            return self._handler.handle(command)
        except Exception as exc:
            logger.debug("명령 실행 실패: %s", exc)
            return "처리하지 못했습니다."

    def _respond(
        self, utterance: Utterance, *, command: str, answer: str, state: ListenerState
    ) -> VoiceOutcome:
        self._show(Presence.SPEAKING, answer)
        self._tts.speak(answer)
        # 말한 내용을 기억해 에코를 막고, 후속 발화 창을 연다.
        next_state = state.with_spoken(
            answer, utterance.heard_at, self._config.follow_up_window
        )
        # 말이 끝나도 창이 열려 있다. 화면도 그대로 깨어 있어야 사용자가
        # 호출어 없이 이어 말해도 된다는 것을 안다.
        self._show(Presence.AWAKE)
        return VoiceOutcome(GateDecision.ACT, command, answer, next_state)

    def _ignore(
        self, utterance: Utterance, decision: GateDecision, state: ListenerState
    ) -> VoiceOutcome:
        self._bus.publish(
            VoiceUtteranceIgnored(text=utterance.text, reason=decision.value)
        )
        # 창이 열려 있는 동안의 잡음까지 화면을 재우면, 사용자는 아직
        # 이어 말할 수 있는데도 다시 이름을 부르게 된다.
        if not state.is_awake(utterance.heard_at):
            self._show(Presence.ASLEEP)
        return VoiceOutcome(decision, state=state)
