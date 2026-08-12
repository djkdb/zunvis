"""운영 명령 — 밀린 이벤트 처리와 상태 점검."""

from __future__ import annotations

import sys

from junvis.apps.container import Junvis


def register(sub) -> dict:
    sub.add_parser("drain", help="밀린 비동기 이벤트를 처리한다")
    sub.add_parser("doctor", help="상태를 점검한다")
    return {"drain": cmd_drain, "doctor": cmd_doctor}


def cmd_drain(_args, junvis: Junvis) -> int:
    report = junvis.drain()
    print(
        f"처리 {report.processed}건, 재시도 {report.failed}건, "
        f"deadletter {report.deadlettered}건"
    )
    for error in report.errors:
        print(f"  - {error}", file=sys.stderr)
    return 0


def cmd_doctor(_args, junvis: Junvis) -> int:
    print(f"홈           : {junvis.home}")
    print(f"DB           : {junvis.db.path}")
    print(f"프로젝트     : {len(junvis.projects.list_all())}개")
    print(f"콘텐츠       : {len(junvis.creator.list_all())}개")
    print(f"기억         : {len(junvis.memory.list_all(limit=1000))}개")
    print(f"미처리 이벤트: {junvis.outbox.pending_count()}건")
    print(f"deadletter   : {junvis.outbox.deadletter_count()}건")

    _print_model(junvis)
    _print_mcp(junvis)
    return 0


def _print_model(junvis: Junvis) -> None:
    available = getattr(junvis.model, "is_available", None)
    if available is None:
        return
    ok = available()
    print(f"Ollama       : {'연결됨' if ok else '연결 안 됨 (`ollama serve` 필요)'}")
    if ok:
        models = junvis.model.installed_models()
        print(f"  설치된 모델: {', '.join(models) if models else '없음'}")


def _print_mcp(junvis: Junvis) -> None:
    servers = junvis.mcp.servers
    if not servers:
        print("외부 MCP    : 없음 (`junvis mcp add` 로 등록)")
        return
    total = len(junvis.mcp.tools(limit=10_000))
    print(f"외부 MCP    : 서버 {len(servers)}개 · 도구 {total}개")
    for spec in servers.values():
        count = len(junvis.mcp.tools(server_id=spec.id, limit=1000))
        state = "신뢰" if spec.trusted else "확인 필요"
        print(f"  {spec.id}: 도구 {count}개 · {state}")
