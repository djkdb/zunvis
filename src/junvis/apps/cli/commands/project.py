"""Project Brain 명령."""

from __future__ import annotations

import sys
from pathlib import Path

from junvis.apps.cli.render import print_project
from junvis.apps.container import Junvis
from junvis.core.domain.errors import JunvisError
from junvis.features.project_brain.application.dto import RegisterProjectCommand
from junvis.features.project_brain.infrastructure.discovery import (
    DEFAULT_DEPTH,
    find_git_repositories,
)
from junvis.features.project_brain.infrastructure.github_repos import (
    GitHubRepositoryLister,
    GitHubUnavailable,
    sort_key,
)


def register(sub) -> dict:
    add = sub.add_parser("add", help="프로젝트를 등록하거나 갱신한다")
    add.add_argument("path", nargs="?", type=Path, default=Path("."), help="프로젝트 경로")
    add.add_argument("--slug")
    add.add_argument("--name")
    add.add_argument("--purpose", default="")
    add.add_argument("--architecture", default="", dest="architecture_note")

    scan = sub.add_parser("scan", help="git 저장소를 한 번에 등록한다 (디스크 또는 GitHub)")
    scan.add_argument("root", nargs="?", type=Path, default=Path("."), help="찾기 시작할 폴더")
    scan.add_argument("--depth", type=int, default=DEFAULT_DEPTH, help="몇 단계까지 내려갈지")
    scan.add_argument(
        "--github",
        nargs="?",
        const="",
        metavar="사용자이름",
        help="디스크 대신 GitHub 프로필에서 가져온다 (이름을 생략하면 내 계정)",
    )
    scan.add_argument("--forks", action="store_true", help="포크한 저장소도 포함한다")
    scan.add_argument("--archived", action="store_true", help="보관된 저장소도 포함한다")
    scan.add_argument("--dry-run", action="store_true", help="등록하지 않고 찾은 것만 보여준다")

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

    return {
        "add": cmd_add,
        "scan": cmd_scan,
        "list": cmd_list,
        "context": cmd_context,
        "search": cmd_search,
        "remember": cmd_remember,
        "refresh": cmd_refresh,
    }


def cmd_scan(args, junvis: Junvis) -> int:
    """git 저장소를 한 번에 등록한다.

    하나씩 손으로 등록하는 것은 시작하는 데 드는 비용이다. 아무것도 모르는
    JUNVIS는 브리핑도 릴스 제안도 빈손이라, 첫 걸음이 가벼워야 기능이 산다.
    """
    if args.github is not None:
        return _scan_github(args, junvis)
    return _scan_disk(args, junvis)


def _scan_github(args, junvis: Junvis) -> int:
    """GitHub 프로필의 저장소를 등록한다.

    디스크에 없는 것까지 가져온다 — 클론하지 않은 것, 다른 컴퓨터에서 만든
    것, 지운 것. 그것들도 "그때 그거 어떻게 됐지"의 대상이다.
    """
    lister = GitHubRepositoryLister()
    try:
        repos = lister.list_repositories(args.github or None)
    except GitHubUnavailable as exc:
        print(f"{exc}", file=sys.stderr)
        return 1

    total = len(repos)
    if not args.forks:
        repos = [repo for repo in repos if not repo.fork]
    if not args.archived:
        repos = [repo for repo in repos if not repo.archived]
    repos.sort(key=sort_key, reverse=True)

    if not repos:
        print("가져올 저장소가 없습니다.", file=sys.stderr)
        if total:
            print(f"  포크·보관된 것 {total}개는 건너뛰었습니다."
                  " 포함하려면 --forks --archived", file=sys.stderr)
        return 1

    known = {
        s.repo_full_name for s in junvis.projects.list_all() if s.repo_full_name
    }
    fresh = [repo for repo in repos if repo.full_name not in known]

    where = f"{args.github}님의" if args.github else "내"
    skipped = total - len(repos)
    note = f", 포크·보관 {skipped}개 제외" if skipped else ""
    print(f"{where} GitHub 저장소 {len(repos)}개{note} (새 것 {len(fresh)}개).\n")

    if args.dry_run:
        for repo in repos:
            mark = " " if repo.full_name in known else "+"
            lock = " 🔒" if repo.private else ""
            print(f"  {mark} {repo.full_name}{lock}  {repo.description[:60]}")
        print("\n등록하려면 --dry-run 없이 다시 실행하세요.")
        return 0

    return _register_all(
        junvis,
        [
            RegisterProjectCommand(
                name=repo.name,
                purpose=repo.description,
                remote_url=repo.clone_url,
            )
            for repo in fresh
        ],
        labels=[repo.full_name for repo in fresh],
    )


