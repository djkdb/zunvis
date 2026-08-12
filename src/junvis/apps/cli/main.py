"""JUNVIS CLI.

argparse만 쓴다. 의존성을 하나 줄이면 macOS에서 설치가 하나 쉬워진다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from junvis.apps.cli.confirm import TerminalConfirmer
from junvis.apps.container import Junvis, build
from junvis.core.domain.errors import JunvisError
from junvis.features.creator.application.dto import ContentSummary
from junvis.features.creator.domain.value_objects import ContentFormat
from junvis.features.project_brain.application.dto import (
    ProjectSummary,
    RegisterProjectCommand,
)
from junvis.features.voice.infrastructure.tts import NullTts

STATUS_LABEL = {
    "suggested": "제안",
    "drafted": "초안",
    "published": "발행됨",
    "dismissed": "버림",
}


def _print_project(summary: ProjectSummary) -> None:
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


def _print_content(summary: ContentSummary) -> None:
    label = STATUS_LABEL.get(summary.status, summary.status)
    print(f"[{label}] {summary.subject}  ({summary.id[:8]})")
    if summary.hook:
        print(f"  Hook   : {summary.hook}")
    if summary.scene_count:
        print(f"  장면   : {summary.scene_count}개 · {summary.duration_seconds}초")
    if summary.source_project_slug:
        print(f"  프로젝트: {summary.source_project_slug}")
    if summary.published_url:
        print(f"  발행   : {summary.published_url}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="junvis", description="JUNVIS — 개인 AI OS")
    parser.add_argument("--home", type=Path, help="JUNVIS 홈 (기본: ~/.junvis)")
    parser.add_argument("--offline", action="store_true", help="GitHub 조회를 건너뛴다")
    parser.add_argument("-y", "--yes", action="store_true", help="확인 요구를 자동 승인한다")
    sub = parser.add_subparsers(dest="command", required=True)

    # -- Project Brain ------------------------------------------------------
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

    # -- Creator Mode -------------------------------------------------------
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

    # -- Daily Brief --------------------------------------------------------
    brief = sub.add_parser("brief", help="오늘의 브리핑")
    brief.add_argument(
        "--notify", action="store_true", help="macOS 알림으로 요약 한 줄 (launchd용)"
    )

    # -- Personal Memory ----------------------------------------------------
    memo = sub.add_parser("memo", help="기억해둘 사실을 남긴다")
    memo.add_argument("text")
    memo.add_argument(
        "--scope", choices=["user", "project", "content"], default="user"
    )
    memo.add_argument("--subject", default="", help="프로젝트 slug 등")
    memo.add_argument("--pin", action="store_true", help="항상 우선 주입")

    memos = sub.add_parser("memos", help="기억을 회상하거나 전부 나열한다")
    memos.add_argument("query", nargs="?", default="")
    memos.add_argument("--scope", choices=["user", "project", "content"])
    memos.add_argument("--limit", type=int, default=50)

    forget = sub.add_parser("forget", help="기억을 지운다")
    forget.add_argument("id")

    # -- Voice --------------------------------------------------------------
    listen = sub.add_parser("listen", help="음성으로 명령을 받는다")
    listen.add_argument(
        "--stdin", action="store_true", help="마이크 대신 표준입력(한 줄 = 발화 하나)"
    )
    listen.add_argument("--quiet", action="store_true", help="소리 내지 않고 화면에만")

    say = sub.add_parser("say", help="한 문장을 소리내어 읽는다")
    say.add_argument("text")

    # -- 외부 MCP 서버 -------------------------------------------------------
    mcp = sub.add_parser("mcp", help="외부 MCP 서버를 관리한다")
    mcp_sub = mcp.add_subparsers(dest="mcp_command", required=True)

    mcp_sub.add_parser("list", help="등록된 서버")

    mcp_add = mcp_sub.add_parser("add", help="서버를 등록한다")
    mcp_add.add_argument("id")
    # dest를 `command`로 두면 최상위 서브파서의 dest("command")를 덮어써서
    # 핸들러를 찾지 못한다. 표시 이름만 command로 유지한다.
    mcp_add.add_argument("executable", metavar="command", help="서버 실행 명령")
    mcp_add.add_argument(
        "server_args", nargs="*", metavar="args", help="서버 실행 인자"
    )
    mcp_add.add_argument("--trusted", action="store_true", help="확인 없이 호출 허용")

    mcp_remove = mcp_sub.add_parser("remove", help="서버 등록을 해제한다")
    mcp_remove.add_argument("id")

    mcp_tools = mcp_sub.add_parser("tools", help="도구 목록 (캐시에서)")
    mcp_tools.add_argument("query", nargs="?", default="")
    mcp_tools.add_argument("--server")
    mcp_tools.add_argument("--limit", type=int, default=12)

    mcp_refresh = mcp_sub.add_parser("refresh", help="도구 카탈로그를 다시 만든다")
    mcp_refresh.add_argument("id", nargs="?", help="생략하면 전부")

    mcp_call = mcp_sub.add_parser("call", help="외부 도구를 호출한다")
    mcp_call.add_argument("server")
    mcp_call.add_argument("tool")
    mcp_call.add_argument("--args", default="{}", help="JSON 인자")

    # -- 운영 ---------------------------------------------------------------
    sub.add_parser("drain", help="밀린 비동기 이벤트를 처리한다")
    sub.add_parser("doctor", help="상태를 점검한다")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    tts = NullTts() if getattr(args, "quiet", False) else None
    container = build(
        args.home,
        confirmer=TerminalConfirmer(assume_yes=args.yes),
        offline=args.offline,
        tts=tts,
    )
    try:
        return _dispatch(args, container)
    except JunvisError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    finally:
        container.close()


def _dispatch(args: argparse.Namespace, junvis: Junvis) -> int:
    handler = _HANDLERS.get(args.command)
    return handler(args, junvis) if handler else 2


# -- Project Brain -----------------------------------------------------------


def _cmd_add(args, junvis: Junvis) -> int:
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
    _print_project(latest)

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


def _cmd_list(_args, junvis: Junvis) -> int:
    summaries = junvis.projects.list_all()
    if not summaries:
        print("등록된 프로젝트가 없습니다. `junvis add <경로>` 로 시작하세요.")
        return 0
    for summary in summaries:
        _print_project(summary)
        print()
    return 0


def _cmd_context(args, junvis: Junvis) -> int:
    print(junvis.projects.load_context(args.slug, budget_tokens=args.budget).to_markdown())
    return 0


def _cmd_search(args, junvis: Junvis) -> int:
    hits = junvis.projects.search(args.query, limit=args.limit)
    if not hits:
        print("검색 결과가 없습니다.")
        return 1
    for summary in hits:
        _print_project(summary)
        print()
    return 0


def _cmd_remember(args, junvis: Junvis) -> int:
    summary = junvis.projects.remember(args.slug, args.text)
    print(f"기억했습니다. ({summary.slug}, 메모 {summary.note_count}건)")
    return 0


def _cmd_refresh(args, junvis: Junvis) -> int:
    slugs = [args.slug] if args.slug else [s.slug for s in junvis.projects.list_all()]
    for slug in slugs:
        _print_project(junvis.projects.refresh(slug))
    return 0


# -- Creator Mode ------------------------------------------------------------


def _resolve_content_id(junvis: Junvis, prefix: str) -> str:
    """id 앞 8자만 쳐도 되게 한다. 32자 hex를 손으로 옮겨 적을 수는 없다."""
    if len(prefix) >= 32:
        return prefix
    matches = [c.id for c in junvis.creator.list_all(limit=200) if c.id.startswith(prefix)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        return prefix  # 유스케이스가 ContentNotFound를 던지게 둔다
    raise JunvisError(f"id '{prefix}'가 {len(matches)}건과 겹칩니다. 더 길게 쓰세요.")


def _cmd_reel(args, junvis: Junvis) -> int:
    if not args.subject and not args.id:
        print("오류: 주제나 --id 중 하나는 필요합니다.", file=sys.stderr)
        return 2
    detail = junvis.creator.generate(
        subject=args.subject,
        idea_id=_resolve_content_id(junvis, args.id) if args.id else None,
        project_slug=args.project,
        content_format=ContentFormat.CAROUSEL if args.carousel else ContentFormat.REELS,
        direction=args.direction,
    )
    print(detail.markdown)
    print(f"\n(id: {detail.summary.id})")
    return 0


def _cmd_content(args, junvis: Junvis) -> int:
    summaries = junvis.creator.list_all(status=args.status, limit=args.limit)
    if not summaries:
        print("해당하는 콘텐츠가 없습니다.")
        return 0
    for summary in summaries:
        _print_content(summary)
        print()
    return 0


def _cmd_show(args, junvis: Junvis) -> int:
    print(junvis.creator.get(_resolve_content_id(junvis, args.id)).markdown)
    return 0


def _cmd_dismiss(args, junvis: Junvis) -> int:
    summary = junvis.creator.dismiss(_resolve_content_id(junvis, args.id), args.reason)
    print(f"버렸습니다: {summary.subject}")
    return 0


def _cmd_published(args, junvis: Junvis) -> int:
    summary = junvis.creator.mark_published(
        _resolve_content_id(junvis, args.id), args.url
    )
    print(f"발행 기록 완료: {summary.subject}")
    return 0


def _cmd_brand(args, junvis: Junvis) -> int:
    if args.topics is not None or args.tone or args.audience:
        voice = junvis.creator.update_brand_voice(
            topics=args.topics, tone=args.tone, audience=args.audience
        )
    else:
        voice = junvis.creator.get_brand_voice()
    print(voice.describe())
    return 0


# -- Daily Brief -------------------------------------------------------------


def _cmd_brief(args, junvis: Junvis) -> int:
    briefing = junvis.brief.compose()
    print(briefing.to_markdown())
    if args.notify:
        # 알림 전송 실패(macOS가 아니거나 권한 없음)로 브리핑이 실패하지는 않는다.
        from junvis.features.brief.infrastructure.notifier import notify

        notify(briefing.headline(), subtitle=f"{briefing.day.isoformat()} 브리핑")
    return 0


# -- Personal Memory ---------------------------------------------------------


def _print_memory(view) -> None:
    marks = []
    if view.pinned:
        marks.append("고정")
    if view.scope != "user":
        marks.append(view.scope)
    if view.subject:
        marks.append(view.subject)
    suffix = f"  [{', '.join(marks)}]" if marks else ""
    print(f"- {view.text}{suffix}  ({view.short_id})")


def _cmd_memo(args, junvis: Junvis) -> int:
    from junvis.features.memory.domain.model import MemoryScope

    view = junvis.memory.remember(
        args.text,
        scope=MemoryScope(args.scope),
        subject=args.subject,
        pinned=args.pin,
    )
    print(f"기억했습니다. ({view.short_id})")
    return 0


def _cmd_memos(args, junvis: Junvis) -> int:
    from junvis.features.memory.domain.model import MemoryScope

    views = junvis.memory.recall(
        args.query,
        scope=MemoryScope(args.scope) if args.scope else None,
        limit=args.limit,
    )
    if not views:
        print("기억나는 것이 없습니다.")
        return 0
    for view in views:
        _print_memory(view)
    return 0


def _cmd_forget(args, junvis: Junvis) -> int:
    memory_id = args.id
    if len(memory_id) < 32:
        matches = [v.id for v in junvis.memory.list_all(limit=500) if v.id.startswith(memory_id)]
        if len(matches) > 1:
            print(f"오류: id '{memory_id}'가 {len(matches)}건과 겹칩니다.", file=sys.stderr)
            return 1
        if matches:
            memory_id = matches[0]
    view = junvis.memory.forget(memory_id)
    print(f"잊었습니다: {view.text}")
    return 0


# -- Voice -------------------------------------------------------------------


def _cmd_say(args, junvis: Junvis) -> int:
    spoken = junvis.voice.tts.speak(args.text)
    if not junvis.voice.tts.audible:
        # 소리가 나지 않는 구현이면 사실대로 말한다. 조용히 0을 돌려주면
        # 사용자는 스피커가 고장 났다고 생각한다.
        print(
            "소리를 내지 못했습니다. TTS는 macOS의 `say`를 씁니다.",
            file=sys.stderr,
        )
        return 1
    return 0 if spoken else 1


def _cmd_listen(args, junvis: Junvis) -> int:
    from junvis.features.voice.domain.model import ListenerState
    from junvis.features.voice.infrastructure.audio import (
        AudioUnavailable,
        SoxWhisperSource,
        StdinSource,
    )

    if args.stdin:
        source = StdinSource()
        print("텍스트 입력 대기 중 (한 줄 = 발화 하나, Ctrl-D로 종료)", file=sys.stderr)
    else:
        source = SoxWhisperSource()
        try:
            source.check()
        except AudioUnavailable as exc:
            print(f"{exc}", file=sys.stderr)
            return 1
        print("듣고 있습니다. 호출어로 시작하세요.", file=sys.stderr)

    words = ", ".join(junvis.voice.config.words)
    print(f"호출어: {words}", file=sys.stderr)

    state = ListenerState()
    try:
        for utterance in source.listen():
            outcome = junvis.voice.handle(utterance, state)
            state = outcome.state
            if outcome.acted:
                print(f"< {utterance.text}")
                print(f"> {outcome.response}")
            else:
                print(f"  (무시: {outcome.decision.reason})", file=sys.stderr)
            junvis.drain()
    except KeyboardInterrupt:
        print("\n종료합니다.", file=sys.stderr)
    return 0


# -- 외부 MCP 서버 ------------------------------------------------------------


def _cmd_mcp(args, junvis: Junvis) -> int:
    import json

    from junvis.core.mcp.config import CONFIG_FILENAME, McpConfig, ServerSpec

    config = McpConfig(junvis.home / CONFIG_FILENAME)

    if args.mcp_command == "list":
        servers = junvis.mcp.servers
        if not servers:
            print(f"등록된 서버가 없습니다. 설정 파일: {config.path}")
            return 0
        for spec in servers.values():
            state = [] if spec.enabled else ["비활성"]
            if spec.trusted:
                state.append("신뢰")
            suffix = f"  [{', '.join(state)}]" if state else ""
            tools = len(junvis.mcp.tools(server_id=spec.id, limit=1000))
            print(f"{spec.id}{suffix}")
            print(f"  실행: {spec.command} {' '.join(spec.args)}")
            print(f"  도구: {tools}개")
        return 0

    if args.mcp_command == "add":
        spec = ServerSpec(
            id=args.id,
            command=args.executable,
            args=tuple(args.server_args),
            trusted=args.trusted,
        )
        config.add(spec)
        junvis.mcp.register(spec)
        print(f"등록했습니다: {spec.id}")
        count = len(junvis.mcp.discover(spec.id))
        print(f"도구 {count}개를 찾았습니다.")
        return 0

    if args.mcp_command == "remove":
        if not config.remove(args.id):
            print(f"등록되지 않은 서버입니다: {args.id}", file=sys.stderr)
            return 1
        junvis.mcp.unregister(args.id)
        print(f"해제했습니다: {args.id}")
        return 0

    if args.mcp_command == "tools":
        tools = junvis.mcp.tools(args.query, server_id=args.server, limit=args.limit)
        if not tools:
            print("도구가 없습니다. `junvis mcp refresh` 로 카탈로그를 만드세요.")
            return 0
        for tool in tools:
            print(f"{tool.qualified_name}")
            if tool.description:
                print(f"  {tool.description.splitlines()[0]}")
        return 0

    if args.mcp_command == "refresh":
        if args.id:
            print(f"{args.id}: 도구 {len(junvis.mcp.discover(args.id))}개")
        else:
            for server_id, count in junvis.mcp.refresh_all().items():
                state = f"도구 {count}개" if count >= 0 else "실패"
                print(f"{server_id}: {state}")
        return 0

    if args.mcp_command == "call":
        result = junvis.mcp.call(args.server, args.tool, json.loads(args.args))
        print(result.text)
        if result.is_error:
            return 1
        return 0

    return 2


# -- 운영 --------------------------------------------------------------------


def _cmd_drain(_args, junvis: Junvis) -> int:
    report = junvis.drain()
    print(
        f"처리 {report.processed}건, 재시도 {report.failed}건, "
        f"deadletter {report.deadlettered}건"
    )
    for error in report.errors:
        print(f"  - {error}", file=sys.stderr)
    return 0


def _cmd_doctor(_args, junvis: Junvis) -> int:
    print(f"홈           : {junvis.home}")
    print(f"DB           : {junvis.db.path}")
    print(f"프로젝트     : {len(junvis.projects.list_all())}개")
    print(f"콘텐츠       : {len(junvis.creator.list_all())}개")
    print(f"미처리 이벤트: {junvis.outbox.pending_count()}건")
    print(f"deadletter   : {junvis.outbox.deadletter_count()}건")

    available = getattr(junvis.model, "is_available", None)
    if available is not None:
        ok = available()
        print(f"Ollama       : {'연결됨' if ok else '연결 안 됨 (`ollama serve` 필요)'}")
        if ok:
            models = junvis.model.installed_models()
            print(f"  설치된 모델: {', '.join(models) if models else '없음'}")
    return 0


_HANDLERS = {
    "add": _cmd_add,
    "list": _cmd_list,
    "context": _cmd_context,
    "search": _cmd_search,
    "remember": _cmd_remember,
    "refresh": _cmd_refresh,
    "reel": _cmd_reel,
    "content": _cmd_content,
    "show": _cmd_show,
    "dismiss": _cmd_dismiss,
    "published": _cmd_published,
    "brand": _cmd_brand,
    "brief": _cmd_brief,
    "memo": _cmd_memo,
    "memos": _cmd_memos,
    "forget": _cmd_forget,
    "listen": _cmd_listen,
    "say": _cmd_say,
    "mcp": _cmd_mcp,
    "drain": _cmd_drain,
    "doctor": _cmd_doctor,
}


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
