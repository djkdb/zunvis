-- core 스키마: Event Bus의 Outbox/Deadletter와 Trace.
-- feature 테이블은 각 feature의 마이그레이션이 소유한다.

CREATE TABLE IF NOT EXISTS outbox (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    topic           TEXT    NOT NULL,
    handler         TEXT    NOT NULL,
    payload         TEXT    NOT NULL,
    occurred_at     TEXT    NOT NULL,
    next_attempt_at TEXT    NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    processed_at    TEXT,
    last_error      TEXT
);

-- 미처리 항목만 인덱싱한다. 처리 완료 행이 쌓여도 조회 비용이 늘지 않는다.
CREATE INDEX IF NOT EXISTS idx_outbox_pending
    ON outbox (next_attempt_at) WHERE processed_at IS NULL;

CREATE TABLE IF NOT EXISTS deadletter (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    topic       TEXT NOT NULL,
    handler     TEXT NOT NULL,
    payload     TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    failed_at   TEXT NOT NULL,
    attempts    INTEGER NOT NULL,
    last_error  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS traces (
    id            TEXT PRIMARY KEY,
    request       TEXT    NOT NULL,
    plan          TEXT,
    tool_calls    TEXT    NOT NULL DEFAULT '[]',
    model         TEXT,
    tokens        INTEGER NOT NULL DEFAULT 0,
    latency_ms    INTEGER NOT NULL DEFAULT 0,
    cost          REAL    NOT NULL DEFAULT 0.0,
    outcome       TEXT    NOT NULL,
    user_feedback TEXT,
    context       TEXT    NOT NULL DEFAULT '{}',
    occurred_at   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_traces_occurred_at ON traces (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_traces_outcome     ON traces (outcome);
