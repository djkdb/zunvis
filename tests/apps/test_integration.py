"""조립된 JUNVIS의 통합 동작.

이 파일의 핵심은 첫 번째 테스트다: `project_brain`은 `creator`의 존재를
모르는데도 새 프로젝트를 등록하면 콘텐츠 제안이 생긴다. 설계 §3에서
약속한 Event Bus 분리가 말이 아니라 사실임을 보이는 것이 목적이다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from junvis.apps.container import Junvis, build
from junvis.apps.mcp_server.main import collect_tools
from junvis.core.model.echo import EchoAdapter
from junvis.features.project_brain.application.dto import RegisterProjectCommand
from tests.features.creator.test_infrastructure import VALID_PAYLOAD


@pytest.fixture()
def model() -> EchoAdapter:
    return EchoAdapter.returning_json(VALID_PAYLOAD)


@pytest.fixture()
def junvis(tmp_path: Path, model: EchoAdapter) -> Junvis:
    container = build(tmp_path / "home", offline=True, model=model)
    yield container
    container.close()


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    path = tmp_path / "reels-editor"
    path.mkdir()

    def run(*args: str) -> None:
        subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)

    run("init", "-q")
    run("config", "user.email", "zun@example.com")
    run("config", "user.name", "ZUN")
    (path / "README.md").write_text("# 릴스 편집기\n\nZUN 브랜드용 도구\n", encoding="utf-8")
    (path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    run("add", ".")
    run("commit", "-q", "-m", "첫 커밋")
    return path


# -- 핵심: feature 간 결합 없이 협업한다 --------------------------------------


def test_registering_a_project_produces_a_content_suggestion(junvis, project) -> None:
    """브리프의 'Content Assistant'.

    project_brain은 creator를 임포트하지 않는다(import-linter 계약 7번).
    그런데도 이 일이 일어나는 이유는 오직 Event Bus 때문이다.
    """
    junvis.projects.register(
        RegisterProjectCommand(slug="reels-editor", name="릴스 편집기", path=project)
    )
    assert junvis.creator.list_all() == []  # 아직은 아무것도 없다 (비동기)

    junvis.drain()

    suggestions = junvis.creator.list_all(status="suggested")
    assert len(suggestions) == 1
    assert suggestions[0].subject == "릴스 편집기 만든 과정"
    assert suggestions[0].source_project_slug == "reels-editor"


def test_snapshot_refresh_also_happened(junvis, project) -> None:
    """같은 이벤트에 두 feature의 구독자가 붙어 있어도 서로를 방해하지 않는다."""
    junvis.projects.register(
        RegisterProjectCommand(slug="reels-editor", name="릴스 편집기", path=project)
    )
    junvis.drain()

    summary = junvis.projects.list_all()[0]
    assert summary.branch in {"main", "master"}
    assert "Python" in summary.tech_stack
    assert len(junvis.creator.list_all()) == 1


def test_re_registering_does_not_pile_up_suggestions(junvis, project) -> None:
    for _ in range(3):
        junvis.projects.register(
            RegisterProjectCommand(slug="reels-editor", name="릴스 편집기", path=project)
        )
        junvis.drain()

    assert len(junvis.creator.list_all()) == 1


def test_nothing_is_left_pending_after_drain(junvis, project) -> None:
    junvis.projects.register(RegisterProjectCommand(slug="reels-editor", path=project))
    junvis.drain()

    assert junvis.outbox.pending_count() == 0
    assert junvis.outbox.deadletter_count() == 0


# -- 제안 → 대본 -------------------------------------------------------------


def test_generating_from_a_suggestion_uses_real_project_facts(
    junvis, project, model
) -> None:
    junvis.projects.register(
        RegisterProjectCommand(
            slug="reels-editor",
            name="릴스 편집기",
            path=project,
            purpose="ZUN 브랜드 콘텐츠 제작 도구",
        )
    )
    junvis.drain()
    suggestion = junvis.creator.list_all(status="suggested")[0]

    detail = junvis.creator.generate(idea_id=suggestion.id)

    assert detail.summary.status == "drafted"
    # 모델에게 실제 프로젝트 정보가 전달됐다 — 지어내지 않는다
    prompt = model.calls[0].prompt
    assert "ZUN 브랜드 콘텐츠 제작 도구" in prompt
    assert "첫 커밋" in prompt
    # 브랜드 성향도 함께 간다
    assert "바이브 코딩" in prompt


def test_full_lifecycle(junvis, model) -> None:
    detail = junvis.creator.generate(subject="Claude Code로 앱 만들기")
    junvis.creator.mark_published(detail.summary.id, "https://instagram.com/p/x")

    published = junvis.creator.list_all(status="published")
    assert [c.published_url for c in published] == ["https://instagram.com/p/x"]

    junvis.creator.record_performance(detail.summary.id, "저장 120, 댓글 14")
    assert junvis.creator.get(detail.summary.id).summary.status == "published"


def test_state_survives_a_restart(tmp_path, model) -> None:
    home = tmp_path / "home"
    with build(home, offline=True, model=model) as first:
        idea_id = first.creator.generate(subject="주제").summary.id

    with build(home, offline=True, model=model) as second:
        assert second.creator.get(idea_id).summary.subject == "주제"


# -- MCP 도구 표면 -----------------------------------------------------------


def test_both_features_expose_tools(junvis) -> None:
    names = {spec.name for spec in collect_tools(junvis)}
    assert {
        "junvis_project_list",
        "junvis_project_context",
        "junvis_content_create",
        "junvis_content_list",
        "junvis_brand_voice",
    } <= names


def test_tool_names_are_unique(junvis) -> None:
    specs = collect_tools(junvis)
    assert len(specs) == len({spec.name for spec in specs})


def test_content_tools_work_end_to_end(junvis) -> None:
    tools = {spec.name: spec for spec in collect_tools(junvis)}

    created = tools["junvis_content_create"].handler(
        {"subject": "MCP로 Claude Code 확장하기"}
    )
    assert "## Hook" in created.text
    assert created.data["status"] == "drafted"

    listed = tools["junvis_content_list"].handler({"status": "drafted"})
    assert "MCP로 Claude Code 확장하기" in listed.text

    fetched = tools["junvis_content_get"].handler({"id": created.data["id"]})
    assert "## 댓글 유도" in fetched.text

    dismissed = tools["junvis_content_dismiss"].handler({"id": created.data["id"]})
    assert dismissed.data["status"] == "dismissed"


def test_brand_voice_tool_reads_and_writes(junvis) -> None:
    tools = {spec.name: spec for spec in collect_tools(junvis)}

    assert "바이브 코딩" in tools["junvis_brand_voice"].handler({}).text

    updated = tools["junvis_brand_voice"].handler({"topics": ["Swift", "macOS"]})
    assert updated.data["topics"] == ["Swift", "macOS"]
    assert tools["junvis_brand_voice"].handler({}).data["topics"] == ["Swift", "macOS"]


def test_every_use_case_leaves_a_trace(junvis) -> None:
    from junvis.core.trace.store import SqliteTraceStore

    junvis.creator.generate(subject="주제")
    junvis.creator.list_all()

    requests = {t.request for t in SqliteTraceStore(junvis.db).recent(50)}
    assert {"content.create", "content.list"} <= requests
