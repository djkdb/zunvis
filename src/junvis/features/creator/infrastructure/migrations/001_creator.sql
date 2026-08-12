-- creator Bounded Context가 소유하는 스키마.

CREATE TABLE IF NOT EXISTS content_ideas (
    id                  TEXT PRIMARY KEY,
    subject             TEXT NOT NULL,
    content_format      TEXT NOT NULL DEFAULT 'reels',
    status              TEXT NOT NULL DEFAULT 'suggested',
    source_project_slug TEXT,
    script              TEXT,              -- ReelScript를 JSON으로. 통째로 교체되는 값이다
    published_url       TEXT,
    performance_note    TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    published_at        TEXT
);

CREATE INDEX IF NOT EXISTS idx_content_updated ON content_ideas (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_content_status  ON content_ideas (status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_content_project ON content_ideas (source_project_slug);

-- 브랜드 성향은 한 벌뿐이다. id를 1로 고정해 행이 늘어날 수 없게 한다.
CREATE TABLE IF NOT EXISTS brand_voice (
    id             INTEGER PRIMARY KEY CHECK (id = 1),
    topics         TEXT NOT NULL DEFAULT '[]',
    tone           TEXT NOT NULL DEFAULT '',
    audience       TEXT NOT NULL DEFAULT '',
    banned_phrases TEXT NOT NULL DEFAULT '[]',
    updated_at     TEXT NOT NULL
);
