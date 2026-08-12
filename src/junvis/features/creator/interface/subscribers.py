"""creator가 다른 Context의 이벤트에 붙는 곳.

여기가 설계 §3에서 약속한 것이 실제로 지켜지는 지점이다:
project_brain은 creator를 모르고, creator는 project_brain의
**contracts(발행된 토픽)만** 안다.
"""

from __future__ import annotations

import logging

from junvis.core.eventbus.bus import Delivery, EventBus, EventEnvelope
from junvis.features.creator.application.use_cases.suggest import SuggestForProject

# 다른 feature에서 임포트가 허용되는 유일한 모듈이 contracts다.
from junvis.features.project_brain.contracts import TOPIC_REGISTERED

logger = logging.getLogger(__name__)

SUBSCRIBER_SUGGEST_ON_NEW_PROJECT = "creator.suggest_on_new_project"


def register_subscribers(bus: EventBus, suggest: SuggestForProject) -> None:
    """새 프로젝트가 등록되면 릴스를 제안한다.

    비동기인 이유: 제안 생성이 프로젝트 등록을 붙잡아 둘 이유가 없고,
    실패해도 등록 자체는 성공해야 하기 때문이다.
    """

    def suggest_on_new_project(envelope: EventEnvelope) -> None:
        slug = envelope.payload.get("slug")
        name = envelope.payload.get("name") or slug
        if not slug:
            return
        logger.debug("새 프로젝트 감지, 콘텐츠 제안: %s", slug)
        suggest(str(slug), str(name))

    bus.subscribe(
        TOPIC_REGISTERED,
        suggest_on_new_project,
        mode=Delivery.ASYNC,
        name=SUBSCRIBER_SUGGEST_ON_NEW_PROJECT,
    )
