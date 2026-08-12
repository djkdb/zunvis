"""Voice 명령."""

from __future__ import annotations

import shutil
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
        help="맥 내장 음성 인식으로 상시 대기한다. 박수 두 번도 부름으로 친다",
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


def _best_native_source(wake_words: tuple[str, ...]):
    """상시 대기를 할 수 있는 것 중 되는 것을 고른다.

    PyObjC가 먼저다. 컴파일러가 필요 없어 깨질 곳이 적다. Swift 헬퍼는
    직접 빌드한 사람만 갖고 있으므로 그다음이다.
    """
    from junvis.features.voice.infrastructure import apple_speech
    from junvis.features.voice.infrastructure.native_source import NativeHelperSource

    if apple_speech.available():
        return apple_speech.AppleSpeechSource(wake_words=wake_words)

    helper = NativeHelperSource(wake_words=wake_words)
    if shutil.which(helper.binary) is not None:
        return helper

    # 둘 다 없다. 더 쉬운 쪽을 알려준다.
    return apple_speech.AppleSpeechSource(wake_words=wake_words)


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
        # 호출어는 한 곳에서만 정한다. 소스와 게이트가 다른 말을 들으면
        # 마이크는 깨어나는데 JUNVIS는 무시하는 상태가 된다.
        source = _best_native_source(junvis.voice.config.words)
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
    print(f"할 수 있는 말: {'  ·  '.join(junvis.voice.examples)}", file=sys.stderr)

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

            if outcome.acted:
                # 방금 JUNVIS가 말했다. 그동안 마이크에 들어온 것은 전부
                # 자기 목소리다. 소스가 버릴 수 있으면 버린다.
                discard = getattr(source, "discard_pending", None)
                if discard is not None:
                    discard()
            junvis.drain()
    except KeyboardInterrupt:
        print("\n종료합니다.", file=sys.stderr)
    return 0
