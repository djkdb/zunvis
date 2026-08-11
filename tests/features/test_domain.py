"""M6 완료 기준: 도메인은 단위 테스트만으로 검증된다 (외부 의존 0)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from junvis.features.project_brain.domain.errors import InvalidSlug
from junvis.features.project_brain.domain.model import (
    SOURCE_SCAN,
    SOURCE_USER,
    CommitRef,
    IssueRef,
    Project,
    ProjectSnapshot,
)
from junvis.features.project_brain.domain.value_objects import (
    RepoRef,
    Slug,
    TechStack,
    TokenBudget,
)

NOW = datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc)


def make_project(**kwargs) -> Project:
    defaults = dict(slug=Slug("zunvis"), name="ZUNVIS", now=NOW)
    defaults.update(kwargs)
    return Project.register(**defaults)


# -- 값 객체 ----------------------------------------------------------------


def test_slug_normalization() -> None:
    assert Slug.from_text("  ZUN Vis Project! ").value == "zun-vis-project"
    # 비ASCII는 제거된다. 남은 것이 없으면 InvalidSlug가 난다(아래 테스트).
    assert Slug.from_text("한글 프로젝트 v2").value == "v2"


def test_slug_rejects_garbage() -> None:
    with pytest.raises(InvalidSlug):
        Slug("-시작이하이픈")
    with pytest.raises(InvalidSlug):
        Slug.from_text("!!!")


@pytest.mark.parametrize(
    "remote",
    [
        "git@github.com:djkdb/zunvis.git",
        "https://github.com/djkdb/zunvis.git",
        "https://github.com/djkdb/zunvis",
        "ssh://git@github.com/djkdb/zunvis.git",
        "https://user@github.com/djkdb/zunvis.git",
    ],
)
def test_repo_ref_parses_every_remote_shape(remote: str) -> None:
    repo = RepoRef.parse(remote)
    assert repo is not None
    assert repo.full_name == "djkdb/zunvis"
    assert repo.url == "https://github.com/djkdb/zunvis"


def test_repo_ref_returns_none_instead_of_raising() -> None:
    # 원격이 없는 로컬 전용 프로젝트도 1급 시민이다.
    assert RepoRef.parse(None) is None
    assert RepoRef.parse("") is None
    assert RepoRef.parse("그냥문자열") is None


def test_tech_stack_dedupes_case_insensitively_and_is_deterministic() -> None:
    stack = TechStack.of([" Python ", "python", "Swift", ""])
    assert list(stack) == ["Python", "Swift"]  # 처음 본 표기를 유지, 소문자 기준 정렬
    merged = TechStack.of(["Python"]).merged(TechStack.of(["swift", "Python"]))
    assert list(merged) == ["Python", "swift"]


def test_token_budget_rejects_zero() -> None:
    with pytest.raises(ValueError):
        TokenBudget(0)


# -- 애그리게이트 ------------------------------------------------------------


def test_register_records_event() -> None:
    project = make_project(repo=RepoRef("github.com", "djkdb", "zunvis"))
    events = project.pull_events()
    assert [type(e).topic for e in events] == ["project.registered"]
    assert events[0].payload()["repo_full_name"] == "djkdb/zunvis"
    # 두 번 꺼내면 비어 있다
    assert project.pull_events() == []


def test_refresh_merges_stack_but_replaces_scan_todos() -> None:
    project = make_project(tech_stack=TechStack.of(["Python"]))
    project.pull_events()
    project.add_todo("사용자가 직접 쓴 할 일", now=NOW)

    project.refresh(
        ProjectSnapshot(
            captured_at=NOW,
            detected_stack=TechStack.of(["Swift"]),
            discovered_todos=("스캔이 찾은 할 일",),
        ),
        now=NOW,
    )
    assert set(project.tech_stack) == {"Python", "Swift"}

    project.refresh(
        ProjectSnapshot(captured_at=NOW, discovered_todos=("새로 찾은 할 일",)),
        now=NOW,
    )
    texts = {todo.text for todo in project.todos}
    # 스캔 TODO는 교체되고, 사용자 TODO는 살아남는다
    assert "사용자가 직접 쓴 할 일" in texts
    assert "새로 찾은 할 일" in texts
    assert "스캔이 찾은 할 일" not in texts
    assert {t.source for t in project.todos} == {SOURCE_USER, SOURCE_SCAN}
    # 스택은 재수집 실패에도 잃지 않는다
    assert set(project.tech_stack) == {"Python", "Swift"}


def test_remember_rejects_empty_text() -> None:
    project = make_project()
    with pytest.raises(ValueError):
        project.remember("   ")


def test_complete_todo() -> None:
    project = make_project()
    todo = project.add_todo("할 일", now=NOW)
    assert project.complete_todo(todo.id, now=NOW) is True
    assert project.todos[0].done is True
    assert project.complete_todo("없는id", now=NOW) is False


# -- Context Pack (이 Context의 심장) ----------------------------------------


def _rich_project() -> Project:
    project = make_project(purpose="개인 AI OS", architecture_note="Clean Architecture")
    project.refresh(
        ProjectSnapshot(
            captured_at=NOW,
            branch="main",
            dirty=True,
            readme_excerpt="README 본문",
            recent_commits=(
                CommitRef("abcdef1234", "첫 커밋", NOW),
                CommitRef("bbbbbb2222", "두 번째 커밋", NOW - timedelta(days=1)),
            ),
            open_issues=(IssueRef(7, "버그 있음"),),
            detected_stack=TechStack.of(["Python"]),
            discovered_todos=("MCP 서버 노출하기",),
        ),
        now=NOW,
    )
    project.remember("Ollama를 기본으로 쓴다", now=NOW)
    project.pull_events()
    return project


def test_context_pack_orders_by_priority() -> None:
    pack = _rich_project().context_pack(TokenBudget(2000))
    titles = [section.title for section in pack.sections]
    assert titles[0] == "목적"
    assert titles.index("기술 스택") < titles.index("최근 커밋")
    assert titles.index("최근 커밋") < titles.index("TODO")
    assert titles.index("TODO") < titles.index("열린 이슈")
    assert titles[-1] == "README"
    assert pack.truncated is False


def test_context_pack_skips_empty_sections() -> None:
    pack = make_project().context_pack()
    # 목적도 스냅샷도 없는 갓 등록한 프로젝트는 섹션이 하나도 없다
    assert pack.sections == ()
    assert "zunvis" in pack.to_markdown()


def test_context_pack_respects_budget() -> None:
    pack = _rich_project().context_pack(TokenBudget(10))  # 40자
    assert pack.truncated is True
    assert pack.estimated_tokens <= 12  # 근사치이므로 약간의 여유를 둔다
    assert "예산" in pack.to_markdown()


def test_context_pack_drops_section_too_small_to_be_useful() -> None:
    """자를 바에야 통째로 빼는 게 낫다는 규칙(MIN_BODY_CHARS)."""
    project = make_project(purpose="가" * 300)
    pack = project.context_pack(TokenBudget(20))  # 80자 — 목적을 담기엔 부족
    assert pack.truncated is True
    # 80자 안에 120자 최소치를 만족할 수 없으므로 섹션이 아예 없다
    assert pack.sections == ()


def test_markdown_render_contains_headers() -> None:
    markdown = _rich_project().context_pack().to_markdown()
    assert markdown.startswith("# ZUNVIS (zunvis)")
    assert "## 목적" in markdown
    assert "abcdef1 첫 커밋" in markdown
    assert "#7 버그 있음" in markdown
