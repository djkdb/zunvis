"""M10 완료 기준: 터미널에서 전체 왕복이 된다."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from junvis.apps.cli.main import main


@pytest.fixture()
def home(tmp_path: Path) -> Path:
    return tmp_path / "home"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    path = tmp_path / "zun-app"
    path.mkdir()

    def run(*args: str) -> None:
        subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)

    run("init", "-q")
    run("config", "user.email", "zun@example.com")
    run("config", "user.name", "ZUN")
    (path / "README.md").write_text("# ZUN App\n\n바이브 코딩 도구\n", encoding="utf-8")
    (path / "package.json").write_text('{"dependencies":{"next":"15"}}', encoding="utf-8")
    run("add", ".")
    run("commit", "-q", "-m", "초기 커밋")
    return path


def cli(home: Path, *args: str) -> int:
    return main(["--home", str(home), "--offline", *args])


def test_full_cli_journey(home: Path, project: Path, capsys) -> None:
    # 1. 아무것도 없는 상태
    assert cli(home, "list") == 0
    assert "등록된 프로젝트가 없습니다" in capsys.readouterr().out

    # 2. 등록 — 등록 이벤트가 비동기 스냅샷 수집을 일으킨다
    assert cli(home, "add", str(project), "--slug", "zun-app", "--purpose", "바이브 코딩") == 0
    output = capsys.readouterr().out
    assert "zun-app" in output
    assert "Next.js" in output  # package.json에서 감지
    assert "초기 커밋" in output  # git에서 감지

    # 3. 기억 주입
    assert cli(home, "remember", "zun-app", "릴스 소재로 좋다") == 0

    # 4. Context Pack
    assert cli(home, "context", "zun-app") == 0
    markdown = capsys.readouterr().out
    assert "## 목적" in markdown
    assert "바이브 코딩" in markdown
    assert "릴스 소재로 좋다" in markdown

    # 5. 검색
    assert cli(home, "search", "바이브") == 0
    assert "zun-app" in capsys.readouterr().out

    # 6. 상태 점검 — 밀린 이벤트가 없어야 한다
    assert cli(home, "doctor") == 0
    doctor = capsys.readouterr().out
    assert "프로젝트     : 1개" in doctor
    assert "미처리 이벤트: 0건" in doctor
    assert "deadletter   : 0건" in doctor


def test_search_miss_returns_nonzero(home: Path, project: Path, capsys) -> None:
    cli(home, "add", str(project), "--slug", "zun-app")
    capsys.readouterr()
    assert cli(home, "search", "존재하지않는단어") == 1


def test_unknown_project_reports_error(home: Path, capsys) -> None:
    assert cli(home, "context", "no-such-project") == 1
    assert "등록되지 않은" in capsys.readouterr().err


def test_state_persists_across_invocations(home: Path, project: Path, capsys) -> None:
    """CLI는 매번 새 프로세스다. 기억이 남아 있어야 의미가 있다."""
    cli(home, "add", str(project), "--slug", "zun-app")
    capsys.readouterr()

    assert cli(home, "list") == 0
    assert "zun-app" in capsys.readouterr().out


def test_refresh_all_projects(home: Path, project: Path, capsys) -> None:
    cli(home, "add", str(project), "--slug", "zun-app")
    capsys.readouterr()

    assert cli(home, "refresh") == 0  # slug 생략 = 전부
    assert "zun-app" in capsys.readouterr().out


# -- Creator Mode ------------------------------------------------------------


def test_adding_a_project_offers_a_reel(home: Path, project: Path, capsys) -> None:
    """브리프의 '이 프로젝트 릴스 만들까?'가 실제로 뜬다."""
    cli(home, "add", str(project), "--slug", "zun-app", "--name", "ZUN App")
    output = capsys.readouterr().out

    assert "릴스 만들까요?" in output
    assert "junvis reel --id" in output


def test_content_list_shows_the_suggestion(home: Path, project: Path, capsys) -> None:
    cli(home, "add", str(project), "--slug", "zun-app", "--name", "ZUN App")
    capsys.readouterr()

    assert cli(home, "content", "--status", "suggested") == 0
    assert "ZUN App 만든 과정" in capsys.readouterr().out


def test_dismiss_by_short_id(home: Path, project: Path, capsys) -> None:
    """32자 hex를 손으로 옮겨 적을 수는 없다. 앞 8자로 충분해야 한다."""
    cli(home, "add", str(project), "--slug", "zun-app", "--name", "ZUN App")
    capsys.readouterr()
    cli(home, "content")
    short_id = capsys.readouterr().out.split("(")[1].split(")")[0]

    assert cli(home, "dismiss", short_id) == 0
    assert "버렸습니다" in capsys.readouterr().out


def test_brand_voice_shows_and_updates(home: Path, capsys) -> None:
    assert cli(home, "brand") == 0
    assert "바이브 코딩" in capsys.readouterr().out

    assert cli(home, "brand", "--tone", "더 담백하게") == 0
    capsys.readouterr()
    assert cli(home, "brand") == 0
    assert "더 담백하게" in capsys.readouterr().out


def test_reel_without_ollama_fails_with_actionable_message(
    home: Path, monkeypatch, capsys
) -> None:
    """로컬 모델이 꺼져 있는 것은 흔한 상황이다. 무엇을 해야 할지 알려줘야 한다."""
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:1")

    assert cli(home, "reel", "테스트 주제") == 1
    assert "ollama serve" in capsys.readouterr().err


def test_reel_requires_subject_or_id(home: Path, capsys) -> None:
    assert cli(home, "reel") == 2
    assert "주제나 --id" in capsys.readouterr().err


# -- Daily Brief -------------------------------------------------------------


def test_brief_on_a_fresh_install(home: Path, capsys) -> None:
    assert cli(home, "brief") == 0
    assert "오늘 챙길 것이 없습니다" in capsys.readouterr().out


def test_brief_reports_projects_and_ideas(home: Path, project: Path, capsys) -> None:
    cli(home, "add", str(project), "--slug", "zun-app", "--name", "ZUN App")
    capsys.readouterr()

    assert cli(home, "brief") == 0
    output = capsys.readouterr().out

    assert "브리핑" in output
    assert "## 진행 중인 프로젝트" in output
    assert "## 대기 중인 아이디어" in output
    assert "ZUN App 만든 과정" in output
    assert "→ junvis reel --id" in output  # 바로 칠 수 있는 명령이 붙는다


def test_brief_notify_does_not_fail_off_macos(home: Path, capsys) -> None:
    """알림 전송 실패로 브리핑이 실패하지는 않는다."""
    assert cli(home, "brief", "--notify") == 0


# -- Voice -------------------------------------------------------------------


def test_listen_over_stdin(home: Path, project: Path, monkeypatch, capsys) -> None:
    """오디오 스택 없이도 판단 파이프라인 전체가 동작한다."""
    import io
    import sys

    cli(home, "add", str(project), "--slug", "zun-app", "--name", "ZUN App")
    capsys.readouterr()

    # Ollama가 없으므로 Intent Judge는 fail-open으로 통과한다.
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:1")
    monkeypatch.setattr(
        sys, "stdin", io.StringIO("점심 뭐 먹지\n자비스 프로젝트 목록\n")
    )

    assert cli(home, "listen", "--stdin", "--quiet") == 0
    captured = capsys.readouterr()

    assert "ZUN App" in captured.out  # 명령이 실행됐다
    assert "호출어 없음" in captured.err  # 첫 줄은 무시됐다


def test_say_off_macos_reports_failure(home: Path, capsys) -> None:
    assert cli(home, "say", "안녕하세요") == 1
    assert "소리를 내지 못했습니다" in capsys.readouterr().err


# -- 외부 MCP 서버 ------------------------------------------------------------


def _fixture_server_args() -> list[str]:
    import sys

    script = Path(__file__).resolve().parent / "fixture_mcp_server.py"
    return [sys.executable, str(script)]


def test_mcp_add_list_tools_and_call(home: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[2] / "src"))
    executable, script = _fixture_server_args()

    assert cli(home, "mcp", "add", "fixture", executable, script, "--trusted") == 0
    added = capsys.readouterr().out
    assert "등록했습니다: fixture" in added
    assert "도구 3개" in added

    assert cli(home, "mcp", "list") == 0
    assert "fixture" in capsys.readouterr().out

    assert cli(home, "mcp", "tools", "계산기") == 0
    assert "fixture.add_numbers" in capsys.readouterr().out

    assert cli(home, "mcp", "call", "fixture", "echo", "--args", '{"text":"안녕"}') == 0
    assert "안녕" in capsys.readouterr().out


def test_mcp_add_does_not_shadow_the_top_level_command(home: Path, capsys) -> None:
    """`mcp add`의 위치 인자 이름이 최상위 서브파서의 dest를 덮으면
    핸들러를 찾지 못해 조용히 exit 2가 난다. 실제로 겪은 버그다."""
    from junvis.apps.cli.main import build_parser

    namespace = build_parser().parse_args(["mcp", "add", "x", "/bin/echo"])
    assert namespace.command == "mcp"
    assert namespace.mcp_command == "add"
    assert namespace.executable == "/bin/echo"


def test_mcp_call_on_unknown_server_reports_error(home: Path, capsys) -> None:
    assert cli(home, "mcp", "call", "없는서버", "echo") == 1
    assert "등록되지 않은 서버" in capsys.readouterr().err


def test_mcp_remove(home: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[2] / "src"))
    executable, script = _fixture_server_args()
    cli(home, "mcp", "add", "fixture", executable, script)
    capsys.readouterr()

    assert cli(home, "mcp", "remove", "fixture") == 0
    assert cli(home, "mcp", "list") == 0
    assert "등록된 서버가 없습니다" in capsys.readouterr().out


def test_mcp_remove_unknown(home: Path, capsys) -> None:
    assert cli(home, "mcp", "remove", "없음") == 1


def test_listen_without_audio_tools_explains_what_is_missing(
    home: Path, capsys
) -> None:
    """말을 걸고 나서 도구가 없다는 걸 알면 늦다."""
    assert cli(home, "listen") == 1
    error = capsys.readouterr().err
    assert "brew install" in error or "Whisper 모델" in error
    assert "--stdin" in error or "Whisper 모델" in error


def test_listen_native_without_helper_points_at_the_build_script(
    home: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("JUNVIS_MAC_BIN", "junvis-mac-없음")

    assert cli(home, "listen", "--native") == 1
    assert "build-mac.sh" in capsys.readouterr().err


def test_listen_native_uses_the_configured_wake_words(
    home: Path, monkeypatch, capsys
) -> None:
    """헬퍼와 게이트가 다른 호출어를 들으면 깨워도 무시된다."""
    from junvis.features.voice.infrastructure import native_source

    spawned: list[list[str]] = []
    monkeypatch.setattr(native_source.shutil, "which", lambda _: "/usr/bin/true")

    def record(self):
        spawned.append(self.command())
        return iter(())

    monkeypatch.setattr(native_source.NativeHelperSource, "listen", record)

    assert cli(home, "listen", "--native") == 0
    assert "박수 두 번" in capsys.readouterr().err

    [command] = spawned
    assert command[command.index("--wake") + 1] == "준비스,자비스,junvis,jarvis"
