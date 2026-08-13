"""첫 실행 안내.

`junvis doctor`가 "지금 상태"를 보여준다면, `junvis setup`은 "무엇을 해야
하는가"를 보여준다. 되는 것과 안 되는 것을 구분하고, 안 되는 것마다
정확히 무엇을 치면 되는지 알려준다.

이 명령은 아무것도 바꾸지 않는다(`--claude-code`로 MCP 설정을 쓸 때만 예외).
점검이 무언가를 고치기 시작하면 점검을 믿을 수 없게 된다.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from pathlib import Path

from junvis.apps.container import Junvis
from junvis.core.model.claude_code import ClaudeCodeAdapter
from junvis.features.brief.infrastructure.calendar_adapter import (
    ENABLE_ENV,
    calendar_enabled,
)
from junvis.features.voice.infrastructure.audio import (
    WHISPER_MODEL_ENV,
    DEFAULT_WHISPER_BIN,
)
from junvis.features.voice.infrastructure.apple_speech import (
    available as apple_speech_available,
)
from junvis.features.voice.infrastructure.native_source import (
    DEFAULT_HELPER,
    HELPER_BIN_ENV,
)

OK = "✓"
MISSING = "·"
WARN = "!"

#: Claude Code가 읽는 설정 파일 후보. 프로젝트 것이 사용자 것을 이긴다.
CLAUDE_PROJECT_CONFIG = Path(".mcp.json")


def register(sub) -> dict:
    setup = sub.add_parser("setup", help="첫 실행 점검과 안내")
    setup.add_argument(
        "--claude-code",
        action="store_true",
        help="현재 디렉터리의 .mcp.json에 JUNVIS를 등록한다",
    )
    return {"setup": cmd_setup}


def cmd_setup(args, junvis: Junvis) -> int:
    if args.claude_code:
        return _write_claude_config(junvis)

    print(f"JUNVIS 홈: {junvis.home}\n")
    todos: list[str] = []

    _core(junvis)
    _model(junvis, todos)
    _voice(todos)
    _calendar(todos)
    _claude_code(junvis, todos)

    print()
    if not todos:
        print("전부 준비됐습니다. `junvis add .` 로 시작하세요.")
        return 0

    print("할 일:")
    for index, todo in enumerate(todos, start=1):
        print(f"  {index}. {todo}")
    print("\n지금 안 해도 나머지 기능은 동작합니다.")
    return 0


# -- 각 영역 -----------------------------------------------------------------


def _core(junvis: Junvis) -> None:
    print("코어")
    print(f"  {OK} Python {platform.python_version()}")
    print(f"  {OK} 데이터베이스 {junvis.db.path}")
    if platform.system() == "Darwin":
        print(f"  {OK} macOS {platform.mac_ver()[0]}")
    else:
        print(f"  {WARN} {platform.system()} — macOS 전용 기능은 조용히 꺼집니다")


def _model(junvis: Junvis, todos: list[str]) -> None:
    print("\n두뇌 (대화·릴스 생성·음성 판정)")

    if isinstance(junvis.model, ClaudeCodeAdapter):
        print(f"  {OK} Claude Code CLI — 이미 로그인돼 있어 따로 설치할 것이 없습니다")
        return

    claude = ClaudeCodeAdapter()
    if claude.is_available():
        print(f"  {OK} 대화는 Claude Code CLI가 맡습니다")
    else:
        print(f"  {MISSING} Claude Code CLI 없음 — 대화 품질이 가장 좋은 선택지입니다")
        todos.append(
            "Claude Code 설치: https://claude.com/claude-code"
            " — 대화에 Ollama보다 낫고 따로 모델을 받을 필요가 없습니다"
        )

    available = getattr(junvis.model, "is_available", None)
    if available is None or not available():
        print(f"  {MISSING} Ollama에 연결할 수 없습니다 (음성 판정용)")
        todos.append("Ollama 설치 후 실행: brew install ollama && ollama serve")
        return

    installed = set(junvis.model.installed_models())
    print(f"  {OK} Ollama 연결됨")
    for role in ("FAST", "DEEP"):
        from junvis.core.model.ports import ModelRole

        wanted = junvis.model.model_for(ModelRole[role])
        if wanted in installed:
            print(f"  {OK} {role.lower()} 모델: {wanted}")
        else:
            print(f"  {MISSING} {role.lower()} 모델 없음: {wanted}")
            todos.append(f"모델 내려받기: ollama pull {wanted}")


def _voice(todos: list[str]) -> None:
    print("\n음성 (`junvis listen`)")
    missing = [name for name in ("sox", DEFAULT_WHISPER_BIN) if not shutil.which(name)]
    model = os.environ.get(WHISPER_MODEL_ENV, "")

    if missing:
        print(f"  {MISSING} 없는 도구: {', '.join(missing)}")
        todos.append("음성 입력 도구 설치: brew install sox whisper-cpp")
    else:
        print(f"  {OK} sox, {DEFAULT_WHISPER_BIN}")

    if model and Path(model).is_file():
        print(f"  {OK} Whisper 모델: {model}")
    else:
        print(f"  {MISSING} Whisper 모델 미설정")
        todos.append(
            f"Whisper 모델 경로 지정: export {WHISPER_MODEL_ENV}=~/models/ggml-base.bin"
        )

    if platform.system() == "Darwin":
        print(f"  {OK} 말하기: macOS `say` (설치 불필요)")
        _native_helper(todos)
    print("     ※ 도구가 없어도 `junvis listen --stdin` 은 동작합니다")


def _native_helper(todos: list[str]) -> None:
    """상시 대기와 박수는 sox/whisper로 안 된다.

    맥 내장 음성 인식이 필요하고, 그건 PyObjC 설치 한 줄이면 된다.
    Swift 헬퍼도 같은 일을 하지만 컴파일러가 필요해 뒤로 뺀다.
    """
    if apple_speech_available():
        print(f"  {OK} 맥 내장 음성 인식 — `junvis listen --native`")
        return

    binary = os.environ.get(HELPER_BIN_ENV) or DEFAULT_HELPER
    if shutil.which(binary):
        print(f"  {OK} 네이티브 헬퍼: {binary} — `junvis listen --native`")
        return

    print(f"  {MISSING} 상시 대기·박수를 쓸 수 없습니다")
    todos.append('맥 내장 음성 인식 켜기: uv pip install -e ".[mac]" — 박수 두 번까지 됩니다')


def _calendar(todos: list[str]) -> None:
    print("\n캘린더 (브리핑의 '오늘 일정')")
    if calendar_enabled():
        print(f"  {OK} 켜짐 — 첫 조회에서 Calendar.app 권한을 물어봅니다")
    else:
        print(f"  {MISSING} 꺼짐 (기본값)")
        todos.append(
            f"일정을 브리핑에 넣으려면: export {ENABLE_ENV}=1"
            " — 느리고 권한이 필요해 기본은 꺼져 있습니다"
        )


def _claude_code(junvis: Junvis, todos: list[str]) -> None:
    print("\nClaude Code 연결")
    binary = shutil.which("junvis-mcp")
    if binary:
        print(f"  {OK} junvis-mcp: {binary}")
    else:
        print(f"  {MISSING} junvis-mcp를 PATH에서 찾지 못했습니다")
        todos.append("설치 확인: uv pip install -e .")

    if CLAUDE_PROJECT_CONFIG.is_file() and "junvis" in CLAUDE_PROJECT_CONFIG.read_text(
        encoding="utf-8", errors="replace"
    ):
        print(f"  {OK} {CLAUDE_PROJECT_CONFIG}에 등록됨")
    else:
        print(f"  {MISSING} {CLAUDE_PROJECT_CONFIG}에 등록되지 않음")
        todos.append("Claude Code에 등록: junvis setup --claude-code")

    servers = junvis.mcp.servers
    if servers:
        print(f"  {OK} 외부 MCP 서버 {len(servers)}개")


# -- 설정 쓰기 ---------------------------------------------------------------


def _write_claude_config(junvis: Junvis) -> int:
    """현재 디렉터리의 `.mcp.json`에 JUNVIS를 더한다.

    기존 항목은 건드리지 않는다. 남의 설정을 덮어쓰는 도구는 신뢰를 잃는다.
    """
    binary = shutil.which("junvis-mcp")
    if not binary:
        print("junvis-mcp를 찾지 못했습니다. `uv pip install -e .` 를 먼저 하세요.", file=sys.stderr)
        return 1

    payload: dict = {}
    if CLAUDE_PROJECT_CONFIG.is_file():
        try:
            payload = json.loads(CLAUDE_PROJECT_CONFIG.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"{CLAUDE_PROJECT_CONFIG}를 읽지 못했습니다: {exc}", file=sys.stderr)
            return 1

    servers = payload.setdefault("mcpServers", {})
    if "junvis" in servers:
        print(f"이미 등록되어 있습니다: {CLAUDE_PROJECT_CONFIG}")
        return 0

    entry: dict = {"command": binary}
    if junvis.home != Path.home() / ".junvis":
        entry["env"] = {"JUNVIS_HOME": str(junvis.home)}
    servers["junvis"] = entry

    CLAUDE_PROJECT_CONFIG.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"등록했습니다: {CLAUDE_PROJECT_CONFIG}")
    print("Claude Code를 다시 시작하면 junvis_* 도구가 보입니다.")
    return 0
