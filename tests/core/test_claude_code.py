"""Claude Code CLI 어댑터.

진짜 `claude`를 부르지 않는다. 가짜 실행 파일을 PATH에 놓고 계약만 본다 —
어떤 인자로 부르는지, stdout을 어떻게 읽는지, 실패를 어떻게 말하는지.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from junvis.core.model.claude_code import FORBIDDEN_TOOLS, ClaudeCodeAdapter
from junvis.core.model.ports import ModelError, ModelRequest

SCHEMA = {"type": "object", "properties": {"hook": {"type": "string"}}}


@pytest.fixture(autouse=True)
def _allow_claude(monkeypatch) -> None:
    """이 파일은 어댑터 자체를 본다. 전역 차단 픽스처를 덮는다."""
    monkeypatch.delenv("JUNVIS_BRAIN", raising=False)


def fake_claude(tmp_path: Path, script: str) -> ClaudeCodeAdapter:
    binary = tmp_path / "claude"
    binary.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    os.environ["PATH"] = f"{tmp_path}{os.pathsep}{os.environ['PATH']}"
    return ClaudeCodeAdapter(binary=str(binary))


def test_the_answer_comes_from_stdout(tmp_path: Path) -> None:
    claude = fake_claude(tmp_path, 'echo "그렇게 하시면 좋겠습니다."')

    assert claude.complete(ModelRequest(prompt="뭐 할까")).text == "그렇게 하시면 좋겠습니다."


def test_the_prompt_goes_over_stdin(tmp_path: Path) -> None:
    """따옴표·개행·한글이 섞인 긴 프롬프트를 인자로 넘기면 깨진다."""
    claude = fake_claude(tmp_path, "cat")

    answer = claude.complete(ModelRequest(prompt='그가 "안녕"이라 했다\n두 번째 줄'))

    assert answer.text == '그가 "안녕"이라 했다\n두 번째 줄'


def test_the_system_prompt_is_appended(tmp_path: Path) -> None:
    claude = fake_claude(tmp_path, 'printf "%s" "$*"')

    answer = claude.complete(ModelRequest(prompt="안녕", system="너는 JUNVIS다"))

    assert "--append-system-prompt 너는 JUNVIS다" in answer.text


def test_file_changing_tools_are_forbidden() -> None:
    """음성은 오인식이 잦다. 말 한마디로 파일이 바뀌면 안 된다."""
    command = ClaudeCodeAdapter().command()

    assert "--disallowed-tools" in command
    for tool in ("Bash", "Edit", "Write"):
        assert tool in command
    assert set(FORBIDDEN_TOOLS) <= set(command)


def test_a_failure_reports_what_claude_said(tmp_path: Path) -> None:
    claude = fake_claude(tmp_path, 'echo "로그인이 필요합니다" >&2; exit 1')

    with pytest.raises(ModelError, match="로그인이 필요합니다"):
        claude.complete(ModelRequest(prompt="안녕"))


def test_an_empty_answer_is_an_error(tmp_path: Path) -> None:
    """조용히 빈 문자열을 돌려주면 사용자는 자기 말이 안 들린 줄 안다."""
    claude = fake_claude(tmp_path, "true")

    with pytest.raises(ModelError, match="빈 답"):
        claude.complete(ModelRequest(prompt="안녕"))


def test_a_hang_is_cut_off(tmp_path: Path) -> None:
    claude = fake_claude(tmp_path, "sleep 5")
    claude._timeout = 1

    with pytest.raises(ModelError, match="안에 답하지 않았습니다"):
        claude.complete(ModelRequest(prompt="안녕"))


def test_a_missing_binary_says_where_to_get_it() -> None:
    claude = ClaudeCodeAdapter(binary="claude-없음")

    assert not claude.is_available()
    with pytest.raises(ModelError, match="claude-code"):
        claude.complete(ModelRequest(prompt="안녕"))


# -- 구조화 출력: CLI에는 스키마 통로가 없다 ----------------------------------


def test_json_is_requested_in_the_prompt(tmp_path: Path) -> None:
    claude = fake_claude(tmp_path, 'cat >/dev/null; echo \'{"hook":"좋다"}\'')

    answer = claude.complete(ModelRequest(prompt="릴스", schema=SCHEMA))

    assert json.loads(answer.text) == {"hook": "좋다"}


def test_a_code_fence_is_stripped(tmp_path: Path) -> None:
    """부탁해도 모델은 코드펜스를 붙인다."""
    claude = fake_claude(
        tmp_path, 'cat >/dev/null; printf \'```json\\n{"hook":"좋다"}\\n```\\n\''
    )

    assert json.loads(claude.complete(ModelRequest(prompt="릴스", schema=SCHEMA)).text)


def test_chatter_around_the_json_is_stripped(tmp_path: Path) -> None:
    claude = fake_claude(
        tmp_path, 'cat >/dev/null; echo \'네, 만들었습니다: {"hook":"좋다"} 어떠신가요?\''
    )

    answer = claude.complete(ModelRequest(prompt="릴스", schema=SCHEMA))

    assert json.loads(answer.text) == {"hook": "좋다"}


def test_braces_inside_strings_do_not_confuse_the_parser(tmp_path: Path) -> None:
    claude = fake_claude(
        tmp_path, 'cat >/dev/null; echo \'{"hook":"중괄호 } 가 들어간 문구"}\''
    )

    answer = claude.complete(ModelRequest(prompt="릴스", schema=SCHEMA))

    assert json.loads(answer.text)["hook"] == "중괄호 } 가 들어간 문구"


def test_no_json_at_all_is_an_error(tmp_path: Path) -> None:
    claude = fake_claude(tmp_path, 'cat >/dev/null; echo "못 하겠습니다"')

    with pytest.raises(ModelError, match="JSON을 찾지 못했습니다"):
        claude.complete(ModelRequest(prompt="릴스", schema=SCHEMA))
