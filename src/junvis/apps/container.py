"""조립 루트(Composition Root).

여기가 **유일하게** 구체 구현을 아는 곳이다. 도메인·유스케이스는
SQLite도 git도 GitHub도 모르고, 이 파일이 그것들을 Port 자리에 끼워 넣는다.
의존성 주입 프레임워크는 쓰지 않는다 — 개인 규모에서 명시적 조립이 더 읽기 쉽다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from junvis.core.eventbus.bus import DrainReport, EventBus
from junvis.core.eventbus.outbox import SqliteOutbox
from junvis.core.persistence import CORE_MIGRATIONS, Database
from junvis.core.policy.engine import ConfirmPort, PolicyEngine
from junvis.core.trace.recorder import TraceRecorder
from junvis.core.trace.store import SqliteTraceStore
from junvis.features.project_brain.application.use_cases.load_context import (
    LoadProjectContext,
)
from junvis.features.project_brain.application.use_cases.queries import (
    ListProjects,
    SearchProjects,
)
from junvis.features.project_brain.application.use_cases.refresh_snapshot import (
    RefreshSnapshot,
)
from junvis.features.project_brain.application.use_cases.register_project import (
    RegisterProject,
)
from junvis.features.project_brain.application.use_cases.remember_note import RememberNote
from junvis.features.project_brain.infrastructure import PROJECT_BRAIN_MIGRATIONS
from junvis.features.project_brain.infrastructure.git_adapter import GitAdapter
from junvis.features.project_brain.infrastructure.github_adapter import GitHubIssueAdapter
from junvis.features.project_brain.infrastructure.project_scanner import ProjectScanner
from junvis.features.project_brain.infrastructure.sqlite_repository import (
    SqliteProjectRepository,
)
from junvis.features.project_brain.interface.subscribers import register_subscribers

HOME_ENV = "JUNVIS_HOME"
DEFAULT_HOME = Path.home() / ".junvis"
DB_FILENAME = "junvis.db"


def resolve_home(home: Path | str | None = None) -> Path:
    if home is not None:
        return Path(home).expanduser()
    env = os.environ.get(HOME_ENV)
    return Path(env).expanduser() if env else DEFAULT_HOME


@dataclass
class Junvis:
    """조립된 JUNVIS 인스턴스."""

    home: Path
    db: Database
    bus: EventBus
    outbox: SqliteOutbox
    policy: PolicyEngine
    tracer: TraceRecorder
    repository: SqliteProjectRepository
    register: RegisterProject
    refresh: RefreshSnapshot
    load_context: LoadProjectContext
    search: SearchProjects
    list_projects: ListProjects
    remember: RememberNote

    def drain(self, limit: int = 100) -> DrainReport:
        """미처리 비동기 이벤트를 소비한다. 진입점이 작업 후 호출한다."""
        return self.bus.drain(limit)

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> Junvis:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def build(
    home: Path | str | None = None,
    *,
    confirmer: ConfirmPort | None = None,
    offline: bool = False,
) -> Junvis:
    """모든 부품을 조립한다.

    `offline=True`면 GitHub 어댑터를 끼우지 않는다. 네트워크가 없는 상태를
    예외가 아니라 정상 모드 중 하나로 다룬다.
    """
    root = resolve_home(home)
    root.mkdir(parents=True, exist_ok=True)

    db = Database(root / DB_FILENAME)
    db.migrate(CORE_MIGRATIONS, PROJECT_BRAIN_MIGRATIONS)

    outbox = SqliteOutbox(db)
    bus = EventBus(outbox)
    policy = PolicyEngine(confirmer=confirmer)
    tracer = TraceRecorder(SqliteTraceStore(db), bus)

    repository = SqliteProjectRepository(db)
    git = GitAdapter()
    scanner = ProjectScanner()
    issues = None if offline else GitHubIssueAdapter()

    # Database.transaction은 "호출하면 컨텍스트 매니저를 주는 것"이므로
    # 그대로 UnitOfWorkPort를 만족한다. 별도 래퍼 클래스를 만들 이유가 없다.
    unit_of_work = db.transaction

    refresh = RefreshSnapshot(
        repository, bus, unit_of_work, git, scanner,
        issues=issues, policy=policy, tracer=tracer,
    )
    container = Junvis(
        home=root,
        db=db,
        bus=bus,
        outbox=outbox,
        policy=policy,
        tracer=tracer,
        repository=repository,
        register=RegisterProject(
            repository, bus, unit_of_work, policy=policy, git=git, tracer=tracer
        ),
        refresh=refresh,
        load_context=LoadProjectContext(repository, policy=policy, tracer=tracer),
        search=SearchProjects(repository, policy=policy, tracer=tracer),
        list_projects=ListProjects(repository, policy=policy, tracer=tracer),
        remember=RememberNote(
            repository, bus, unit_of_work, policy=policy, tracer=tracer
        ),
    )

    register_subscribers(bus, refresh)
    return container
