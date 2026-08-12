"""voice가 발행하는 도메인 이벤트."""

from __future__ import annotations

from dataclasses import dataclass

from junvis.core.domain.event import DomainEvent


@dataclass(frozen=True, kw_only=True)
class VoiceCommandReceived(DomainEvent):
    """게이트 1~4를 모두 통과한 발화. 이제 실행 대상이다."""

    topic = "voice.command_received"

    text: str
    raw_text: str
    followed_up: bool = False


@dataclass(frozen=True, kw_only=True)
class VoiceUtteranceIgnored(DomainEvent):
    """무시된 발화. 왜 반응하지 않았는지 나중에 설명할 수 있어야 한다."""

    topic = "voice.utterance_ignored"

    text: str
    reason: str
