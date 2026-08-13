"""첫 실행 안내와 등록 실패 롤백.

여기 있는 것들은 전부 "처음 써 보는 사람이 걸려 넘어지는 지점"이다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from junvis.apps.cli.main import main
from junvis.features.brief.infrastructure.calendar_adapter import (
    MacCalendarAdapter,
    calendar_enabled,
)


@pytest.fixture()
def home(tmp_path: Path) -> Path:
    return tmp_path / "home"


def cli(home: Path, *args: str, cwd: Path | None = None) -> int:
    return main(["--home", str(home), "--offline", *args])


# -- setup 점검 --------------------------------------------------------------


def test_setup_reports_every_area(home: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:1")
    assert cli(home, "setup") == 0

    output = capsys.readouterr().out
    for area in ["코어", "두뇌", "음성", "캘린더", "Claude Code"]:
        assert area in output


def test_setup_tells_you_what_to_type(home: Path, capsys, monkeypatch) -> None:
    """무엇이 없다고만 하면 도움이 되지 않는다."""
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:1")
    monkeypatch.delenv("JUNVIS_WHISPER_MODEL", raising=False)
    cli(home, "setup")

    output = capsys.readouterr().out
    assert "할 일:" in output
    assert "brew install ollama" in output
    assert "JUNVIS_WHISPER_MODEL" in output


def test_setup_changes_nothing(home: Path, tmp_path, monkeypatch, capsys) -> None:
    """점검이 무언가를 고치기 시작하면 점검을 믿을 수 없게 된다."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:1")

    cli(home, "setup")

    assert not (tmp_path / ".mcp.json").exists()


# -- Claude Code 등록 --------------------------------------------------------


def _fake_junvis_mcp(tmp_path: Path, monkeypatch) -> None:
    """`junvis-mcp`가 PATH에 있는 상황을 만든다."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    binary = bin_dir / "junvis-mcp"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))


def test_claude_code_registration(home: Path, tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    _fake_junvis_mcp(tmp_path, monkeypatch)

    assert cli(home, "setup", "--claude-code") == 0

    config = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert config["mcpServers"]["junvis"]["command"].endswith("junvis-mcp")
    # 기본 홈이 아니면 그 경로를 함께 심는다
    assert config["mcpServers"]["junvis"]["env"]["JUNVIS_HOME"] == str(home)


def test_claude_code_registration_keeps_other_servers(
    home: Path, tmp_path, monkeypatch, capsys
) -> None:
    """남의 설정을 덮어쓰는 도구는 신뢰를 잃는다."""
    monkeypatch.chdir(tmp_path)
    _fake_junvis_mcp(tmp_path, monkeypatch)
    (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"other": {"command": "x"}}}), encoding="utf-8"
    )

    cli(home, "setup", "--claude-code")

    config = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert set(config["mcpServers"]) == {"other", "junvis"}


def test_claude_code_registration_is_idempotent(
    home: Path, tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    _fake_junvis_mcp(tmp_path, monkeypatch)

    cli(home, "setup", "--claude-code")
    capsys.readouterr()
    assert cli(home, "setup", "--claude-code") == 0
    assert "이미 등록" in capsys.readouterr().out


def test_claude_code_registration_without_the_binary(
    home: Path, tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "없는디렉터리"))

    assert cli(home, "setup", "--claude-code") == 1
    assert "uv pip install" in capsys.readouterr().err


# -- 등록 실패 롤백 ----------------------------------------------------------


def test_broken_server_is_not_persisted(home: Path, capsys) -> None:
    """먼저 저장하면 깨진 서버가 설정에 남아 이후 모든 실행이 안고 간다."""
    assert cli(home, "mcp", "add", "bad", "/bin/echo") == 1
    assert "등록하지 않았습니다" in capsys.readouterr().err

    assert not (home / "mcp.json").exists()
    assert cli(home, "mcp", "list") == 0
    assert "등록된 서버가 없습니다" in capsys.readouterr().out


def test_working_server_is_persisted(home: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[2] / "src"))
    script = Path(__file__).resolve().parent / "fixture_mcp_server.py"

    assert cli(home, "mcp", "add", "fixture", sys.executable, str(script)) == 0
    assert "도구 3개" in capsys.readouterr().out
    assert "fixture" in (home / "mcp.json").read_text(encoding="utf-8")


# -- 캘린더 기본값 -----------------------------------------------------------


def test_calendar_is_off_by_default(monkeypatch) -> None:
    """launchd가 매일 아침 도는데 거기서 권한 대화상자를 기다리면 안 된다."""
    monkeypatch.delenv("JUNVIS_CALENDAR", raising=False)
    assert calendar_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on"])
def test_calendar_can_be_enabled(monkeypatch, value: str) -> None:
    monkeypatch.setenv("JUNVIS_CALENDAR", value)
    assert calendar_enabled() is True


@pytest.mark.parametrize("value", ["", "0", "false", "no"])
def test_calendar_stays_off_for_falsey_values(monkeypatch, value: str) -> None:
    monkeypatch.setenv("JUNVIS_CALENDAR", value)
    assert calendar_enabled() is False


def test_disabled_calendar_never_shells_out(monkeypatch) -> None:
    monkeypatch.delenv("JUNVIS_CALENDAR", raising=False)
    monkeypatch.setattr(
        MacCalendarAdapter,
        "_run",
        lambda self: pytest.fail("꺼져 있는데 osascript를 불렀다"),
    )
    from datetime import datetime, timezone

    assert MacCalendarAdapter().today(datetime.now(timezone.utc)) == ()
