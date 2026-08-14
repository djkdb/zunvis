"""voice가 필요로 하는 바깥 세계의 계약."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from junvis.core.ports import ClockPort, SystemClock
from junvis.features.voice.domain.model import Presence, Utterance

__all__ = [
    "ClockPort",
    "SystemClock",
    "IntentJudgePort",
    "TextToSpeechPort",
    "AudioSourcePort",
    "CommandHandlerPort",
    "PresencePort",
]


class IntentJudgePort(Protocol):
    """게이트 4 — "이게 진짜 나에게 한 말인가?"

    호출어가 들렸다고 전부 명령은 아니다. 옆 사람과의 대화에 이름이
    섞였을 수도 있고, STT가 잡음을 문장으로 만들어냈을 수도 있다.
    작은 로컬 모델로 판정한다.
    """

    def is_command(self, text: str) -> bool: ...


class TextToSpeechPort(Protocol):
    #: 실제로 소리가 나는 구현인가. False면 받아들이기만 하고 들리지는 않는다.
    audible: bool
    #: 지금 말하는 중인가. 게이트가 이걸 보고 규칙을 바꾼다.
    speaking: bool

    def speak(self, text: str) -> bool:
        """말하기를 **시작한다.** 받아들였으면 True.

        끝날 때까지 기다리지 않는다. 기다리면 그동안 마이크를 못 읽어서
        말을 끊을 수도, 끼어들 수도 없다. 실패해도 예외를 던지지 않는다.
        """

    def stop(self) -> None:
        """말하는 중이면 끊는다."""

    def wait(self) -> None:
        """끝날 때까지 기다린다. 듣기 루프는 부르지 않는다."""


class AudioSourcePort(Protocol):
    def listen(self) -> Iterator[Utterance]:
        """발화를 하나씩 내놓는다. 마이크든 표준입력이든 같은 형태다."""


class CommandHandlerPort(Protocol):
    def handle(self, command: str) -> str:
        """명령을 실행하고 사람에게 읽어줄 응답을 돌려준다.

        무엇을 실행할지는 조립 루트의 라우터가 정한다. voice는
        다른 feature를 임포트하지 않는다.
        """

    def examples(self) -> tuple[str, ...]:
        """지금 말할 수 있는 것들.

        음성 인터페이스에는 메뉴가 없다. "네?" 하고 조용해지면 사용자는
        무엇을 말해야 할지 모른 채로 남는다. 라우터만이 무엇을 알아듣는지
        알고 있으므로, 여기서 물어본다.
        """


class PresencePort(Protocol):
    """지금 상태를 사람에게 보여준다.

    **보여주기만 한다.** 여기서 무엇을 돌려받지 않으므로 판단에 영향을
    주지 않고, 화면이 꺼져 있어도 파이프라인은 그대로 돈다. 실패해도
    예외를 던지지 않는다 — 장식 때문에 명령이 죽으면 안 된다.
    """

    def show(self, presence: Presence, text: str = "") -> None: ...