def _scan_disk(args, junvis: Junvis) -> int:
    found = find_git_repositories(args.root, depth=args.depth)
    if not found:
        print(f"{args.root} 아래에서 git 저장소를 찾지 못했습니다.", file=sys.stderr)
        print(f"  더 깊이 찾으려면: junvis scan {args.root} --depth 5", file=sys.stderr)
        return 1

    known = {s.local_path for s in junvis.projects.list_all() if s.local_path}
    fresh = [path for path in found if str(path) not in known]

    print(f"git 저장소 {len(found)}개를 찾았습니다 (새 것 {len(fresh)}개).\n")
    if args.dry_run:
        for path in found:
            mark = " " if str(path) in known else "+"
            print(f"  {mark} {path}")
        print("\n등록하려면 --dry-run 없이 다시 실행하세요.")
        return 0

    return _register_all(
        junvis,
        [RegisterProjectCommand(path=path) for path in fresh],
        labels=[path.name for path in fresh],
    )


def _register_all(junvis: Junvis, commands, *, labels) -> int:
    """하나가 실패해도 나머지는 등록한다. 이름이 이상한 것은 흔하다."""
    registered, failed = [], []
    for command, label in zip(commands, labels):
        try:
            registered.append(junvis.projects.register(command))
        except JunvisError as exc:
            failed.append((label, exc))
    junvis.drain()  # 스냅샷 수집과 콘텐츠 제안

    for summary in registered:
        print(f"  + {summary.slug}  {summary.name}")
    for label, exc in failed:
        print(f"  ! {label}: {exc}", file=sys.stderr)

    if registered:
        print(f"\n{len(registered)}개를 등록했습니다. `junvis brief` 로 확인하세요.")
    elif not failed:
        print("전부 이미 등록되어 있습니다.")
    return 0


def cmd_add(args, junvis: Junvis) -> int:
    summary = junvis.projects.register(
        RegisterProjectCommand(
            name=args.name,
            slug=args.slug,
            path=args.path,
            purpose=args.purpose,
            architecture_note=args.architecture_note,
        )
    )
    junvis.drain()  # 스냅샷 수집과 콘텐츠 제안을 여기서 처리한다
    latest = next(
        (s for s in junvis.projects.list_all() if s.slug == summary.slug), summary
    )
    print_project(latest)

    suggestions = [
        c
        for c in junvis.creator.list_all(status="suggested")
        if c.source_project_slug == summary.slug
    ]
    if suggestions:
        print()
        print(f'제안: "{suggestions[0].subject}" 릴스 만들까요?')
        print(f"  → junvis reel --id {suggestions[0].id[:8]}")
    return 0


def cmd_list(_args, junvis: Junvis) -> int:
    summaries = junvis.projects.list_all()
    if not summaries:
        print("등록된 프로젝트가 없습니다. `junvis add <경로>` 로 시작하세요.")
        return 0
    for summary in summaries:
        print_project(summary)
        print()
    return 0


def cmd_context(args, junvis: Junvis) -> int:
    print(junvis.projects.load_context(args.slug, budget_tokens=args.budget).to_markdown())
    return 0


def cmd_search(args, junvis: Junvis) -> int:
    hits = junvis.projects.search(args.query, limit=args.limit)
    if not hits:
        print("검색 결과가 없습니다.")
        return 1
    for summary in hits:
        print_project(summary)
        print()
    return 0


def cmd_remember(args, junvis: Junvis) -> int:
    summary = junvis.projects.remember(args.slug, args.text)
    print(f"기억했습니다. ({summary.slug}, 메모 {summary.note_count}건)")
    return 0


def cmd_refresh(args, junvis: Junvis) -> int:
    slugs = [args.slug] if args.slug else [s.slug for s in junvis.projects.list_all()]
    if not slugs:
        print("등록된 프로젝트가 없습니다.", file=sys.stderr)
        return 1
    for slug in slugs:
        print_project(junvis.projects.refresh(slug))
    return 0
