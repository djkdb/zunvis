-- project_brain Bounded Context가 소유하는 스키마.

CREATE TABLE IF NOT EXISTS projects (
    id                TEXT PRIMARY KEY,
    slug              TEXT NOT NULL UNIQUE,
    name              TEXT NOT NULL,
    local_path        TEXT,
    repo_host         TEXT,
    repo_owner        TEXT,
    repo_name         TEXT,
    purpose           TEXT NOT NULL DEFAULT '',
    architecture_note TEXT NOT NULL DEFAULT '',
    tech_stack        TEXT NOT NULL DEFAULT '[]',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_updated_at ON projects (updated_at DESC);

-- 스냅샷은 프로젝트당 최신 1건만 유지한다.
-- 이력이 필요해지면 별도 테이블로 분리하되, 지금 필요하지 않은 복잡도는 두지 않는다.
CREATE TABLE IF NOT EXISTS project_snapshots (
    project_id      TEXT PRIMARY KEY REFERENCES projects (id) ON DELETE CASCADE,
    branch          TEXT,
    dirty           INTEGER NOT NULL DEFAULT 0,
    readme_excerpt  TEXT    NOT NULL DEFAULT '',
    recent_commits  TEXT    NOT NULL DEFAULT '[]',
    open_issues     TEXT    NOT NULL DEFAULT '[]',
    detected_stack  TEXT    NOT NULL DEFAULT '[]',
    discovered_todos TEXT   NOT NULL DEFAULT '[]',
    captured_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS project_todos (
    id         TEXT PRIMARY KEY,
    project_id TEXT    NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    text       TEXT    NOT NULL,
    source     TEXT    NOT NULL DEFAULT 'user',
    done       INTEGER NOT NULL DEFAULT 0,
    position   INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_todos_project ON project_todos (project_id, position);

CREATE TABLE IF NOT EXISTS project_notes (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    text       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notes_project ON project_notes (project_id, created_at);

-- 전문 검색. 저장소가 프로젝트 저장 시마다 이 행을 다시 만든다.
-- 외부 콘텐츠 테이블(external content) 대신 단순 복제를 쓴다:
-- 개인 규모에서 동기화 버그를 감수할 이유가 없다.
CREATE VIRTUAL TABLE IF NOT EXISTS project_search USING fts5 (
    slug,
    name,
    purpose,
    architecture_note,
    tech_stack,
    readme,
    notes,
    project_id UNINDEXED,
    tokenize = 'unicode61'
);
