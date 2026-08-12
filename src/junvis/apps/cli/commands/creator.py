"""Creator Mode 명령."""

from __future__ import annotations

import sys

from junvis.apps.cli.render import print_content
from junvis.apps.container import Junvis
from junvis.core.domain.errors import JunvisError
from junvis.features.creator.domain.value_objects import ContentFormat


def register(sub) -> dict:
    reel = sub.add_parser("reel", help="릴스/캐러셀 기획을 한 번에 생성한다")
    reel.add_argument("subject", nargs="?", help="주제 (--id를 쓰면 생략)")
    reel.add_argument("--id", help="기존 제안 id에 대본을 붙인다")
    reel.add_argument("--project", help="근거로 쓸 프로젝트 slug")
    reel.add_argument("--carousel", action="store_true", help="릴스 대신 캐러셀로")
    reel.add_argument("--direction", default="", help="추가 지시")

    content = sub.add_parser("content", help="콘텐츠 목록")
    content.add_argument(
        "--status", choices=["suggested", "drafted", "published", "dismissed"]
    )
    content.add_argument("--limit", type=int, default=50)

    show = sub.add_parser("show", help="콘텐츠 전체 대본을 출력한다")
    show.add_argument("id")

    dismiss = sub.add_parser("dismiss", help="제안이나 초안을 버린다")
    dismiss.add_argument("id")
    dismiss.add_argument("--reason", default="")

    published = sub.add_parser("published", help="발행 사실을 기록한다")
    published.add_argument("id")
    published.add_argument("--url")

    brand = sub.add_parser("brand", help="ZUN 브랜드 성향을 보거나 바꾼다")
    brand.add_argument("--topics", nargs="*", help="다루는 주제 목록")
    brand.add_argument("--tone")
    brand.add_argument("--audience")

    return {
        "reel": cmd_reel,
        "content": cmd_content,
        "show": cmd_show,
        "dismiss": cmd_dismiss,
        "published": cmd_published,
        "brand": cmd_brand,
    }


def resolve_content_id(junvis: Junvis, prefix: str) -> str:
    """id 앞 8자만 쳐도 되게 한다. 32자 hex를 손으로 옮겨 적을 수는 없다."""
    if len(prefix) >= 32:
        return prefix
    matches = [c.id for c in junvis.creator.list_all(limit=200) if c.id.startswith(prefix)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        return prefix  # 유스케이스가 ContentNotFound를 던지게 둔다
    raise JunvisError(f"id '{prefix}'가 {len(matches)}건과 겹칩니다. 더 길게 쓰세요.")


def cmd_reel(args, junvis: Junvis) -> int:
    if not args.subject and not args.id:
        print("오류: 주제나 --id 중 하나는 필요합니다.", file=sys.stderr)
        return 2
    detail = junvis.creator.generate(
        subject=args.subject,
        idea_id=resolve_content_id(junvis, args.id) if args.id else None,
        project_slug=args.project,
        content_format=ContentFormat.CAROUSEL if args.carousel else ContentFormat.REELS,
        direction=args.direction,
    )
    print(detail.markdown)
    print(f"\n(id: {detail.summary.id})")
    return 0


def cmd_content(args, junvis: Junvis) -> int:
    summaries = junvis.creator.list_all(status=args.status, limit=args.limit)
    if not summaries:
        print("해당하는 콘텐츠가 없습니다.")
        return 0
    for summary in summaries:
        print_content(summary)
        print()
    return 0


def cmd_show(args, junvis: Junvis) -> int:
    print(junvis.creator.get(resolve_content_id(junvis, args.id)).markdown)
    return 0


def cmd_dismiss(args, junvis: Junvis) -> int:
    summary = junvis.creator.dismiss(resolve_content_id(junvis, args.id), args.reason)
    print(f"버렸습니다: {summary.subject}")
    return 0


def cmd_published(args, junvis: Junvis) -> int:
    summary = junvis.creator.mark_published(
        resolve_content_id(junvis, args.id), args.url
    )
    print(f"발행 기록 완료: {summary.subject}")
    return 0


def cmd_brand(args, junvis: Junvis) -> int:
    if args.topics is not None or args.tone or args.audience:
        voice = junvis.creator.update_brand_voice(
            topics=args.topics, tone=args.tone, audience=args.audience
        )
    else:
        voice = junvis.creator.get_brand_voice()
    print(voice.describe())
    return 0
