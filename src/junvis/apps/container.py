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
    ContentMemoryAdapter,
    ProjectContextAdapter,
    ProjectDigestAdapter,
)
from junvis.apps.memory_learning import register_learning
from junvis.apps.conversation import Conversation
from junvis.apps.voice_router import VoiceCommandRouter
from junvis.core.eventbus.bus import DrainReport, EventBus
from junvis.core.eventbus.outbox import SqliteOutbox
from junvis.core.mcp.catalog import ToolCatalog
from junvis.core.mcp.config import CONFIG_FILENAME, McpConfig
from junvis.core.mcp.host import McpHost
from junvis.core.model.claude_code import ClaudeCodeAdapter
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
from junvis.features.memory.application.use_cases.queries import (
    BuildDigest,
    ListMemories,
    RecallMemories,
)
from junvis.features.memory.application.use_cases.learn_from_dialogue import (
    LearnFromDialogue,
)
from junvis.features.memory.application.use_cases.remember import (
    ForgetFact,
    PinFact,
    RememberFact,
)
from junvis.features.memory.infrastructure import MEMORY_MIGRATIONS
from junvis.features.memory.infrastructure.sqlite_repository import (
    SqliteMemoryRepository,
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
from junvis.features.voice.application.ports import TextToSpeechPort
from junvis.features.voice.application.use_cases.handle_utterance import HandleUtterance
from junvis.features.voice.domain.model import WakeWordConfig
from junvis.features.voice.infrastructure.intent_judge import LlmIntentJudge
from junvis.features.voice.infrastructure.presence import STATE_FILENAME, FilePresence
from junvis.features.voice.infrastructure.tts import default_tts

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
class Memory:
    """memory의 유스케이스 묶음."""

    remember: RememberFact
    recall: RecallMemories
    list_all: ListMemories
    forget: ForgetFact
    pin: PinFact
    digest: BuildDigest
    #: 대화에서 오래 갈 사실만 뽑아 기억한다(Mem0의 2단계, docs/10 §3).
    learn: LearnFromDialogue


@dataclass
class Voice:
    """voice의 유스케이스 묶음."""

    handle: HandleUtterance
    tts: TextToSpeechPort
    config: WakeWordConfig
    #: 오브(`junvis orb`)가 읽는 상태 파일. 듣기와 화면은 다른 프로세스다.
    presence_path: Path
    #: 지금 말할 수 있는 것들. 음성에는 메뉴가 없으니 어딘가에는 적어야 한다.
    examples: tuple[str, ...]
    #: 규칙이 못 알아들은 말을 받는다. `junvis ask` 도 이것을 쓴다.
    conversation: Conversation
    #: 마이크를 거치지 않고 같은 라우터로 보낸다. 호출어도 게이트도 없다 —
    #: 타이핑한 것은 언제나 나에게 한 말이다.
    handle_text: object


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
    voice: Voice
    memory: Memory
    mcp: McpHost

    def drain(self, limit: int = 100) -> DrainReport:
        """미처리 비동기 이벤트를 소비한다. 진입점이 작업 후 호출한다."""
        return self.bus.drain(limit)

    def close(self) -> None:
        # 외부 MCP 서버 프로세스를 먼저 내린다. 고아 프로세스를 남기지 않는다.
        self.mcp.close()
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
    tts: TextToSpeechPort | None = None,
) -> Junvis:
    """모든 부품을 조립한다.

    `offline=True`면 GitHub 어댑터를 끼우지 않는다. 네트워크가 없는 상태를
    예외가 아니라 정상 모드 중 하나로 다룬다.
    `model`·`tts`를 주면 그것을 쓴다(테스트는 EchoAdapter·NullTts를 넣는다).
    """
    root = resolve_home(home)
    root.mkdir(parents=True, exist_ok=True)

    db = Database(root / DB_FILENAME)
    db.migrate(
        CORE_MIGRATIONS, PROJECT_BRAIN_MIGRATIONS, CREATOR_MIGRATIONS, MEMORY_MIGRATIONS
    )

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

    memory_repository = SqliteMemoryRepository(db)

    resolved_model = model or _default_model()
    # 주입된 모델은 그대로 쓴다. 테스트가 넣은 것을 조립 루트가 몰래
    # 갈아 끼우면 무엇을 검증한 것인지 알 수 없게 된다.
    chat_model = resolved_model if model is not None else _conversation_brain(resolved_model)
    judge_model = _judge_brain(resolved_model)
    memory = _build_memory(
        memory_repository, bus, policy, tracer, unit_of_work, judge_model
    )
    projects = _build_project_brain(
        project_repository, bus, policy, tracer, unit_of_work, offline=offline
    )
    creator = _build_creator(
        content_repository, brand_voice, bus, policy, tracer,
        unit_of_work, projects, memory, resolved_model,
    )
    brief = _build_brief(
        db, project_repository, content_repository, brand_voice, policy, tracer,
        offline=offline,
    )
    voice = _build_voice(
        bus, tracer, resolved_model, projects, creator, brief, memory,
        tts=tts, root=root, chat_model=chat_model, judge_model=judge_model,
    )
    mcp_config = McpConfig(root / CONFIG_FILENAME)
    mcp_host = McpHost(
        ToolCatalog(db), mcp_config.load(), policy=policy, log_dir=root / "logs"
    )

    register_project_subscribers(bus, projects.refresh)
    register_creator_subscribers(bus, creator.suggest)
    # 자동 기억은 **작은 모델만** 쓴다. 대화 한 번에 호출이 둘 늘어나는데
    # 거기에 Claude를 부르면 답을 듣고 나서 또 10초를 기다리게 된다.
    register_learning(bus, memory.remember, learn=memory.learn)

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
        voice=voice,
        memory=memory,
        mcp=mcp_host,
    )


