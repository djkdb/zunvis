"""project_brain이 **다른 Bounded Context에 공개하는 것**의 전부.

다른 feature는 이 모듈만 임포트한다. 애그리게이트도 저장소도 유스케이스도
공개하지 않는다. 여기에 없는 것에 의존하면 그것은 규칙 위반이다.
"""

from __future__ import annotations

from junvis.features.project_brain.application.dto import ProjectSummary
from junvis.features.project_brain.domain.events import (
    ProjectNoteAdded,
    ProjectRegistered,
    ProjectSnapshotRefreshed,
)

#: 구독 가능한 토픽. `creator`·`brief`가 여기에 붙는다.
TOPIC_REGISTERED = ProjectRegistered.topic
TOPIC_SNAPSHOT_REFRESHED = ProjectSnapshotRefreshed.topic
TOPIC_NOTE_ADDED = ProjectNoteAdded.topic

__all__ = [
    "ProjectSummary",
    "TOPIC_REGISTERED",
    "TOPIC_SNAPSHOT_REFRESHED",
    "TOPIC_NOTE_ADDED",
]
