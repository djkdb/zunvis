"""JUNVIS CLI (M10).

argparse만 쓴다. 의존성을 하나 줄이면 macOS에서 설치가 하나 쉬워진다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from junvis.apps.cli.confirm import TerminalConfirmer
from junvis.apps.container import build
from junvis.core.domain.errors import JunvisError
from junvis.features.project_brain.application.dto import (
    ProjectSummary,
    RegisterProjectCommand,
)


def _print_summary(summary: ProjectSummary) -> None:
    print(f"{summary.slug} — {summary.name}")
    if summary.purpose:
        print(f"  목적   : {summary.purpose}")
    if summary.repo_full_name:
        print(f"  저장소 : {summary.repo_full_name}")
    if summary.tech_stack:
        print(f"  스택   : {', '.join(summary.tech_stack)}")
    if summary.branch:
        print(f"  브랜치 : {summary.branch}{' (변경 있음)' if summary.dirty else ''}")
    if summary.last_commit:
        print(f"  최근   : {summary.last_commit}")
    if summary.open_todo_count:
        print(f"  TODO   : {summary.open_todo_count}건")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="junvis", description="JUNVIS — 개인 AI OS")
    parser.add_argument("--home", type=Path, help="JUNVIS 홈 (기본: ~/.junvis)")
    parser.add_argument("--offline", action="store_true", help="GitHub 조회를 건너뛴다")
    parser.add_argument("-y", "--yes", action="store_true", help="확인 요구를 자동 승인한다")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="프로젝트를 등록하거나 갱신한다")
    add.add_argument("path", nargs="?", type=Path, default=Path("."), help="프로젝트 경로")
    add.add_argument("--slug")
    add.add_argument("--name")
    add.add_argument("--purpose", default="")
    add.add_argument("--architecture", default="", dest="architecture_note")

    sub.add_parser("list", help="기억하고 있는 프로젝트를 나열한다")

    context = sub.add_parser("context", help="Context Pack을 출력한다")
    context.add_argument("slug")
    context.add_argument("--budget", type=int, default=2000, help="토큰 예산")

    search = sub.add_parser("search", help="프로젝트를 전문 검색한다")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)

    remember = sub.add_parser("remember", help="프로젝트에 대해 기억해둔다")
    remember.add_argument("slug")
    remember.add_argument("text")

    refresh = sub.add_parser("refresh", help="스냅샷을 다시 수집한다")
    refresh.add_argument("slug", nargs="?", help="생략하면 전부 갱신한다")

    sub.add_parser("drain", help="밀린 비동기 이벤트를 처리한다")
    sub.add_parser("doctor", help="상태를 점검한다")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    container = build(
        args.home, confirmer=TerminalConfirmer(assume_yes=args.yes), offline=args.offline
    )
    try:
        return _dispatch(args, container)
    except JunvisError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    finally:
        container.close()


def _dispatch(args: argparse.Namespace, container) -> int:
    if args.command == "add":
        summary = container.register(
            RegisterProjectCommand(
                name=args.name,
                slug=args.slug,
                path=args.path,
                purpose=args.purpose,
                architecture_note=args.architecture_note,
            )
        )
        container.drain()  # 등록 직후 스냅샷 수집을 여기서 처리한다
        # 수집 결과가 반영된 최신 상태를 보여준다
        latest = next(
            (s for s in container.list_projects() if s.slug == summary.slug), summary
        )
        _print_summary(latest)
        return 0

    if args.command == "list":
        summaries = container.list_projects()
        if not summaries:
            print("등록된 프로젝트가 없습니다. `junvis add <경로>` 로 시작하세요.")
            return 0
        for summary in summaries:
            _print_summary(summary)
            print()
        return 0

    if args.command == "context":
        print(container.load_context(args.slug, budget_tokens=args.budget).to_markdown())
        return 0

    if args.command == "search":
        hits = container.search(args.query, limit=args.limit)
        if not hits:
            print("검색 결과가 없습니다.")
            return 1
        for summary in hits:
            _print_summary(summary)
            print()
        return 0

    if args.command == "remember":
        summary = container.remember(args.slug, args.text)
        print(f"기억했습니다. ({summary.slug}, 메모 {summary.note_count}건)")
        return 0

    if args.command == "refresh":
        slugs = [args.slug] if args.slug else [s.slug for s in container.list_projects()]
        for slug in slugs:
            _print_summary(container.refresh(slug))
        return 0

    if args.command == "drain":
        report = container.drain()
        print(
            f"처리 {report.processed}건, 재시도 {report.failed}건, "
            f"deadletter {report.deadlettered}건"
        )
        for error in report.errors:
            print(f"  - {error}", file=sys.stderr)
        return 0

    if args.command == "doctor":
        print(f"홈           : {container.home}")
        print(f"DB           : {container.db.path}")
        print(f"프로젝트     : {len(container.list_projects())}개")
        print(f"미처리 이벤트: {container.outbox.pending_count()}건")
        print(f"deadletter   : {container.outbox.deadletter_count()}건")
        return 0

    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
