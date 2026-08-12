-- 외부 MCP 서버의 도구 카탈로그 캐시.
-- 이것이 있어야 서버를 띄우지 않고도 어떤 도구가 있는지 답할 수 있다.

CREATE TABLE IF NOT EXISTS mcp_tools (
    server_id     TEXT NOT NULL,
    name          TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    input_schema  TEXT NOT NULL DEFAULT '{}',
    discovered_at TEXT NOT NULL,
    PRIMARY KEY (server_id, name)
);

CREATE INDEX IF NOT EXISTS idx_mcp_tools_server ON mcp_tools (server_id);
