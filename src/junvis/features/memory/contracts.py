"""memory가 다른 Bounded Context에 공개하는 것의 전부."""

from __future__ import annotations

from junvis.features.memory.application.dto import MemoryView
from junvis.features.memory.domain.events import MemoryForgotten, MemoryRemembered

TOPIC_REMEMBERED = MemoryRemembered.topic
TOPIC_FORGOTTEN = MemoryForgotten.topic

__all__ = ["MemoryView", "TOPIC_REMEMBERED", "TOPIC_FORGOTTEN"]
