-- memory Bounded Context가 소유하는 스키마.

CREATE TABLE IF NOT EXISTS memories (
    id               TEXT PRIMARY KEY,
    text             TEXT    NOT NULL,
    -- 중복 판정용 정규화 형태. 표현만 다른 같은 사실을 두 번 넣지 않는다.
    normalized       TEXT    NOT NULL,
    scope            TEXT    NOT NULL DEFAULT 'user',
    subject          TEXT    NOT NULL DEFAULT '',
    tags             TEXT    NOT NULL DEFAULT '[]',
    source           TEXT    NOT NULL DEFAULT 'user',
    pinned           INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL,
    last_recalled_at TEXT,
    recall_count     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_memories_scope      ON memories (scope, subject);
CREATE INDEX IF NOT EXISTS idx_memories_recent     ON memories (pinned DESC, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_norm ON memories (normalized);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_search USING fts5 (
    text,
    tags,
    subject,
    memory_id UNINDEXED,
    tokenize = 'unicode61'
);
