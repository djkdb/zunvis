"""Voice 명령."""

from __future__ import annotations

import sys

from junvis.apps.container import Junvis


def register(sub) -> dict:
    listen = sub.add_parser("listen", help="음성으로 명령을 받는다")
    listen.add_argument(
        "--stdin", action="store_true", help="마이크 대신 표준입력(한 줄 = 발화 하나)"
    )
    listen.add_argument("--quiet", action="store_true", help="소리 내지 않고 화면에만")

    say = sub.add_parser("say", help="한 문장을 소리내어 읽는다")
    say.add_argument("text")

    return {"listen": cmd_listen, "say": cmd_say}


def cmd_say(args, junvis: Junvis) -> int:
    spoken = junvis.voice.tts.speak(args.text)
    if not junvis.voice.tts.audible:
        # 소리가 나지 않는 구현이면 사실대로 말한다. 조용히 0을 돌려주면
        # 사용자는 스피커가 고장 났다고 생각한다.
        print("소리를 내지 못했습니다. TTS는 macOS의 `say`를 씁니다.", file=sys.stderr)
        return 1
    return 0 if spoken else 1


def cmd_listen(args, junvis: Junvis) -> int:
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