def _build_memory(repository, bus, policy, tracer, unit_of_work, model) -> Memory:
    remember = RememberFact(repository, bus, unit_of_work, policy=policy, tracer=tracer)
    recall = RecallMemories(repository, unit_of_work, policy=policy, tracer=tracer)
    forget = ForgetFact(repository, bus, unit_of_work, policy=policy, tracer=tracer)
    return Memory(
        remember=remember,
        recall=recall,
        list_all=ListMemories(repository, policy=policy, tracer=tracer),
        forget=forget,
        pin=PinFact(repository, unit_of_work, policy=policy, tracer=tracer),
        # 프롬프트 조립용이라 Trace를 남기지 않는다(brief의 수집 조회와 같은 이유).
        digest=BuildDigest(repository),
        learn=LearnFromDialogue(model, remember, recall, forget, tracer=tracer),
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
    memory: Memory,
    model: ModelPort,
) -> Creator:
    generator = LlmScriptGenerator(model)
    # creator는 project_brain도 memory도 모른다. 여기서 어댑터로 이어 붙인다.
    project_context = ProjectContextAdapter(projects.load_context)
    return Creator(
        generate=GenerateContent(
            repository, brand_voice, generator, bus, unit_of_work,
            project_context=project_context,
            memory=ContentMemoryAdapter(memory.digest),
            policy=policy, tracer=tracer,
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


#: 무엇을 두뇌로 쓸지. "claude" · "ollama" · 비우면 알아서 고른다.
BRAIN_ENV = "JUNVIS_BRAIN"


def _judge_brain(shared: ModelPort) -> ModelPort:
    """게이트 4는 **절대** Claude로 하지 않는다.

    이 판정은 발화마다 돈다. 거기에 `claude -p` 를 부르면 프로세스가 매번
    새로 뜨고, MCP 서버가 붙어 있으면 그것까지 전부 기동한다. 실제로 말
    한마디에 90초가 걸려 대화 자체가 타임아웃됐다.

    "이게 나에게 한 말인가"는 작은 모델로 충분한 판정이다. Ollama가 꺼져
    있으면 `LlmIntentJudge`가 fail-open으로 통과시킨다 — 사용자를 무시하는
    것이 잘못 실행하는 것보다 나쁘기 때문이다.
    """
    return OllamaAdapter() if isinstance(shared, ClaudeCodeAdapter) else shared


def _conversation_brain(shared: ModelPort) -> ModelPort:
    """대화만은 Claude에게 맡길 수 있다.

    게이트 4(Intent Judge)는 **발화마다** 돈다. 거기에 Claude를 부르면 말
    한마디마다 몇 초씩 기다리고 토큰도 태운다. 그 판정은 작은 모델로 충분하다.

    대화는 반대다. 품질이 곧 값어치이고, 한 번 부르는 데 몇 초는 괜찮다.
    그래서 공유 모델이 Claude가 아니더라도 대화만 따로 올려 준다.
    """
    if isinstance(shared, ClaudeCodeAdapter):
        return shared
    if os.environ.get(BRAIN_ENV, "").strip().lower() == "ollama":
        return shared

    claude = ClaudeCodeAdapter()
    return claude if claude.is_available() else shared


def _default_model() -> ModelPort:
    """있는 것 중 좋은 것을 고른다.

    Claude Code CLI가 깔려 있으면 그것을 쓴다 — 이미 로그인돼 있고, 로컬
    소형 모델과 답변 품질이 비교되지 않으며, Ollama를 따로 띄울 필요가 없다.
    없으면 Ollama로 내려간다.
    """
    choice = os.environ.get(BRAIN_ENV, "").strip().lower()
    if choice == "ollama":
        return OllamaAdapter()
    if choice == "claude":
        return ClaudeCodeAdapter()

    claude = ClaudeCodeAdapter()
    return claude if claude.is_available() else OllamaAdapter()


def _build_voice(
    bus,
    tracer,
    model: ModelPort,
    projects: ProjectBrain,
    creator: Creator,
    brief: Brief,
    memory: Memory,
    *,
    tts: TextToSpeechPort | None,
    root: Path,
    chat_model: ModelPort,
    judge_model: ModelPort,
) -> Voice:
    """라우터가 여러 Context를 안다. feature끼리는 여전히 서로를 모른다."""
    router = VoiceCommandRouter(
        compose_brief=brief.compose,
        list_projects=projects.list_all,
        list_content=creator.list_all,
        generate_content=creator.generate,
    )
    conversation = Conversation(
        chat_model,
        list_projects=projects.list_all,
        digest=memory.digest,
        get_brand_voice=creator.get_brand_voice,
        commands=router.examples(),
        bus=bus,
    )
    # 라우터가 대화를 알아야 하고 대화가 라우터의 명령을 알아야 한다.
    # 순환이 아니라 한 방향씩이므로 만든 뒤에 이어 준다.
    router.set_conversation(conversation)
    config = WakeWordConfig.with_words(_wake_words())
    resolved_tts = tts or default_tts()
    presence = FilePresence(root / STATE_FILENAME)
    return Voice(
        handle=HandleUtterance(
            LlmIntentJudge(judge_model),
            router,
            resolved_tts,
            bus,
            config=config,
            tracer=tracer,
            presence=presence,
        ),
        tts=resolved_tts,
        config=config,
        presence_path=presence.path,
        examples=router.examples(),
        conversation=conversation,
        handle_text=router.handle,
    )


def _wake_words() -> tuple[str, ...]:
    raw = os.environ.get("JUNVIS_WAKE_WORDS", "")
    return tuple(word.strip() for word in raw.split(",") if word.strip())
