"""다른 Context에서 일어난 사건을 기억으로 옮긴다.

`memory` 안이 아니라 조립 루트에 있는 이유: 이 코드는 `creator`와
`project_brain`의 토픽을 알아야 하는데, feature끼리는 서로를 임포트하지
않기 때문이다(계약 11번). 두 Context를 아는 것은 조립 루트의 일이다.

**무엇을 기억하지 않을지가 더 중요하다.** `voice.command_received`는
남기지 않는다 — 말한 것을 전부 저장하면 잡음이 신호를 덮고, digest가
그것들로 채워진다. 사용자가 명시적으로 남긴 것과 **실제로 일어난 사건**만
기억한다(docs/06-MEMORY.md §2).

대화(`conversation.happened`)는 예외인데, 통째로 저장하지 않기 때문이다.
모델이 "오래 갈 사실"만 뽑고 잡담에는 빈 목록을 돌려준다(docs/10 §3).
그 판정이 있어야 위의 원칙과 어긋나지 않는다.
"""

from __future__ import annotations

import logging

from junvis.core.eventbus.bus import Delivery, EventBus, EventEnvelope
from junvis.features.creator.contracts import TOPIC_PUBLISHED
from junvis.features.memory.application.use_cases.remember import RememberFact
from junvis.features.memory.domain.model import MemoryScope
from junvis.features.project_brain.contracts import TOPIC_REGISTERED

#: 조립 루트가 발행한다. feature의 사건이 아니라 여러 Context에 걸친 일이다.
TOPIC_CONVERSATION = "conversation.happened"

logger = logging.getLogger(__name__)

SUBSCRIBER_LEARN_PUBLISHED = "memory.learn_from_published_content"
SUBSCRIBER_LEARN_PROJECT = "memory.learn_from_new_project"
SUBSCRIBER_LEARN_DIALOGUE = "memory.learn_from_dialogue"


def register_learning(bus: EventBus, remember: RememberFact, learn=None) -> None:
    def learn_from_published(envelope: EventEnvelope) -> None:
        subject = envelope.payload.get("subject")
        if not subject:
            return
        remember(
            f"「{subject}」 콘텐츠를 발행했다",
            scope=MemoryScope.CONTENT,
            tags=("발행",),
            source=f"event:{envelope.topic}",
        )

    def learn_from_new_project(envelope: EventEnvelope) -> None:
        name = envelope.payload.get("name")
        slug = envelope.payload.get("slug")
        if not name or not slug:
            return
        remember(
            f"「{name}」 프로젝트를 시작했다",
            scope=MemoryScope.PROJECT,
            subject=str(slug),
            tags=("시작",),
            source=f"event:{envelope.topic}",
        )

    if learn is not None:
        def learn_from_dialogue(envelope: EventEnvelope) -> None:
            learn(
                str(envelope.payload.get("question", "")),
                str(envelope.payload.get("answer", "")),
            )

        bus.subscribe(
            TOPIC_CONVERSATION,
            learn_from_dialogue,
            mode=Delivery.ASYNC,
            name=SUBSCRIBER_LEARN_DIALOGUE,
        )

    bus.subscribe(
        TOPIC_PUBLISHED,
        learn_from_published,
        mode=Delivery.ASYNC,
        name=SUBSCRIBER_LEARN_PUBLISHED,
    )
    bus.subscribe(
        TOPIC_REGISTERED,
        learn_from_new_project,
        mode=Delivery.ASYNC,
        name=SUBSCRIBER_LEARN_PROJECT,
    )
