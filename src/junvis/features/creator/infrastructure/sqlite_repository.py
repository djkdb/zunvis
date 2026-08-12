"""creator 저장소의 SQLite 구현."""

from __future__ import annotations

import json
from datetime import datetime

from junvis.core.persistence.database import Database
from junvis.features.creator.domain.model import ContentIdea, ReelScript, Scene
from junvis.features.creator.domain.repository import BrandVoiceStore, ContentRepository
from junvis.features.creator.domain.value_objects import (
    BrandVoice,
    ContentFormat,
    ContentStatus,
    Hashtag,
    IdeaId,
)


def _script_to_json(script: ReelScript | None) -> str | None:
    if script is None:
        return None
    return json.dumps(
        {
            "hook": script.hook,
            "scenes": [
                {
                    "order": s.order,
                    "visual": s.visual,
                    "narration": s.narration,
                    "duration_seconds": s.duration_seconds,
                }
                for s in script.scenes
            ],
            "caption": script.caption,
            "hashtags": [tag.value for tag in script.hashtags],
            "broll": list(script.broll),
            "thumbnail_text": script.thumbnail_text,
            "comment_bait": script.comment_bait,
        },
        ensure_ascii=False,
    )


def _script_from_json(raw: str | None) -> ReelScript | None:
    if not raw:
        return None
    data = json.loads(raw)
    return ReelScript(
        hook=data["hook"],
        scenes=tuple(Scene(**scene) for scene in data["scenes"]),
        caption=data["caption"],
        hashtags=tuple(Hashtag(value) for value in data.get("hashtags", [])),
        broll=tuple(data.get("broll", [])),
        thumbnail_text=data.get("thumbnail_text", ""),
        comment_bait=data.get("comment_bait", ""),
    )


class SqliteContentRepository(ContentRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    def save(self, idea: ContentIdea) -> None:
        self._db.execute(
            """
            INSERT INTO content_ideas
                (id, subject, content_format, status, source_project_slug, script,
                 published_url, performance_note, created_at, updated_at, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                subject = excluded.subject,
                content_format = excluded.content_format,
                status = excluded.status,
                source_project_slug = excluded.source_project_slug,
                script = excluded.script,
                published_url = excluded.published_url,
                performance_note = excluded.performance_note,
                updated_at = excluded.updated_at,
                published_at = excluded.published_at
            """,
            (
                idea.id.value,
                idea.subject,
                idea.content_format.value,
                idea.status.value,
                idea.source_project_slug,
                _script_to_json(idea.script),
                idea.published_url,
                idea.performance_note,
                idea.created_at.isoformat(),
                idea.updated_at.isoformat(),
                idea.published_at.isoformat() if idea.published_at else None,
            ),
        )

    def get(self, idea_id: IdeaId) -> ContentIdea | None:
        row = self._db.query_one("SELECT * FROM content_ideas WHERE id = ?", (idea_id.value,))
        return self._hydrate(row) if row else None

    def list(
        self, *, status: ContentStatus | None = None, limit: int = 50
    ) -> list[ContentIdea]:
        if status is None:
            rows = self._db.query(
                "SELECT * FROM content_ideas ORDER BY updated_at DESC LIMIT ?", (limit,)
            )
        else:
            rows = self._db.query(
                """
                SELECT * FROM content_ideas
                WHERE status = ? ORDER BY updated_at DESC LIMIT ?
                """,
                (status.value, limit),
            )
        return [self._hydrate(row) for row in rows]

    def find_by_project(self, slug: str) -> list[ContentIdea]:
        rows = self._db.query(
            "SELECT * FROM content_ideas WHERE source_project_slug = ? ORDER BY created_at",
            (slug,),
        )
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row) -> ContentIdea:
        return ContentIdea(
            id=IdeaId(row["id"]),
            subject=row["subject"],
            content_format=ContentFormat(row["content_format"]),
            status=ContentStatus(row["status"]),
            source_project_slug=row["source_project_slug"],
            script=_script_from_json(row["script"]),
            published_url=row["published_url"],
            performance_note=row["performance_note"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            published_at=(
                datetime.fromisoformat(row["published_at"]) if row["published_at"] else None
            ),
        )


class SqliteBrandVoiceStore(BrandVoiceStore):
    def __init__(self, db: Database) -> None:
        self._db = db

    def get(self) -> BrandVoice:
        row = self._db.query_one("SELECT * FROM brand_voice WHERE id = 1")
        if row is None:
            # 아직 저장한 적이 없으면 브리프의 ZUN 기본값으로 시작한다.
            return BrandVoice.default_zun()
        return BrandVoice(
            topics=tuple(json.loads(row["topics"])),
            tone=row["tone"],
            audience=row["audience"],
            banned_phrases=tuple(json.loads(row["banned_phrases"])),
        )

    def save(self, voice: BrandVoice) -> None:
        from junvis.core.domain.event import utcnow

        self._db.execute(
            """
            INSERT INTO brand_voice (id, topics, tone, audience, banned_phrases, updated_at)
            VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                topics = excluded.topics,
                tone = excluded.tone,
                audience = excluded.audience,
                banned_phrases = excluded.banned_phrases,
                updated_at = excluded.updated_at
            """,
            (
                json.dumps(list(voice.topics), ensure_ascii=False),
                voice.tone,
                voice.audience,
                json.dumps(list(voice.banned_phrases), ensure_ascii=False),
                utcnow().isoformat(),
            ),
        )
