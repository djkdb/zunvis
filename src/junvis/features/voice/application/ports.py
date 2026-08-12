"""voice가 필요로 하는 바깥 세계의 계약."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from junvis.core.ports import ClockPort, SystemClock
from junvis.features.voice.domain.model import Utterance

__all__ = [
    "ClockPort",
    "SystemClock",
    "IntentJudgePort",
    "TextToSpeechPort",
    "AudioSourcePort",
    "CommandHandlerPort",
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

    def speak(self, text: str) -> bool:
        """받아들였으면 True. 실패해도 예외를 던지지 않는다."""


class AudioSourcePort(Protocol):
    def listen(self) -> Iterator[Utterance]:
        """발화를 하나씩 내놓는다. 마이크든 표준입력이든 같은 형태다."""


class CommandHandlerPort(Protocol):
    def handle(self, command: str) -> str:
        """명령을 실행하고 사람에게 읽어줄 응답을 돌려준다.

        무엇을 실행할지는 조립 루트의 라우터가 정한다. voice는
        다른 feature를 임포트하지 않는다.
        """
