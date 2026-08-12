"""외부 MCP 서버 관리 명령."""

from __future__ import annotations

import json
import sys

from junvis.apps.container import Junvis
from junvis.core.mcp.config import CONFIG_FILENAME, McpConfig, ServerSpec


def register(sub) -> dict:
    mcp = sub.add_parser("mcp", help="외부 MCP 서버를 관리한다")
    mcp_sub = mcp.add_subparsers(dest="mcp_command", required=True)

    mcp_sub.add_parser("list", help="등록된 서버")

    add = mcp_sub.add_parser("add", help="서버를 등록한다")
    add.add_argument("id")
    # dest를 `command`로 두면 최상위 서브파서의 dest("command")를 덮어써서
    # 핸들러를 찾지 못한다. 표시 이름만 command로 유지한다.
    add.add_argument("executable", metavar="command", help="서버 실행 명령")
    add.add_argument("server_args", nargs="*", metavar="args", help="서버 실행 인자")
    add.add_argument("--trusted", action="store_true", help="확인 없이 호출 허용")

    remove = mcp_sub.add_parser("remove", help="서버 등록을 해제한다")
    remove.add_argument("id")

    tools = mcp_sub.add_parser("tools", help="도구 목록 (캐시에서)")
    tools.add_argument("query", nargs="?", default="")
    tools.add_argument("--server")
    tools.add_argument("--limit", type=int, default=12)

    refresh = mcp_sub.add_parser("refresh", help="도구 카탈로그를 다시 만든다")
    refresh.add_argument("id", nargs="?", help="생략하면 전부")

    call = mcp_sub.add_parser("call", help="외부 도구를 호출한다")
    call.add_argument("server")
    call.add_argument("tool")
    call.add_argument("--args", default="{}", help="JSON 인자")

    return {"mcp": cmd_mcp}


def cmd_mcp(args, junvis: Junvis) -> int:
    config = McpConfig(junvis.home / CONFIG_FILENAME)
    handler = _SUBCOMMANDS.get(args.mcp_command)
    return handler(args, junvis, config) if handler else 2


def _list(_args, junvis: Junvis, config: McpConfig) -> int:
    servers = junvis.mcp.servers
    if not servers:
        print(f"등록된 서버가 없습니다. 설정 파일: {config.path}")
        return 0
    for spec in servers.values():
        state = [] if spec.enabled else ["비활성"]
        if spec.trusted:
            state.append("신뢰")
        suffix = f"  [{', '.join(state)}]" if state else ""
        print(f"{spec.id}{suffix}")
        print(f"  실행: {spec.command} {' '.join(spec.args)}")
        print(f"  도구: {len(junvis.mcp.tools(server_id=spec.id, limit=1000))}개")
    return 0


def _add(args, junvis: Junvis, config: McpConfig) -> int:
    spec = ServerSpec(
        id=args.id,
        command=args.executable,
        args=tuple(args.server_args),
        trusted=args.trusted,
    )
    config.add(spec)
    junvis.mcp.register(spec)
    print(f"등록했습니다: {spec.id}")
    print(f"도구 {len(junvis.mcp.discover(spec.id))}개를 찾았습니다.")
    return 0


def _remove(args, junvis: Junvis, config: McpConfig) -> int:
    if not config.remove(args.id):
        print(f"등록되지 않은 서버입니다: {args.id}", file=sys.stderr)
        return 1
    junvis.mcp.unregister(args.id)
    print(f"해제했습니다: {args.id}")
    return 0


def _tools(args, junvis: Junvis, _config: McpConfig) -> int:
    tools = junvis.mcp.tools(args.query, server_id=args.server, limit=args.limit)
    if not tools:
        print("도구가 없습니다. `junvis mcp refresh` 로 카탈로그를 만드세요.")
        return 0
    for tool in tools:
        print(tool.qualified_name)
        if tool.description:
            print(f"  {tool.description.splitlines()[0]}")
    return 0


def _refresh(args, junvis: Junvis, _config: McpConfig) -> int:
    if args.id:
        print(f"{args.id}: 도구 {len(junvis.mcp.discover(args.id))}개")
        return 0
    for server_id, count in junvis.mcp.refresh_all().items():
        print(f"{server_id}: {'도구 %d개' % count if count >= 0 else '실패'}")
    return 0


def _call(args, junvis: Junvis, _config: McpConfig) -> int:
    result = junvis.mcp.call(args.server, args.tool, json.loads(args.args))
    print(result.text)
    return 1 if result.is_error else 0


_SUBCOMMANDS = {
    "list": _list,
    "add": _add,
    "remove": _remove,
    "tools": _tools,
    "refresh": _refresh,
    "call": _call,
}
