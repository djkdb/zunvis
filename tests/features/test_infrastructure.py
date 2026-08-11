"""M8 완료 기준: 실제 SQLite와 실제 git 저장소로 왕복이 된다."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from junvis.features.project_brain.domain.model import (
    CommitRef,
    IssueRef,
    Project,
    ProjectSnapshot,
)
from junvis.features.project_brain.domain.value_objects import (
    ProjectId,
    RepoRef,
    Slug,
    TechStack,
)
from junvis.features.project_brain.infrastructure.git_adapter import GitAdapter
from junvis.features.project_brain.infrastructure.project_scanner import ProjectScanner
from junvis.features.project_brain.infrastructure.sqlite_repository import (
    SqliteProjectRepository,
)

NOW = datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc)


@pytest.fixture()
def repository(db) -> SqliteProjectRepository:
    return SqliteProjectRepository(db)


def build_project(slug: str = "zunvis") -> Project:
    project = Project.register(
        slug=Slug(slug),
        name="ZUNVIS",
        local_path=Path("/Users/zun/dev/zunvis"),
        repo=RepoRef("github.com", "djkdb", "zunvis"),
        purpose="개인 AI OS",
        architecture_note="Clean Architecture + Event Bus",
        tech_stack=TechStack.of(["Python"]),
        now=NOW,
    )
    project.refresh(
        ProjectSnapshot(
            captured_at=NOW,
            branch="main",
            dirty=True,
            readme_excerpt="JUNVIS는 macOS용 개인 AI OS다",
            recent_commits=(CommitRef("a" * 40, "첫 커밋", NOW, "ZUN"),),
            open_issues=(IssueRef(3, "MCP 서버 붙이기", "open", "https://x/3"),),
            detected_stack=TechStack.of(["MCP"]),
            discovered_todos=("스케줄러 만들기",),
        ),
        now=NOW,
    )
    project.remember("Ollama를 기본 모델로 쓴다", now=NOW)
    project.pull_events()
    return project


# -- 저장소 왕복 -------------------------------------------------------------


def test_roundtrip_preserves_everything(repository) -> None:
    original = build_project()
    repository.save(original)

    loaded = repository.get_by_slug(Slug("zunvis"))

    assert loaded is not None
    assert loaded.name == original.name
    assert loaded.local_path == original.local_path
    assert loaded.repo == original.repo
    assert loaded.purpose == original.purpose
    assert set(loaded.tech_stack) == {"Python", "MCP"}
    assert loaded.snapshot.branch == "main"
    assert loaded.snapshot.dirty is True
    assert loaded.snapshot.recent_commits[0].subject == "첫 커밋"
    assert loaded.snapshot.open_issues[0].number == 3
    assert [t.text for t in loaded.todos] == ["스케줄러 만들기"]
    assert [n.text for n in loaded.notes] == ["Ollama를 기본 모델로 쓴다"]
    assert loaded.created_at == original.created_at


def test_save_is_idempotent_update(repository) -> None:
    project = build_project()
    repository.save(project)
    project.describe(purpose="바뀐 목적", now=NOW)
    repository.save(project)

    assert len(repository.list()) == 1
    assert repository.get(project.id).purpose == "바뀐 목적"


def test_get_by_id_and_missing(repository) -> None:
    project = build_project()
    repository.save(project)
    assert repository.get(project.id) is not None
    assert repository.get(ProjectId("없는아이디")) is None
    assert repository.get_by_slug(Slug("nope")) is None


def test_list_is_ordered_by_recency(repository) -> None:
    older = build_project("older")
    older.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    newer = build_project("newer")
    newer.updated_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
    repository.save(older)
    repository.save(newer)

    assert [p.slug.value for p in repository.list()] == ["newer", "older"]


def test_remove(repository) -> None:
    project = build_project()
    repository.save(project)
    assert repository.remove(project.id) is True
    assert repository.list() == []
    assert repository.remove(project.id) is False


# -- FTS5 검색 ---------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    ["zunvis", "ZUNVIS", "개인", "Clean", "macOS", "Ollama", "MCP"],
)
def test_search_finds_across_indexed_fields(repository, query: str) -> None:
    repository.save(build_project())
    hits = repository.search(query)
    assert [h.slug.value for h in hits] == ["zunvis"]


def test_search_is_prefix_matching(repository) -> None:
    repository.save(build_project())
    assert repository.search("zun")[0].slug.value == "zunvis"


def test_search_survives_fts_syntax_in_user_input(repository) -> None:
    """사용자가 FTS5 문법 문자를 넣어도 질의가 깨지지 않아야 한다."""
    repository.save(build_project())
    for hostile in ['"', "AND OR NOT", "*", "(((", "zunvis OR", '"unclosed']:
        repository.search(hostile)  # 예외가 나지 않으면 통과


def test_search_returns_empty_for_meaningless_query(repository) -> None:
    repository.save(build_project())
    assert repository.search("   ") == []


def test_reindex_drops_stale_terms(repository) -> None:
    """저장할 때마다 FTS 행을 다시 만들므로 옛 단어는 남지 않는다.

    README에도 나오지 않는 고유 토큰을 써야 실제로 재색인을 검증한다.
    """
    project = build_project()
    project.describe(purpose="브이로그편집기", now=NOW)
    repository.save(project)
    assert repository.search("브이로그편집기")

    project.describe(purpose="완전히 다른 설명", now=NOW)
    repository.save(project)

    assert repository.search("브이로그편집기") == []
    assert repository.search("완전히")


# -- git 어댑터 --------------------------------------------------------------


def git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    run = lambda *args: subprocess.run(  # noqa: E731
        ["git", "-C", str(path), *args], check=True, capture_output=True
    )
    run("init", "-q")
    run("config", "user.email", "zun@example.com")
    run("config", "user.name", "ZUN")
    run("remote", "add", "origin", "git@github.com:djkdb/zunvis.git")
    (path / "README.md").write_text("# ZUNVIS\n\n개인 AI OS\n", encoding="utf-8")
    run("add", ".")
    run("commit", "-q", "-m", "첫 커밋")
    return path


def test_git_adapter_reads_real_repository(tmp_path) -> None:
    path = git_repo(tmp_path / "repo")
    reading = GitAdapter().read(path)

    assert reading is not None
    assert reading.branch in {"main", "master"}
    assert reading.dirty is False
    # 원격 URL 표기는 환경(insteadOf 재작성 등)에 따라 달라진다.
    # 계약은 "어떤 표기든 저장소를 식별할 수 있다"이다.
    assert RepoRef.parse(reading.remote_url).full_name == "djkdb/zunvis"
    assert len(reading.commits) == 1
    assert reading.commits[0].subject == "첫 커밋"
    assert reading.commits[0].author == "ZUN"


def test_git_adapter_detects_dirty_tree(tmp_path) -> None:
    path = git_repo(tmp_path / "repo")
    (path / "new.txt").write_text("변경", encoding="utf-8")
    assert GitAdapter().read(path).dirty is True


def test_git_adapter_returns_none_for_non_repo(tmp_path) -> None:
    assert GitAdapter().read(tmp_path) is None


def test_git_adapter_survives_repo_without_commits(tmp_path) -> None:
    """커밋이 하나도 없는 저장소에서도 예외가 나지 않아야 한다."""
    path = tmp_path / "empty"
    path.mkdir()
    subprocess.run(["git", "-C", str(path), "init", "-q"], check=True, capture_output=True)
    reading = GitAdapter().read(path)
    assert reading is not None
    assert reading.commits == ()


# -- 스캐너 ------------------------------------------------------------------


def test_scanner_detects_stack_and_todos(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM python\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"next": "15", "tailwindcss": "4"}}', encoding="utf-8"
    )
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "TODO.md").write_text("- [ ] 스케줄러\n- [x] 끝난 일\n", encoding="utf-8")

    result = ProjectScanner().scan(tmp_path)

    assert {"Python", "Docker", "Node.js", "Next.js", "Tailwind CSS", "GitHub Actions"} <= set(
        result.stack
    )
    assert result.todos == ("스케줄러",)  # 완료된 항목은 가져오지 않는다


def test_scanner_strips_badges_from_readme(tmp_path) -> None:
    (tmp_path / "README.md").write_text(
        "# 제목\n[![build](https://img.shields.io/x)](https://y)\n\n본문입니다\n",
        encoding="utf-8",
    )
    excerpt = ProjectScanner().scan(tmp_path).readme_excerpt
    assert "shields.io" not in excerpt
    assert "본문입니다" in excerpt


def test_scanner_truncates_long_readme(tmp_path) -> None:
    (tmp_path / "README.md").write_text("가" * 5000, encoding="utf-8")
    excerpt = ProjectScanner().scan(tmp_path).readme_excerpt
    assert len(excerpt) < 2000
    assert excerpt.endswith("…")


def test_scanner_on_empty_directory(tmp_path) -> None:
    result = ProjectScanner().scan(tmp_path)
    assert result.readme_excerpt == ""
    assert len(result.stack) == 0
    assert result.todos == ()
