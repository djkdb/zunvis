"""SQLite 접근의 단일 창구.

설계 결정(docs/02-ARCHITECTURE.md §0): 저장소는 SQLite(WAL) + FTS5.
검소하고, 백업이 파일 복사 한 번이며, macOS에서 추가 데몬이 필요 없다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from junvis.core.domain.event import utcnow

MEMORY = ":memory:"


class Database:
    """연결 1개를 소유하고 트랜잭션 경계를 제공한다.

    JUNVIS는 단일 프로세스 개인용이므로 커넥션 풀을 두지 않는다.
    동시성이 필요해지면 WAL 덕분에 읽기 커넥션만 추가하면 된다.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = path if path == MEMORY else Path(path)
        self._conn: sqlite3.Connection | None = None
        self._depth = 0

    @property
    def path(self) -> Path | str:
        return self._path

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = self._connect()
        return self._conn

    def _connect(self) -> sqlite3.Connection:
        if self._path != MEMORY:
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            self._path if self._path == MEMORY else str(self._path),
            isolation_level=None,  # 트랜잭션을 우리가 명시적으로 연다
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        if self._path != MEMORY:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -- 트랜잭션 -----------------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """재진입 가능한 트랜잭션.

        유스케이스가 저장 + 이벤트 발행을 한 경계 안에서 처리할 수 있어야
        동기 구독자 실패 시 함께 롤백된다(설계 §3 "전달 모드").
        """
        conn = self.connection
        outermost = self._depth == 0
        if outermost:
            conn.execute("BEGIN IMMEDIATE")
        self._depth += 1
        try:
            yield conn
        except BaseException:
            self._depth -= 1
            if outermost:
                conn.execute("ROLLBACK")
            raise
        else:
            self._depth -= 1
            if outermost:
                conn.execute("COMMIT")

    # -- 질의 --------------------------------------------------------------

    def execute(self, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> sqlite3.Cursor:
        return self.connection.execute(sql, params)

    def executemany(self, sql: str, rows: Sequence[Sequence[Any]]) -> sqlite3.Cursor:
        return self.connection.executemany(sql, rows)

    def query(self, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> list[sqlite3.Row]:
        return list(self.connection.execute(sql, params).fetchall())

    def query_one(
        self, sql: str, params: Sequence[Any] | dict[str, Any] = ()
    ) -> sqlite3.Row | None:
        return self.connection.execute(sql, params).fetchone()

    # -- 마이그레이션 -------------------------------------------------------

    def migrate(self, *directories: Path) -> list[str]:
        """core와 각 feature가 자기 스키마를 소유한다.

        feature 테이블을 core 마이그레이션에 몰아넣으면 Bounded Context
        경계가 스키마에서부터 무너진다. 그래서 디렉터리를 여러 개 받는다.
        적용된 이름은 `<디렉터리명>/<파일명>`으로 기록해 충돌을 피한다.

        주의: sqlite3의 `executescript()`는 실행 전에 대기 중인 트랜잭션을
        암묵적으로 커밋한다. 그래서 스크립트와 기록을 한 트랜잭션으로 묶을
        수 없다. 대신 **모든 마이그레이션을 멱등하게**(IF NOT EXISTS) 쓰는
        것을 규칙으로 삼는다. 중간에 죽어도 다시 적용하면 그만이다.
        """
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name       TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        applied = {row["name"] for row in self.query("SELECT name FROM schema_migrations")}
        newly: list[str] = []
        for directory in directories:
            for sql_file in sorted(Path(directory).glob("*.sql")):
                name = f"{Path(directory).name}/{sql_file.name}"
                if name in applied:
                    continue
                self.connection.executescript(sql_file.read_text(encoding="utf-8"))
                self.connection.execute(
                    "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
                    (name, utcnow().isoformat()),
                )
                newly.append(name)
        return newly
