"""M7 완료 기준: Fake 어댑터만으로 전 유스케이스를 검증한다."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path

import pytest

from junvis.core.domain.errors import PolicyConfirmationRequired
from junvis.core.eventbus.bus import EventBus
from junvis.core.policy.engine import PolicyEngine
from junvis.features.project_brain.application.dto import RegisterProjectCommand
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
from junvis.features.project_brain.domain.errors import InvalidSlug, ProjectNotFound
from tests.features.fakes import (
    FakeGit,
    FakeIssues,
    FakeScanner,
    FixedClock,
    InMemoryProjectRepository,
    sample_reading,
    sample_scan,
)


@pytest.fixture()
def repo() -> InMemoryProjectRepository:
    return InMemoryProjectRepository()


@pytest.fixture()
def bus() -> EventBus:
    return EventBus()


@pytest.fixture()
def register(repo, bus) -> RegisterProject:
    return RegisterProject(repo, bus, nullcontext, git=FakeGit(), clock=FixedClock())


# -- 등록 --------------------------------------------------------------------


def test_register_derives_slug_from_name(register, repo) -> None:
    summary = register(RegisterProjectCommand(name="ZUN Vis"))
    assert summary.slug == "zun-vis"
    assert len(repo.items) == 1


def test_register_derives_slug_from_path(repo, bus, tmp_path) -> None:
    use_case = RegisterProject(repo, bus, nullcontext, git=FakeGit(), clock=FixedClock())
    project_dir = tmp_path / "my-cool-app"
    project_dir.mkdir()
    summary = use_case(RegisterProjectCommand(path=project_dir))
    assert summary.slug == "my-cool-app"
    assert summary.local_path == str(project_dir.resolve())


def test_register_publishes_event(register, bus) -> None:
    seen = []
    bus.subscribe("project.registered", lambda env: seen.append(env.payload["slug"]))
    register(RegisterProjectCommand(name="zunvis"))
    assert seen == ["zunvis"]


def test_registering_twice_updates_instead_of_failing(register, repo, bus) -> None:
    register(RegisterProjectCommand(slug="zunvis", name="ZUNVIS"))
    events = []
    bus.subscribe("project.registered", lambda env: events.append(env), name="second")

    summary = register(RegisterProjectCommand(slug="zunvis", purpose="개인 AI OS"))

    assert len(repo.items) == 1
    assert summary.purpose == "개인 AI OS"
    assert events == []  # 갱신은 등록 이벤트를 내지 않는다


def test_register_picks_up_remote_from_git(repo, bus, tmp_path) -> None:
    use_case = RegisterProject(
        repo, bus, nullcontext, git=FakeGit(sample_reading()), clock=FixedClock()
    )
    summary = use_case(RegisterProjectCommand(name="zunvis", path=tmp_path))
    assert summary.repo_full_name == "djkdb/zunvis"


def test_explicit_remote_url_wins_over_git(repo, bus, tmp_path) -> None:
    use_case = RegisterProject(
        repo, bus, nullcontext, git=FakeGit(sample_reading()), clock=FixedClock()
    )
    summary = use_case(
        RegisterProjectCommand(
            name="zunvis", path=tmp_path, remote_url="https://github.com/other/repo.git"
        )
    )
    assert summary.repo_full_name == "other/repo"


# -- 스냅샷 재수집 ------------------------------------------------------------


def _refresh(repo, bus, *, issues=None, git=None, scanner=None) -> RefreshSnapshot:
    return RefreshSnapshot(
        repo,
        bus,
        nullcontext,
        git or FakeGit(sample_reading()),
        scanner or FakeScanner(sample_scan()),
        issues=issues,
        clock=FixedClock(),
    )


def test_refresh_collects_from_every_source(register, repo, bus, tmp_path) -> None:
    register(RegisterProjectCommand(slug="zunvis", name="ZUNVIS", path=tmp_path))
    from junvis.features.project_brain.domain.model import IssueRef

    summary = _refresh(repo, bus, issues=FakeIssues((IssueRef(1, "이슈"),)))("zunvis")

    assert summary.branch == "main"
    assert summary.last_commit.endswith("첫 커밋")
    assert "Python" in summary.tech_stack
    assert summary.open_todo_count == 1


def test_refresh_without_local_path_still_works(register, repo, bus) -> None:
    """경로가 없어도(원격만 아는 프로젝트) 실패하지 않는다."""
    register(RegisterProjectCommand(slug="zunvis", name="ZUNVIS"))
    summary = _refresh(repo, bus)("zunvis")
    assert summary.branch is None


def test_refresh_missing_project_raises(repo, bus) -> None:
    with pytest.raises(ProjectNotFound):
        _refresh(repo, bus)("no-such-project")


def test_malformed_slug_is_rejected_before_lookup(repo, bus) -> None:
    """형식이 틀린 slug는 '없음'이 아니라 '잘못됨'이다. 둘을 구분한다."""
    with pytest.raises(InvalidSlug):
        _refresh(repo, bus)("한글슬러그")


def test_refresh_publishes_event(register, repo, bus, tmp_path) -> None:
    register(RegisterProjectCommand(slug="zunvis", path=tmp_path))
    seen = []
    bus.subscribe("project.snapshot_refreshed", lambda env: seen.append(env.payload))
    _refresh(repo, bus)("zunvis")
    assert seen[0]["branch"] == "main"
    assert seen[0]["commit_count"] == 1


# -- 컨텍스트 로드 ------------------------------------------------------------


def test_load_context_returns_pack(register, repo, bus, tmp_path) -> None:
    register(RegisterProjectCommand(slug="zunvis", name="ZUNVIS", purpose="개인 AI OS"))
    _refresh(repo, bus)("zunvis")

    pack = LoadProjectContext(repo)("zunvis", budget_tokens=1000)

    assert pack.slug == "zunvis"
    assert pack.sections[0].title == "목적"
    assert "개인 AI OS" in pack.to_markdown()


def test_load_context_missing_project_raises(repo) -> None:
    with pytest.raises(ProjectNotFound):
        LoadProjectContext(repo)("no-such-project")


# -- 메모 --------------------------------------------------------------------


def test_remember_appends_note_and_publishes(register, repo, bus) -> None:
    register(RegisterProjectCommand(slug="zunvis"))
    seen = []
    bus.subscribe("project.note_added", lambda env: seen.append(env.payload["text"]))

    summary = RememberNote(repo, bus, nullcontext, clock=FixedClock())(
        "zunvis", "Ollama를 기본으로 쓴다"
    )

    assert summary.note_count == 1
    assert seen == ["Ollama를 기본으로 쓴다"]


# -- 조회 --------------------------------------------------------------------


def test_list_and_search(register, repo) -> None:
    register(RegisterProjectCommand(slug="zunvis", name="ZUNVIS", purpose="개인 AI OS"))
    register(RegisterProjectCommand(slug="other", name="Other"))

    assert len(ListProjects(repo)()) == 2
    hits = SearchProjects(repo)("zunvis")
    assert [h.slug for h in hits] == ["zunvis"]


# -- 정책 게이트 --------------------------------------------------------------


def test_policy_gate_blocks_when_no_confirmer(repo, bus) -> None:
    """미확인 위험 행위는 유스케이스 안에서 멈춘다."""
    strict = PolicyEngine()
    use_case = RegisterProject(
        repo, bus, nullcontext, policy=strict, git=FakeGit(), clock=FixedClock()
    )
    # project.register는 LOW라 통과한다
    use_case(RegisterProjectCommand(slug="zunvis"))

    # 등급을 강제로 올려 확인이 필요한 상황을 만든다
    from junvis.core.policy.engine import Rule, RiskLevel

    blocked = PolicyEngine(rules=[Rule("t", RiskLevel.HIGH, "테스트", actions=("project.*",))])
    guarded = RegisterProject(
        repo, bus, nullcontext, policy=blocked, git=FakeGit(), clock=FixedClock()
    )
    with pytest.raises(PolicyConfirmationRequired):
        guarded(RegisterProjectCommand(slug="another"))


def test_no_project_created_when_policy_blocks(repo, bus) -> None:
    from junvis.core.policy.engine import Rule, RiskLevel

    blocked = PolicyEngine(rules=[Rule("t", RiskLevel.FORBIDDEN, "금지", actions=("project.*",))])
    use_case = RegisterProject(
        repo, bus, nullcontext, policy=blocked, git=FakeGit(), clock=FixedClock()
    )
    with pytest.raises(Exception):
        use_case(RegisterProjectCommand(slug="zunvis"))
    assert repo.items == {}
