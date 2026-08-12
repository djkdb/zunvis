"""V2 완료 기준: 게이트 4와 응답·상태 전이를 검증한다."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from junvis.core.eventbus.bus import EventBus
from junvis.features.voice.application.use_cases.handle_utterance import HandleUtterance
from junvis.features.voice.domain.model import (
    GateDecision,
    ListenerState,
    Utterance,
    WakeWordConfig,
)
from junvis.features.voice.infrastructure.tts import NullTts

NOW = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)


class FakeJudge:
    def __init__(self, verdict: bool = True, *, raises: Exception | None = None) -> None:
        self.verdict = verdict
        self.raises = raises
        self.asked: list[str] = []

    def is_command(self, text: str) -> bool:
        self.asked.append(text)
        if self.raises is not None:
            raise self.raises
        return self.verdict


class FakeHandler:
    def __init__(self, response: str = "네, 했습니다", *, raises: Exception | None = None):
        self.response = response
        self.raises = raises
        self.commands: list[str] = []

    def handle(self, command: str) -> str:
        self.commands.append(command)
        if self.raises is not None:
            raise self.raises
        return self.response


@pytest.fixture()
def bus() -> EventBus:
    return EventBus()


def build(bus, judge=None, handler=None, tts=None) -> tuple:
    judge = judge or FakeJudge()
    handler = handler or FakeHandler()
    tts = tts or NullTts()
    use_case = HandleUtterance(judge, handler, tts, bus, config=WakeWordConfig())
    return use_case, judge, handler, tts


def heard(text: str, at: datetime = NOW) -> Utterance:
    return Utterance(text=text, heard_at=at)


# -- 통과 경로 ---------------------------------------------------------------


def test_command_is_executed_and_spoken(bus) -> None:
    use_case, judge, handler, tts = build(bus)

    outcome = use_case(heard("자비스 오늘 브리핑"), ListenerState())

    assert outcome.acted
    assert outcome.command == "오늘 브리핑"  # 호출어가 명령에 새어 들어가지 않는다
    assert handler.commands == ["오늘 브리핑"]
    assert tts.spoken == ["네, 했습니다"]
    assert judge.asked == ["오늘 브리핑"]


def test_command_event_is_published(bus) -> None:
    use_case, *_ = build(bus)
    seen = []
    bus.subscribe("voice.command_received", lambda e: seen.append(e.payload))

    use_case(heard("자비스 프로젝트 목록"), ListenerState())

    assert seen[0]["text"] == "프로젝트 목록"
    assert seen[0]["raw_text"] == "자비스 프로젝트 목록"
    assert seen[0]["followed_up"] is False


def test_bare_wake_word_gets_a_prompt_not_a_command(bus) -> None:
    use_case, judge, handler, tts = build(bus)

    outcome = use_case(heard("자비스"), ListenerState())

    assert outcome.acted
    assert outcome.response == "네?"
    assert handler.commands == []  # 실행할 것이 없다
    assert judge.asked == []  # 판정할 것도 없다


# -- 게이트 4 (Intent Judge) --------------------------------------------------


def test_non_command_is_ignored(bus) -> None:
    use_case, _, handler, tts = build(bus, judge=FakeJudge(False))

    outcome = use_case(heard("자비스 어 잠깐만"), ListenerState())

    assert outcome.decision is GateDecision.IGNORE_NOT_A_COMMAND
    assert handler.commands == []
    assert tts.spoken == []


def test_judge_failure_fails_open(bus) -> None:
    """모델이 죽었다고 사용자를 무시하는 것이 더 나쁜 실패다."""
    use_case, _, handler, _ = build(bus, judge=FakeJudge(raises=RuntimeError("모델 없음")))

    outcome = use_case(heard("자비스 브리핑"), ListenerState())

    assert outcome.acted
    assert handler.commands == ["브리핑"]


def test_ignored_utterance_publishes_a_reason(bus) -> None:
    use_case, *_ = build(bus)
    seen = []
    bus.subscribe("voice.utterance_ignored", lambda e: seen.append(e.payload))

    use_case(heard("그냥 혼잣말"), ListenerState())

    assert seen[0]["reason"] == "ignore_no_wake_word"


# -- 실행 실패 ---------------------------------------------------------------


def test_handler_failure_still_answers(bus) -> None:
    use_case, _, _, tts = build(bus, handler=FakeHandler(raises=RuntimeError("터짐")))

    outcome = use_case(heard("자비스 브리핑"), ListenerState())

    assert outcome.response == "처리하지 못했습니다."
    assert tts.spoken == ["처리하지 못했습니다."]


# -- 상태 전이 ---------------------------------------------------------------


def test_response_opens_the_follow_up_window(bus) -> None:
    use_case, *_ = build(bus)

    first = use_case(heard("자비스 브리핑"), ListenerState())
    second = use_case(heard("프로젝트 목록", NOW + timedelta(seconds=3)), first.state)

    assert second.acted  # 호출어 없이도 통과
    assert second.command == "프로젝트 목록"


def test_follow_up_is_marked_in_the_event(bus) -> None:
    use_case, *_ = build(bus)
    seen = []
    bus.subscribe("voice.command_received", lambda e: seen.append(e.payload))

    first = use_case(heard("자비스 브리핑"), ListenerState())
    use_case(heard("프로젝트 목록", NOW + timedelta(seconds=3)), first.state)

    assert [p["followed_up"] for p in seen] == [False, True]


def test_own_response_coming_back_is_ignored(bus) -> None:
    """이게 없으면 자기 말에 자기가 반응하는 무한 루프가 생긴다."""
    use_case, _, handler, _ = build(bus, handler=FakeHandler("자비스가 브리핑을 읽습니다"))

    first = use_case(heard("자비스 브리핑"), ListenerState())
    echo = use_case(
        heard("자비스가 브리핑을 읽습니다", NOW + timedelta(seconds=1)), first.state
    )

    assert echo.decision is GateDecision.IGNORE_ECHO
    assert handler.commands == ["브리핑"]  # 두 번 실행되지 않았다


def test_state_is_unchanged_when_ignored(bus) -> None:
    use_case, *_ = build(bus)
    state = ListenerState()
    assert use_case(heard("혼잣말"), state).state is state


# -- 상태 표시 ---------------------------------------------------------------


class SpyPresence:
    def __init__(self) -> None:
        self.shown: list[tuple[str, str]] = []

    def show(self, presence, text: str = "") -> None:
        self.shown.append((presence.value, text))

    @property
    def sequence(self) -> list[str]:
        return [presence for presence, _ in self.shown]


def with_presence(bus, **kwargs):
    presence = SpyPresence()
    use_case = HandleUtterance(
        kwargs.pop("judge", None) or FakeJudge(),
        kwargs.pop("handler", None) or FakeHandler(),
        NullTts(),
        bus,
        config=WakeWordConfig(),
        presence=presence,
    )
    return use_case, presence


def test_a_command_walks_through_thinking_then_speaking(bus) -> None:
    use_case, presence = with_presence(bus)

    use_case(heard("자비스 브리핑"), ListenerState())

    assert presence.sequence == ["thinking", "speaking", "awake"]


def test_calling_the_name_alone_only_answers(bus) -> None:
    """부름은 실행이 아니다. 생각하는 척하면 안 된다."""
    use_case, presence = with_presence(bus)

    use_case(heard("자비스"), ListenerState())

    assert presence.sequence == ["speaking", "awake"]
    assert presence.shown[0] == ("speaking", "네?")


def test_noise_puts_the_screen_back_to_sleep(bus) -> None:
    use_case, presence = with_presence(bus)

    use_case(heard("점심 뭐 먹지"), ListenerState())

    assert presence.sequence == ["asleep"]


def test_noise_inside_the_follow_up_window_keeps_the_screen_awake(bus) -> None:
    """아직 이어 말할 수 있는데 화면이 잠들면 사용자는 다시 이름을 부른다."""
    use_case, presence = with_presence(bus)
    open_window = ListenerState().with_spoken("네?", NOW, timedelta(seconds=12))

    # 에코로 걸리는 발화. 창은 아직 열려 있다.
    use_case(heard("네?", NOW + timedelta(seconds=1)), open_window)

    assert presence.sequence == []


def test_a_broken_screen_does_not_break_the_command(bus) -> None:
    """장식이 본체를 붙잡으면 안 된다."""

    class BrokenPresence:
        def show(self, presence, text: str = "") -> None:
            raise RuntimeError("화면이 죽었다")

    handler = FakeHandler("네, 했습니다")
    use_case = HandleUtterance(
        FakeJudge(), handler, NullTts(), bus,
        config=WakeWordConfig(), presence=BrokenPresence(),
    )

    outcome = use_case(heard("자비스 브리핑"), ListenerState())

    assert outcome.acted
    assert handler.commands == ["브리핑"]
