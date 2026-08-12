"""네이티브 헬퍼와의 계약.

Swift는 여기서 컴파일할 수 없다. 그래서 검증하는 것은 **경계**다 —
헬퍼가 무엇을 보내면 JUNVIS가 무엇을 하는가. 이게 고정돼 있으면
Swift에 오타가 있어도 통합은 이미 증명된 상태다.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from junvis.features.voice.domain.model import DEFAULT_WAKE_WORDS
from junvis.features.voice.infrastructure.audio import AudioUnavailable
from junvis.features.voice.infrastructure.native_source import (
    MIN_CONFIDENCE,
    NativeHelperSource,
)


def lines(*events: dict | str) -> list[str]:
    return [
        e if isinstance(e, str) else json.dumps(e, ensure_ascii=False) + "\n"
        for e in events
    ]


def parse(*events: dict | str, **kwargs) -> list:
    return list(NativeHelperSource(**kwargs).parse(iter(lines(*events))))


# -- 받아쓰기 ----------------------------------------------------------------


def test_transcript_becomes_an_utterance() -> None:
    [utterance] = parse(
        {"type": "transcript", "text": "준비스 오늘 브리핑", "confidence": 0.9}
    )
    assert utterance.text == "준비스 오늘 브리핑"
    assert utterance.confidence == 0.9


def test_low_confidence_is_dropped() -> None:
    """Speech·Whisper 모두 무음에서 헛것을 만든다."""
    assert parse(
        {"type": "transcript", "text": "어", "confidence": MIN_CONFIDENCE - 0.1}
    ) == []


def test_empty_transcript_is_dropped() -> None:
    assert parse({"type": "transcript", "text": "   ", "confidence": 1.0}) == []


def test_timestamp_is_used_when_given() -> None:
    moment = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)
    [utterance] = parse(
        {"type": "transcript", "text": "x", "confidence": 1, "at": moment.isoformat()}
    )
    assert utterance.heard_at == moment


def test_bad_timestamp_falls_back_to_now() -> None:
    [utterance] = parse(
        {"type": "transcript", "text": "x", "confidence": 1, "at": "말도 안 되는 값"}
    )
    assert utterance.heard_at.tzinfo is not None


# -- 박수 (핵심) -------------------------------------------------------------


def test_double_clap_is_treated_as_calling_the_name() -> None:
    """새 도메인 개념을 만들지 않는다. 박수 = 이름을 부른 것."""
    [utterance] = parse({"type": "clap", "count": 2})
    assert utterance.text == DEFAULT_WAKE_WORDS[0] == "준비스"


def test_single_clap_is_ignored() -> None:
    assert parse({"type": "clap", "count": 1}) == []


def test_clap_count_is_configurable() -> None:
    assert parse({"type": "clap", "count": 2}, clap_count=3) == []
    assert len(parse({"type": "clap", "count": 3}, clap_count=3)) == 1


def test_clap_uses_the_configured_wake_word() -> None:
    [utterance] = parse({"type": "clap", "count": 2}, wake_words=("자비스",))
    assert utterance.text == "자비스"


# -- 잡음에 견디기 -----------------------------------------------------------


def test_non_json_lines_do_not_break_the_stream() -> None:
    """헬퍼가 로그를 stdout에 섞어도 파이프라인이 죽으면 안 된다."""
    result = parse(
        "그냥 로그 한 줄\n",
        {"type": "transcript", "text": "살아있다", "confidence": 1},
        "[warn] 뭔가\n",
    )
    assert [u.text for u in result] == ["살아있다"]


def test_unknown_event_types_are_skipped() -> None:
    assert parse({"type": "무엇인가"}, {"type": "ready", "wake_words": []}) == []


def test_error_events_are_logged_not_raised(caplog) -> None:
    assert parse({"type": "error", "message": "마이크 권한이 없습니다"}) == []
    assert "마이크 권한" in caplog.text


def test_blank_lines_are_skipped() -> None:
    assert parse("\n", "   \n") == []


# -- 실행 --------------------------------------------------------------------


def test_command_carries_wake_words_and_clap_count() -> None:
    command = NativeHelperSource(wake_words=("준비스", "자비스"), clap_count=2).command()
    assert command[1] == "listen"
    assert "준비스,자비스" in command
    assert "--clap" in command


def test_missing_helper_explains_what_to_do() -> None:
    source = NativeHelperSource(binary="존재하지-않는-헬퍼")
    with pytest.raises(AudioUnavailable, match="build-mac.sh"):
        source.check()


def test_end_to_end_with_a_fake_helper(tmp_path) -> None:
    """실제 프로세스를 띄워 stdout을 읽는 경로 전체를 확인한다.

    Swift 헬퍼가 없어도 계약을 지키는 무언가만 있으면 JUNVIS는 동작한다.
    """
    helper = tmp_path / "fake-junvis-mac"
    helper.write_text(
        "#!/bin/sh\n"
        'echo \'{"type":"ready","wake_words":["준비스"]}\'\n'
        'echo \'{"type":"clap","count":2}\'\n'
        'echo \'{"type":"transcript","text":"오늘 브리핑","confidence":0.95}\'\n',
        encoding="utf-8",
    )
    helper.chmod(0o755)

    source = NativeHelperSource(binary=str(helper))
    heard = [u.text for u in source.listen()]

    assert heard == ["준비스", "오늘 브리핑"]


def test_fake_helper_drives_the_full_gate(tmp_path) -> None:
    """박수 → "네?" → 호출어 없는 후속 명령. 도메인을 한 줄도 안 고쳤다."""
    from junvis.core.eventbus.bus import EventBus
    from junvis.features.voice.application.use_cases.handle_utterance import (
        HandleUtterance,
    )
    from junvis.features.voice.domain.model import ListenerState
    from junvis.features.voice.infrastructure.tts import NullTts

    helper = tmp_path / "fake-junvis-mac"
    helper.write_text(
        "#!/bin/sh\n"
        'echo \'{"type":"clap","count":2}\'\n'
        'echo \'{"type":"transcript","text":"오늘 브리핑","confidence":0.95}\'\n',
        encoding="utf-8",
    )
    helper.chmod(0o755)

    class Judge:
        def is_command(self, text: str) -> bool:
            return True

    class Handler:
        def __init__(self) -> None:
            self.commands: list[str] = []

        def handle(self, command: str) -> str:
            self.commands.append(command)
            return "브리핑입니다"

    handler = Handler()
    tts = NullTts()
    handle = HandleUtterance(Judge(), handler, tts, EventBus())

    state = ListenerState()
    responses = []
    for utterance in NativeHelperSource(binary=str(helper)).listen():
        outcome = handle(utterance, state)
        state = outcome.state
        responses.append(outcome.response)

    assert responses == ["네?", "브리핑입니다"]
    assert handler.commands == ["오늘 브리핑"]  # 박수는 명령을 실행하지 않는다
