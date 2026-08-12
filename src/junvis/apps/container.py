"""조립 루트(Composition Root).

여기가 **유일하게** 구체 구현을 아는 곳이다. 도메인·유스케이스는
SQLite도 git도 Ollama도 모르고, 이 파일이 그것들을 Port 자리에 끼워 넣는다.
의존성 주입 프레임워크는 쓰지 않는다 — 개인 규모에서 명시적 조립이 더 읽기 쉽다.

유스케이스는 feature별로 묶는다. feature가 늘어날 때 컨테이너가
평평한 필드 목록으로 부풀지 않게 하기 위해서다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from junvis.apps.adapters import (
    BrandInterestsAdapter,
    ContentDigestAdapter,
    ProjectContextAdapter,
    ProjectDigestAdapter,
)
from junvis.core.eventbus.bus import DrainReport, EventBus
from junvis.core.eventbus.outbox import SqliteOutbox
from junvis.core.model.ollama import OllamaAdapter
from junvis.core.model.ports import ModelPort
from junvis.core.persistence import CORE_MIGRATIONS, Database
from junvis.core.policy.engine import ConfirmPort, PolicyEngine
from junvis.core.trace.recorder import TraceRecorder
from junvis.core.trace.store import SqliteTraceStore
from junvis.features.brief.application.use_cases.compose_briefing import ComposeBriefing
from junvis.features.brief.infrastructure.calendar_adapter import MacCalendarAdapter
from junvis.features.brief.infrastructure.habit_analyzer import TraceHabitAnalyzer
from junvis.features.brief.infrastructure.news_adapter import HackerNewsAdapter
from junvis.features.creator.application.use_cases.generate_content import GenerateContent
from junvis.features.creator.application.use_cases.lifecycle import (
    DismissContent,
    MarkPublished,
    RecordPerformance,
    UpdateBrandVoice,
)
from junvis.features.creator.application.use_cases.queries import (
    GetBrandVoice,
    GetContent,
    ListContent,
)
from junvis.features.creator.application.use_cases.suggest import SuggestForProject
from junvis.features.creator.infrastructure import CREATOR_MIGRATIONS
from junvis.features.creator.infrastructure.script_generator import LlmScriptGenerator
from junvis.features.creator.infrastructure.sqlite_repository import (
    SqliteBrandVoiceStore,
    SqliteContentRepository,
)
from junvis.features.creator.interface.subscribers import (
    register_subscribers as register_creator_subscribers,
)
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
from junvis.features.project_brain.interface.subscribers import (
    register_subscribers as register_project_subscribers,
)

HOME_ENV = "JUNVIS_HOME"
DEFAULT_HOME = Path.home() / ".junvis"
DB_FILENAME = "junvis.db"


def resolve_home(home: Path | str | None = None) -> Path:
    if home is not None:
        return Path(home).expanduser()
    env = os.environ.get(HOME_ENV)
    return Path(env).expanduser() if env else DEFAULT_HOME


@dataclass
class ProjectBrain:
    """project_brain의 유스케이스 묶음."""

    register: RegisterProject
    refresh: RefreshSnapshot
    load_context: LoadProjectContext
    search: SearchProjects
    list_all: ListProjects
    remember: RememberNote


@dataclass
class Creator:
    """creator의 유스케이스 묶음."""

    generate: GenerateContent
    list_all: ListContent
    get: GetContent
    dismiss: DismissContent
    mark_published: MarkPublished
    record_performance: RecordPerformance
    get_brand_voice: GetBrandVoice
    update_brand_voice: UpdateBrandVoice
    suggest: SuggestForProject


@dataclass
class Brief:
    """brief의 유스케이스 묶음."""

    compose: ComposeBriefing


@dataclass
class Junvis:
    """조립된 JUNVIS 인스턴스."""

    home: Path
    db: Database
    bus: EventBus
    outbox: SqliteOutbox
    policy: PolicyEngine
    tracer: TraceRecorder
    model: ModelPort
    projects: ProjectBrain
    creator: Creator
    brief: Brief

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
    model: ModelPort | None = None,
) -> Junvis:
    """모든 부품을 조립한다.

    `offline=True`면 GitHub 어댑터를 끼우지 않는다. 네트워크가 없는 상태를
    예외가 아니라 정상 모드 중 하나로 다룬다.
    `model`을 주면 그것을 쓴다(테스트는 EchoAdapter를 넣는다).
    """
    root = resolve_home(home)
    root.mkdir(parents=True, exist_ok=True)

    db = Database(root / DB_FILENAME)
    db.migrate(CORE_MIGRATIONS, PROJECT_BRAIN_MIGRATIONS, CREATOR_MIGRATIONS)

    outbox = SqliteOutbox(db)
    bus = EventBus(outbox)
    policy = PolicyEngine(confirmer=confirmer)
    tracer = TraceRecorder(SqliteTraceStore(db), bus)

    # Database.transaction은 "호출하면 컨텍스트 매니저를 주는 것"이므로
    # 그대로 UnitOfWorkPort를 만족한다. 별도 래퍼 클래스를 만들 이유가 없다.
    unit_of_work = db.transaction

    # 저장소는 조립 루트가 소유한다. 여러 feature와 brief가 같은 저장소를
    # 서로 다른 방식으로(추적하며/추적 없이) 감싸야 하기 때문이다.
    project_repository = SqliteProjectRepository(db)
    content_repository = SqliteContentRepository(db)
    brand_voice = SqliteBrandVoiceStore(db)

    resolved_model = model or OllamaAdapter()
    projects = _build_project_brain(
        project_repository, bus, policy, tracer, unit_of_work, offline=offline
    )
    creator = _build_creator(
        content_repository, brand_voice, bus, policy, tracer,
        unit_of_work, projects, resolved_model,
    )
    brief = _build_brief(
        db, project_repository, content_repository, brand_voice, policy, tracer,
        offline=offline,
    )

    register_project_subscribers(bus, projects.refresh)
    register_creator_subscribers(bus, creator.suggest)

    return Junvis(
        home=root,
        db=db,
        bus=bus,
        outbox=outbox,
        policy=policy,
        tracer=tracer,
        model=resolved_model,
        projects=projects,
        creator=creator,
        brief=brief,
    )


def _build_project_brain(
    repository, bus, policy, tracer, unit_of_work, *, offline: bool
) -> ProjectBrain:
    git = GitAdapter()
    scanner = ProjectScanner()
    issues = None if offline else GitHubIssueAdapter()
    return ProjectBrain(
        register=RegisterProject(
            repository, bus, unit_of_work, policy=policy, git=git, tracer=tracer
        ),
        refresh=RefreshSnapshot(
            repository, bus, unit_of_work, git, scanner,
            issues=issues, policy=policy, tracer=tracer,
        ),
        load_context=LoadProjectContext(repository, policy=policy, tracer=tracer),
        search=SearchProjects(repository, policy=policy, tracer=tracer),
        list_all=ListProjects(repository, policy=policy, tracer=tracer),
        remember=RememberNote(repository, bus, unit_of_work, policy=policy, tracer=tracer),
    )


def _build_creator(
    repository,
    brand_voice,
    bus,
    policy,
    tracer,
    unit_of_work,
    projects: ProjectBrain,
    model: ModelPort,
) -> Creator:
    generator = LlmScriptGenerator(model)
    # creator는 project_brain을 모른다. 여기서 어댑터로 이어 붙인다.
    project_context = ProjectContextAdapter(projects.load_context)
    return Creator(
        generate=GenerateContent(
            repository, brand_voice, generator, bus, unit_of_work,
            project_context=project_context, policy=policy, tracer=tracer,
        ),
        list_all=ListContent(repository, policy=policy, tracer=tracer),
        get=GetContent(repository, policy=policy, tracer=tracer),
        dismiss=DismissContent(repository, bus, unit_of_work, policy=policy, tracer=tracer),
        mark_published=MarkPublished(
            repository, bus, unit_of_work, policy=policy, tracer=tracer
        ),
        record_performance=RecordPerformance(
            repository, bus, unit_of_work, policy=policy, tracer=tracer
        ),
        get_brand_voice=GetBrandVoice(brand_voice, policy=policy, tracer=tracer),
        update_brand_voice=UpdateBrandVoice(brand_voice, policy=policy, tracer=tracer),
        suggest=SuggestForProject(repository, bus, unit_of_work, tracer=tracer),
    )


def _build_brief(
    db, project_repository, content_repository, brand_voice, policy, tracer, *, offline: bool
) -> Brief:
    """brief는 다른 feature를 모른다. 어댑터로만 이어 붙인다.

    캘린더와 뉴스는 각각 macOS 권한과 네트워크를 요구한다. 둘 다 없어도
    브리핑은 나와야 하므로, 실패는 유스케이스가 흡수한다.

    수집용 조회에는 **Trace를 붙이지 않는다.** 브리핑이 자기 조회를 기록하면
    "작업 습관"이 브리핑 자신의 활동으로 채워진다. 사용자가 직접 부른
    `junvis list`와 브리핑이 내부적으로 읽는 것은 다른 사건이다.
    """
    return Brief(
        compose=ComposeBriefing(
            ProjectDigestAdapter(ListProjects(project_repository)),
            ContentDigestAdapter(ListContent(content_repository)),
            calendar=MacCalendarAdapter(),
            habits=TraceHabitAnalyzer(db),
            news=None if offline else HackerNewsAdapter(),
            interests=BrandInterestsAdapter(GetBrandVoice(brand_voice)),
            policy=policy,
            tracer=tracer,
        )
    )
