"""JUNVIS CLI.

argparse만 쓴다. 의존성을 하나 줄이면 macOS에서 설치가 하나 쉬워진다.

명령은 기능별 모듈이 소유한다. 각 모듈이 자기 파서와 핸들러를 함께 내놓아,
명령을 추가할 때 이 파일을 고칠 일이 없다(OCP).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from junvis.apps.cli.commands import creator, external, knowledge, ops, project, voice
from junvis.apps.cli.confirm import TerminalConfirmer
from junvis.apps.container import build
from junvis.core.domain.errors import JunvisError
from junvis.features.voice.infrastructure.tts import NullTts

#: 등록 순서가 `--help`에 나오는 순서다. 자주 쓰는 것부터.
COMMAND_MODULES = (project, creator, knowledge, voice, external, ops)


def _assemble() -> tuple[argparse.ArgumentParser, dict]:
    parser = argparse.ArgumentParser(prog="junvis", description="JUNVIS — 개인 AI OS")
    parser.add_argument("--home", type=Path, help="JUNVIS 홈 (기본: ~/.junvis)")
    parser.add_argument("--offline", action="store_true", help="네트워크 조회를 건너뛴다")
    parser.add_argument("-y", "--yes", action="store_true", help="확인 요구를 자동 승인한다")
    sub = parser.add_subparsers(dest="command", required=True)

    handlers: dict = {}
    for module in COMMAND_MODULES:
        registered = module.register(sub)
        collision = handlers.keys() & registered.keys()
        if collision:
            raise RuntimeError(f"명령 이름이 겹칩니다: {', '.join(sorted(collision))}")
        handlers.update(registered)
    return parser, handlers


def build_parser() -> argparse.ArgumentParser:
    return _assemble()[0]


def main(argv: list[str] | None = None) -> int:
    parser, handlers = _assemble()
    args = parser.parse_args(argv)

    container = build(
        args.home,
        confirmer=TerminalConfirmer(assume_yes=args.yes),
        offline=args.offline,
        tts=NullTts() if getattr(args, "quiet", False) else None,
    )
    try:
        handler = handlers.get(args.command)
        return handler(args, container) if handler else 2
    except JunvisError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    finally:
        container.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
