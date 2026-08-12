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
