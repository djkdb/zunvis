"""Voice 명령."""

from __future__ import annotations

import sys

from junvis.apps.container import Junvis
from junvis.apps.orb.server import DEFAULT_PORT


def register(sub) -> dict:
    listen = sub.add_parser("listen", help="음성으로 명령을 받는다")
    listen.add_argument(
        "--stdin", action="store_true", help="마이크 대신 표준입력(한 줄 = 발화 하나)"
    )
    listen.add_argument(
        "--native",
        action="store_true",
        help="네이티브 헬퍼(junvis-mac)로 듣는다. 박수 두 번도 부름으로 친다",
    )
    listen.add_argument("--quiet", action="store_true", help="소리 내지 않고 화면에만")

    say = sub.add_parser("say", help="한 문장을 소리내어 읽는다")
    say.add_argument("text")

    orb = sub.add_parser("orb", help="부르면 반응하는 화면을 띄운다")
    orb.add_argument("--port", type=int, default=DEFAULT_PORT)
    orb.add_argument("--no-open", action="store_true", help="브라우저를 열지 않는다")

    return {"listen": cmd_listen, "say": cmd_say, "orb": cmd_orb}


def cmd_orb(args, junvis: Junvis) -> int:
    from junvis.apps.orb.server import HOST, build_server, open_later

    try:
        server = build_server(junvis.voice.presence_path, args.port)
    except OSError as exc:
        print(f"{args.port} 포트를 열지 못했습니다: {exc}", file=sys.stderr)
        print("  다른 포트로: junvis orb --port 4174", file=sys.stderr)
        return 1

    url = f"http://{HOST}:{args.port}/"
    print(f"오브: {url}", file=sys.stderr)
    print("다른 창에서 `junvis listen` 을 띄우면 반응합니다.", file=sys.stderr)
    if not args.no_open:
        open_later(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n닫습니다.", file=sys.stderr)
    finally:
        server.server_close()
    return 0


def cmd_say(args, junvis: Junvis) -> int:
    spoken = junvis.voice.tts.speak(args.text)
    if not junvis.voice.tts.audible:
        # 소리가 나지 않는 구현이면 사실대로 말한다. 조용히 0을 돌려주면
        # 사용자는 스피커가 고장 났다고 생각한다.
        print("소리를 내지 못했습니다. TTS는 macOS의 `say`를 씁니다.", file=sys.stderr)
        return 1
    return 0 if spoken else 1


def _make_source(args, junvis: Junvis):
    """플래그를 발화 소스로 바꾼다. 준비되지 않았으면 그 자리에서 알려준다."""
    from junvis.features.voice.infrastructure.audio import (
        AudioUnavailable,
        SoxWhisperSource,
        StdinSource,
    )

    if args.stdin:
        return StdinSource(), "텍스트 입력 대기 중 (한 줄 = 발화 하나, Ctrl-D로 종료)"

    if args.native:
        from junvis.features.voice.infrastructure.native_source import (
            NativeHelperSource,
        )

        # 호출어는 한 곳에서만 정한다. 헬퍼와 게이트가 다른 말을 들으면
        # 헬퍼는 깨어나는데 JUNVIS는 무시하는 상태가 된다.
        source = NativeHelperSource(wake_words=junvis.voice.config.words)
        source.check()
        return source, "듣고 있습니다. 호출어 또는 박수 두 번."

    source = SoxWhisperSource()
    source.check()
    return source, "듣고 있습니다. 호출어로 시작하세요."


def cmd_listen(args, junvis: Junvis) -> int:
    from junvis.features.voice.domain.model import ListenerState
    from junvis.features.voice.infrastructure.audio import AudioUnavailable

    try:
        source, greeting = _make_source(args, junvis)
    except AudioUnavailable as exc:
        print(f"{exc}", file=sys.stderr)
        return 1

    print(greeting, file=sys.stderr)
    print(f"호출어: {', '.join(junvis.voice.config.words)}", file=sys.stderr)

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
