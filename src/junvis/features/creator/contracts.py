"""creator가 다른 Bounded Context에 공개하는 것의 전부."""

from __future__ import annotations

from junvis.features.creator.application.dto import ContentSummary
from junvis.features.creator.domain.events import (
    ContentDismissed,
    ContentDrafted,
    ContentPublished,
    ContentSuggested,
)

TOPIC_SUGGESTED = ContentSuggested.topic
TOPIC_DRAFTED = ContentDrafted.topic
TOPIC_PUBLISHED = ContentPublished.topic
TOPIC_DISMISSED = ContentDismissed.topic

__all__ = [
    "ContentSummary",
    "TOPIC_SUGGESTED",
    "TOPIC_DRAFTED",
    "TOPIC_PUBLISHED",
    "TOPIC_DISMISSED",
]
