"""project_brain이 자기 이벤트에 붙이는 구독자.

`creator`·`brief` 같은 다른 Context의 구독자는 그쪽 feature가 스스로 붙인다.
여기 있는 것은 project_brain 자신의 후속 작업뿐이다.
"""

from __future__ import annotations

import logging

from junvis.core.eventbus.bus import Delivery, EventBus, EventEnvelope
from junvis.features.project_brain.application.use_cases.refresh_snapshot import (
    RefreshSnapshot,
)
from junvis.features.project_brain.contracts import TOPIC_REGISTERED

logger = logging.getLogger(__name__)

SUBSCRIBER_REFRESH_AFTER_REGISTER = "project_brain.refresh_after_register"


def register_subscribers(bus: EventBus, refresh: RefreshSnapshot) -> None:
    """등록 직후 스냅샷을 수집한다.

    비동기(ASYNC)인 이유: git 호출과 네트워크가 끼어 있어 등록 응답을
    붙잡아 둘 이유가 없다. 실패하면 Outbox가 재시도하고, 세 번 실패하면
    deadletter로 가서 Daily Brief에 보고된다.
    """

    def refresh_after_register(envelope: EventEnvelope) -> None:
        slug = envelope.payload.get("slug")
        if not slug:
            return
        logger.debug("등록 후 스냅샷 수집: %s", slug)
        refresh(str(slug))

    bus.subscribe(
        TOPIC_REGISTERED,
        refresh_after_register,
        mode=Delivery.ASYNC,
        name=SUBSCRIBER_REFRESH_AFTER_REGISTER,
    )
