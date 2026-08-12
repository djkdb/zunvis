"""Daily Brief와 Personal Memory 명령.

둘을 한 모듈에 둔 이유: 브리핑과 기억은 "JUNVIS가 아는 것"을 다루는
읽기 중심 명령이고, 각각 두세 개뿐이라 파일을 나눌 만큼 크지 않다.
"""

from __future__ import annotations

import sys

from junvis.apps.cli.render import print_memory
from junvis.apps.container import Junvis
from junvis.features.memory.domain.model import MemoryScope

SCOPES = [scope.value for scope in MemoryScope]


def register(sub) -> dict:
    brief = sub.add_parser("brief", help="오늘의 브리핑")
    brief.add_argument(
        "--notify", action="store_true", help="macOS 알림으로 요약 한 줄 (launchd용)"
    )

    memo = sub.add_parser("memo", help="기억해둘 사실을 남긴다")
    memo.add_argument("text")
    memo.add_argument("--scope", choices=SCOPES, default=MemoryScope.USER.value)
    memo.add_argument("--subject", default="", help="프로젝트 slug 등")
    memo.add_argument("--pin", action="store_true", help="항상 우선 주입")

    memos = sub.add_parser("memos", help="기억을 회상하거나 전부 나열한다")
    memos.add_argument("query", nargs="?", default="")
    memos.add_argument("--scope", choices=SCOPES)
    memos.add_argument("--limit", type=int, default=50)

    forget = sub.add_parser("forget", help="기억을 지운다")
    forget.add_argument("id")

    return {
        "brief": cmd_brief,
        "memo": cmd_memo,
        "memos": cmd_memos,
        "forget": cmd_forget,
    }


def cmd_brief(args, junvis: Junvis) -> int:
    briefing = junvis.brief.compose()
    print(briefing.to_markdown())
    if args.notify:
        # 알림 전송 실패(macOS가 아니거나 권한 없음)로 브리핑이 실패하지는 않는다.
        from junvis.features.brief.infrastructure.notifier import notify

        notify(briefing.headline(), subtitle=f"{briefing.day.isoformat()} 브리핑")
    return 0


def cmd_memo(args, junvis: Junvis) -> int:
    view = junvis.memory.remember(
        args.text,
        scope=MemoryScope(args.scope),
        subject=args.subject,
        pinned=args.pin,
    )
    print(f"기억했습니다. ({view.short_id})")
    return 0


def cmd_memos(args, junvis: Junvis) -> int:
    views = junvis.memory.recall(
        args.query,
        scope=MemoryScope(args.scope) if args.scope else None,
        limit=args.limit,
    )
    if not views:
        print("기억나는 것이 없습니다.")
        return 0
    for view in views:
        print_memory(view)
    return 0


def cmd_forget(args, junvis: Junvis) -> int:
    memory_id = args.id
    if len(memory_id) < 32:
        matches = [
            v.id for v in junvis.memory.list_all(limit=500) if v.id.startswith(memory_id)
        ]
        if len(matches) > 1:
            print(f"오류: id '{memory_id}'가 {len(matches)}건과 겹칩니다.", file=sys.stderr)
            return 1
        if matches:
            memory_id = matches[0]
    view = junvis.memory.forget(memory_id)
    print(f"잊었습니다: {view.text}")
    return 0
