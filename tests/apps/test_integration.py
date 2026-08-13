"""조립된 JUNVIS의 통합 동작.

이 파일의 핵심은 첫 번째 테스트다: `project_brain`은 `creator`의 존재를
모르는데도 새 프로젝트를 등록하면 콘텐츠 제안이 생긴다. 설계 §3에서
약속한 Event Bus 분리가 말이 아니라 사실임을 보이는 것이 목적이다.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from junvis.apps.container import Junvis, build
from junvis.apps.mcp_server.main import collect_tools
from junvis.core.model.echo import EchoAdapter
from junvis.features.project_brain.application.dto import RegisterProjectCommand
from junvis.features.voice.domain.model import ListenerState, Utterance
from junvis.features.voice.infrastructure.tts import NullTts
from tests.features.creator.test_infrastructure import VALID_PAYLOAD


class ScriptedModel:
    """요청의 스키마를 보고 알맞은 응답을 돌려주는 테스트용 모델.

    한 컨테이너 안에서 Intent Judge와 대본 생성기가 같은 ModelPort를
    공유하므로, 고정 응답 하나로는 둘 다 만족시킬 수 없다.
    """

    def __init__(self) -> None:
        self.calls: list = []
        self.judge_verdict = True
        self.chat_answer = "그건 이렇게 생각합니다."

    def complete(self, request):
        from junvis.core.model.ports import ModelResponse

        self.calls.append(request)
        properties = (request.schema or {}).get("properties", {})
        if "is_command" in properties:
            body = json.dumps({"is_command": self.judge_verdict})
        elif request.schema is None:
            # 스키마가 없으면 대화다. 사람에게 하는 말을 돌려준다.
            body = self.chat_answer
        else:
            body = json.dumps(VALID_PAYLOAD, ensure_ascii=False)
        return ModelResponse(text=body, model="scripted")


@pytest.fixture()
def model() -> EchoAdapter:
    return EchoAdapter.returning_json(VALID_PAYLOAD)


@pytest.fixture()
def junvis(tmp_path: Path, model: EchoAdapter) -> Junvis:
    container = build(tmp_path / "home", offline=True, model=model, tts=NullTts())
    yield container
    container.close()


@pytest.fixture()
def talking(tmp_path: Path) -> Junvis:
    """음성 경로용 컨테이너. 판정과 생성을 모두 지원하는 모델을 쓴다."""
    container = build(
        tmp_path / "voice-home", offline=True, model=ScriptedModel(), tts=NullTts()
    )
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


# -- Daily Brief -------------------------------------------------------------


def test_brief_pulls_from_both_features(junvis, project) -> None:
    """brief는 두 feature를 임포트하지 않는데도 둘 다 읽는다(계약 8번)."""
    junvis.projects.register(
        RegisterProjectCommand(
            slug="reels-editor",
            name="릴스 편집기",
            path=project,
            purpose="ZUN 브랜드 콘텐츠 제작 도구",
        )
    )
    junvis.drain()

    briefing = junvis.brief.compose()
    markdown = briefing.to_markdown()
    titles = [section.title for section in briefing.sections]

    assert "진행 중인 프로젝트" in titles  # project_brain에서
    assert "대기 중인 아이디어" in titles  # creator에서
    assert "작업 습관" in titles  # Trace에서
    assert "릴스 편집기" in markdown
    assert "릴스 편집기 만든 과정" in markdown


def test_brief_is_empty_on_a_fresh_install(tmp_path, model) -> None:
    with build(tmp_path / "fresh", offline=True, model=model) as fresh:
        assert fresh.brief.compose().is_empty


def test_brief_surfaces_uncommitted_work(junvis, project) -> None:
    junvis.projects.register(
        RegisterProjectCommand(slug="reels-editor", name="릴스 편집기", path=project)
    )
    junvis.drain()
    (project / "새파일.txt").write_text("작업 중", encoding="utf-8")
    junvis.projects.refresh("reels-editor")

    briefing = junvis.brief.compose()
    assert briefing.sections[0].title == "멈춰 있는 작업"
    assert briefing.headline().startswith("멈춰 있는 작업:")


def test_briefing_does_not_count_itself_as_activity(junvis) -> None:
    """launchd가 매일 아침 브리핑을 돌린다.

    브리핑이 자기 조회를 Trace에 남기면 "가장 활발한 시간대"가 결국
    브리핑 시각으로 수렴한다. 자기 집계로 통계를 오염시키면 안 된다.
    """
    for _ in range(3):
        junvis.brief.compose()

    titles = [s.title for s in junvis.brief.compose().sections]
    assert "작업 습관" not in titles


def test_user_actions_do_count_as_activity(junvis) -> None:
    junvis.creator.generate(subject="주제")  # 사용자가 직접 부른 것
    briefing = junvis.brief.compose()

    section = next(s for s in briefing.sections if s.title == "작업 습관")
    assert "content.create" in section.render()


def test_brief_tool_is_exposed(junvis) -> None:
    tools = {spec.name: spec for spec in collect_tools(junvis)}
    result = tools["junvis_daily_brief"].handler({})
    assert "브리핑" in result.text
    assert "peak_urgency" in result.data


def test_offline_mode_skips_news(junvis) -> None:
    """offline=True면 뉴스 어댑터를 아예 끼우지 않는다."""
    titles = [s.title for s in junvis.brief.compose().sections]
    assert "AI 소식" not in titles


# -- Personal Memory ---------------------------------------------------------


def test_remembered_rules_reach_the_content_prompt(junvis, model) -> None:
    """기억이 어딘가에 쌓이기만 하면 죽은 데이터다. 첫 소비자는 Creator다."""
    from junvis.features.memory.domain.model import MemoryScope

    junvis.memory.remember(
        "썸네일 문구는 3단어 이하로", scope=MemoryScope.CONTENT, pinned=True
    )

    junvis.creator.generate(subject="MCP 서버 만들기")

    prompt = model.calls[0].prompt
    assert "썸네일 문구는 3단어 이하로" in prompt
    assert "반드시 지킬 것" in prompt


def test_only_content_scoped_memories_reach_the_prompt(junvis, model) -> None:
    """프로젝트 기억이 릴스 프롬프트에 섞이면 예산만 축낸다."""
    from junvis.features.memory.domain.model import MemoryScope

    junvis.memory.remember("Supabase를 쓴다", scope=MemoryScope.PROJECT, subject="x")
    junvis.memory.remember("과장하지 말 것", scope=MemoryScope.CONTENT)

    junvis.creator.generate(subject="주제")

    prompt = model.calls[0].prompt
    assert "과장하지 말 것" in prompt
    assert "Supabase" not in prompt


def test_content_generation_works_without_any_memory(junvis) -> None:
    assert junvis.creator.generate(subject="주제").summary.status == "drafted"


def test_publishing_content_is_learned(junvis) -> None:
    detail = junvis.creator.generate(subject="MCP 서버 만들기")
    junvis.creator.mark_published(detail.summary.id)
    junvis.drain()

    texts = [view.text for view in junvis.memory.list_all()]
    assert "「MCP 서버 만들기」 콘텐츠를 발행했다" in texts


def test_registering_a_project_is_learned(junvis, project) -> None:
    junvis.projects.register(
        RegisterProjectCommand(slug="reels-editor", name="릴스 편집기", path=project)
    )
    junvis.drain()

    remembered = [v for v in junvis.memory.list_all() if v.scope == "project"]
    assert remembered[0].text == "「릴스 편집기」 프로젝트를 시작했다"
    assert remembered[0].subject == "reels-editor"


def test_repeated_registration_does_not_pile_up_memories(junvis, project) -> None:
    for _ in range(3):
        junvis.projects.register(
            RegisterProjectCommand(slug="reels-editor", name="릴스 편집기", path=project)
        )
        junvis.drain()

    assert len([v for v in junvis.memory.list_all() if v.scope == "project"]) == 1


def test_voice_commands_are_not_remembered(talking) -> None:
    """말한 것을 전부 저장하면 잡음이 신호를 덮는다."""
    say(talking, "자비스 프로젝트 목록")
    talking.drain()

    assert talking.memory.list_all() == []


def test_memory_tools_are_exposed(junvis) -> None:
    tools = {spec.name: spec for spec in collect_tools(junvis)}

    created = tools["junvis_remember"].handler(
        {"text": "Ollama를 기본으로 쓴다", "pinned": True}
    )
    assert created.data["pinned"] is True

    recalled = tools["junvis_recall"].handler({"query": "Ollama"})
    assert "Ollama를 기본으로 쓴다" in recalled.text

    forgotten = tools["junvis_forget"].handler({"id": created.data["id"]})
    assert "잊었습니다" in forgotten.text
    assert tools["junvis_memories"].handler({}).data["memories"] == []


def test_memory_survives_a_restart(tmp_path, model) -> None:
    home = tmp_path / "memory-home"
    with build(home, offline=True, model=model) as first:
        first.memory.remember("썸네일은 3단어 이하", pinned=True)

    with build(home, offline=True, model=model) as second:
        assert [v.text for v in second.memory.list_all()] == ["썸네일은 3단어 이하"]


# -- Voice -------------------------------------------------------------------


def say(junvis: Junvis, text: str, state: ListenerState | None = None):
    return junvis.voice.handle(
        Utterance(text=text, heard_at=datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)),
        state or ListenerState(),
    )


def test_voice_brief_command(talking, project) -> None:
    talking.projects.register(
        RegisterProjectCommand(slug="reels-editor", name="릴스 편집기", path=project)
    )
    talking.drain()

    outcome = say(talking, "자비스 오늘 브리핑")

    assert outcome.acted
    assert "브리핑입니다" in outcome.response
    assert talking.voice.tts.spoken == [outcome.response]


def test_voice_project_command(talking, project) -> None:
    talking.projects.register(
        RegisterProjectCommand(slug="reels-editor", name="릴스 편집기", path=project)
    )
    talking.drain()

    assert "릴스 편집기" in say(talking, "자비스 프로젝트 뭐 있어").response


def test_voice_project_command_with_nothing_registered(talking) -> None:
    assert "없습니다" in say(talking, "자비스 프로젝트 목록").response


def test_voice_content_command_fills_a_pending_suggestion(talking, project) -> None:
    talking.projects.register(
        RegisterProjectCommand(slug="reels-editor", name="릴스 편집기", path=project)
    )
    talking.drain()

    outcome = say(talking, "자비스 릴스 하나 만들자")

    assert "기획을 만들었습니다" in outcome.response
    assert talking.creator.list_all(status="drafted")


def test_voice_content_command_with_an_explicit_subject(talking) -> None:
    outcome = say(talking, "자비스 MCP 서버 만들기 릴스 만들어줘")

    assert "기획을 만들었습니다" in outcome.response
    drafted = talking.creator.list_all(status="drafted")
    assert drafted[0].subject == "MCP 서버 만들기"


def test_unmatched_speech_becomes_a_conversation(talking) -> None:
    """규칙에 없는 말이라고 "못 합니다"로 끝내지 않는다."""
    outcome = say(talking, "자비스 요즘 뭐부터 하면 좋을까")

    assert outcome.acted
    assert outcome.response == "그건 이렇게 생각합니다."


def test_conversation_is_grounded_in_what_junvis_knows(talking, project) -> None:
    """근거 없이 답하면 그럴듯한 거짓말을 한다. 개인 비서에서 최악이다."""
    talking.projects.register(
        RegisterProjectCommand(slug="reels-editor", name="릴스 편집기", path=project)
    )
    talking.drain()

    say(talking, "자비스 요즘 뭐부터 하면 좋을까")

    chat = [c for c in talking.model.calls if c.schema is None][-1]
    assert "릴스 편집기" in chat.prompt
    assert "ZUN" in chat.system


def test_rules_still_win_over_conversation(talking) -> None:
    """아는 명령은 여전히 규칙이 결정론적으로 실행한다."""
    outcome = say(talking, "자비스 오늘 브리핑")

    assert "브리핑입니다" in outcome.response or "챙길 것은 없습니다" in outcome.response


def test_voice_ignores_speech_without_a_wake_word(talking) -> None:
    outcome = say(talking, "오늘 점심 뭐 먹지")
    assert not outcome.acted
    assert talking.voice.tts.spoken == []


def test_voice_respects_the_intent_judge(talking) -> None:
    talking.model.judge_verdict = False
    outcome = say(talking, "자비스 어 잠깐만")
    assert not outcome.acted


def test_voice_full_conversation_with_follow_up(talking, project) -> None:
    """호출어 → 응답 → 호출어 없는 후속 명령."""
    talking.projects.register(
        RegisterProjectCommand(slug="reels-editor", name="릴스 편집기", path=project)
    )
    talking.drain()

    first = say(talking, "자비스 오늘 브리핑")
    second = say(talking, "프로젝트 목록", first.state)

    assert first.acted and second.acted
    assert "릴스 편집기" in second.response
    assert len(talking.voice.tts.spoken) == 2


def test_voice_command_publishes_an_event(talking) -> None:
    seen = []
    talking.bus.subscribe("voice.command_received", lambda e: seen.append(e.payload))

    say(talking, "자비스 프로젝트 목록")

    assert seen[0]["text"] == "프로젝트 목록"


def test_every_use_case_leaves_a_trace(junvis) -> None:
    from junvis.core.trace.store import SqliteTraceStore

    junvis.creator.generate(subject="주제")
    junvis.creator.list_all()

    requests = {t.request for t in SqliteTraceStore(junvis.db).recent(50)}
    assert {"content.create", "content.list"} <= requests


def test_voice_survives_korean_stt_spacing(talking) -> None:
    """실제로 이렇게 들렸다: "릴 스 만들어 줘".

    한국어 STT의 띄어쓰기는 신뢰할 수 없다. 라우터가 "릴스"만 찾으면
    사용자는 또박또박 붙여 말해야 하는데, 그건 사람이 기계에 맞추는 것이다.
    """
    outcome = say(talking, "자비스 MCP 서버 릴 스 만들어 줘")

    assert outcome.acted
    assert "기획을 만들었습니다" in outcome.response
    # 상투어를 못 걷어내면 "릴 스 만들어 줘"가 주제에 섞여 들어간다.
    # 조용히 엉뚱한 기획을 만드는 쪽이 못 알아듣는 것보다 나쁘다.
    assert talking.creator.list_all(status="drafted")[0].subject == "MCP 서버"


def test_voice_survives_spacing_in_the_wake_word(talking) -> None:
    outcome = say(talking, "자비 스 프로젝트 목록")

    assert outcome.acted


# -- 실행인가 질문인가 --------------------------------------------------------


def test_asking_for_an_opinion_does_not_execute(talking) -> None:
    """실제로 겪은 것: "릴스 소재로 뭐가 좋을까"가 릴스를 만들어 버렸다.

    질문에 엉뚱한 실행으로 답하는 것은 못 알아듣는 것보다 나쁘다.
    """
    outcome = say(talking, "자비스 내 프로젝트 중에 릴스 소재로 뭐가 제일 좋을까")

    assert outcome.response == "그건 이렇게 생각합니다."
    assert talking.creator.list_all(status="drafted") == []


@pytest.mark.parametrize(
    "said",
    ["프로젝트 뭐 있어", "프로젝트 목록", "오늘 브리핑", "릴스 만들어줘"],
)
def test_plain_commands_still_run(talking, said: str) -> None:
    """규칙이 잡을 수 있는 것은 규칙이 잡아야 한다."""
    outcome = say(talking, f"자비스 {said}")

    assert outcome.response != "그건 이렇게 생각합니다."
