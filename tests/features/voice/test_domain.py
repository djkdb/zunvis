"""V1 완료 기준: 게이트 1~3이 모델 없이 결정적으로 검증된다."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from junvis.features.voice.domain.model import (
    DEFAULT_WAKE_WORDS,
    GateDecision,
    ListenerState,
    Utterance,
    WakeWordConfig,
    gate,
    normalize,
)

NOW = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)
CONFIG = WakeWordConfig()


def heard(text: str, at: datetime = NOW) -> Utterance:
    return Utterance(text=text, heard_at=at)


# -- 호출어 인식 -------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "자비스 오늘 브리핑",
        "오늘 브리핑 좀, 자비스",  # 문장 어디에 있든
        "자비스야 프로젝트 뭐 있어",  # 조사가 붙어도
        "Junvis, what's up",
        "JARVIS brief please",
    ],
)
def test_wake_word_is_found_anywhere(text: str) -> None:
    assert CONFIG.contains_wake_word(heard(text)) is True


@pytest.mark.parametrize(
    "text",
    [
        "오늘 브리핑 알려줘",
        "junvistest 라는 프로젝트",  # 라틴 문자는 단어 경계로 본다
        "그냥 혼잣말",
    ],
)
def test_wake_word_absent(text: str) -> None:
    assert CONFIG.contains_wake_word(heard(text)) is False


def test_wake_word_is_stripped_from_the_command() -> None:
    assert CONFIG.strip_wake_word(heard("자비스, 오늘 브리핑!")) == "오늘 브리핑"
    assert CONFIG.strip_wake_word(heard("오늘 브리핑 자비스")) == "오늘 브리핑"
    assert CONFIG.strip_wake_word(heard("자비스")) == ""


@pytest.mark.parametrize(
    "text",
    ["준비스 오늘 브리핑", "헤이 준비스 오늘 브리핑", "야 준비스, 오늘 브리핑"],
)
def test_junvis_is_a_default_wake_word(text: str) -> None:
    """이름이 JUNVIS인데 '준비스'로 못 부르면 이상하다."""
    utterance = heard(text)
    assert CONFIG.contains_wake_word(utterance) is True
    # 부름말이 명령에 남으면 라우터가 엉뚱한 규칙에 걸린다
    assert CONFIG.strip_wake_word(utterance) == "오늘 브리핑"


def test_address_prefix_alone_is_not_a_wake_word() -> None:
    assert CONFIG.contains_wake_word(heard("헤이 거기 잠깐만")) is False


def test_custom_wake_words() -> None:
    config = WakeWordConfig.with_words(("준비스",))
    assert config.contains_wake_word(heard("준비스 브리핑")) is True
    assert config.contains_wake_word(heard("자비스 브리핑")) is False


def test_empty_custom_words_fall_back_to_defaults() -> None:
    assert WakeWordConfig.with_words(("", "  ")).words == DEFAULT_WAKE_WORDS


def test_normalize_strips_punctuation_and_case() -> None:
    assert normalize("  Hello,  WORLD!! ") == "hello world"


# -- 게이트 순서 -------------------------------------------------------------


def test_blank_utterance_is_ignored_first() -> None:
    assert gate(heard("   "), CONFIG, ListenerState()) is GateDecision.IGNORE_EMPTY
    assert gate(heard("..."), CONFIG, ListenerState()) is GateDecision.IGNORE_EMPTY


def test_no_wake_word_is_ignored() -> None:
    decision = gate(heard("오늘 날씨 어때"), CONFIG, ListenerState())
    assert decision is GateDecision.IGNORE_NO_WAKE_WORD
    assert "호출어" in decision.reason


def test_wake_word_passes() -> None:
    assert gate(heard("자비스 브리핑"), CONFIG, ListenerState()).is_act


# -- 에코 차단 (핵심) --------------------------------------------------------


def spoke(text: str, at: datetime = NOW) -> ListenerState:
    return ListenerState().with_spoken(text, at, CONFIG.follow_up_window)


def test_own_speech_coming_back_is_ignored() -> None:
    state = spoke("오늘 브리핑입니다. 멈춰 있는 작업이 있습니다.")
    echo = heard("오늘 브리핑입니다 멈춰 있는 작업이 있습니다", NOW + timedelta(seconds=1))

    assert gate(echo, CONFIG, state) is GateDecision.IGNORE_ECHO


def test_echo_check_runs_before_wake_word_check() -> None:
    """JUNVIS가 호출어를 포함해 말했을 때 그 소리가 돌아오면 무한 루프가 된다."""
    state = spoke("자비스가 무엇을 도와드릴까요")
    echo = heard("자비스가 무엇을 도와드릴까요", NOW + timedelta(seconds=1))

    assert gate(echo, CONFIG, state) is GateDecision.IGNORE_ECHO


def test_partial_echo_is_caught() -> None:
    state = spoke("프로젝트는 ZUNVIS, 릴스 편집기입니다")
    assert gate(heard("프로젝트는 ZUNVIS", NOW + timedelta(seconds=2)), CONFIG, state) is (
        GateDecision.IGNORE_ECHO
    )


def test_echo_window_expires() -> None:
    state = spoke("오늘 브리핑입니다")
    late = heard("오늘 브리핑입니다", NOW + CONFIG.echo_window + timedelta(seconds=1))

    # 창이 지나면 더 이상 에코로 보지 않는다. 사용자가 같은 말을 할 수 있다.
    assert gate(late, CONFIG, state) is not GateDecision.IGNORE_ECHO


def test_different_speech_is_not_an_echo() -> None:
    state = spoke("오늘 브리핑입니다")
    assert gate(heard("자비스 릴스 만들자", NOW + timedelta(seconds=1)), CONFIG, state).is_act


def test_only_recent_lines_are_remembered() -> None:
    state = ListenerState()
    for index in range(10):
        state = state.with_spoken(f"문장 {index}", NOW, CONFIG.follow_up_window)
    assert len(state.recent_spoken) == 5
    assert state.recent_spoken[-1].text == "문장 9"


# -- 후속 발화 창 ------------------------------------------------------------


def test_follow_up_window_lets_you_skip_the_wake_word() -> None:
    state = spoke("네, 무엇을 도와드릴까요")
    follow_up = heard("프로젝트 목록", NOW + timedelta(seconds=3))

    assert gate(follow_up, CONFIG, state).is_act


def test_follow_up_window_closes() -> None:
    state = spoke("네")
    late = heard("프로젝트 목록", NOW + CONFIG.follow_up_window + timedelta(seconds=1))

    assert gate(late, CONFIG, state) is GateDecision.IGNORE_NO_WAKE_WORD


def test_fresh_state_has_no_open_window() -> None:
    assert ListenerState().is_awake(NOW) is False


# -- 에코: 실제로 무한 루프를 만든 것들 ---------------------------------------


def _echoed(heard: str, spoken: str) -> bool:
    from junvis.features.voice.domain.model import (
        DEFAULT_ECHO_THRESHOLD,
        DEFAULT_ECHO_WINDOW,
        ListenerState,
        Utterance,
    )
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 8, 13, 3, 0, tzinfo=timezone.utc)
    state = ListenerState().with_spoken(spoken, now, timedelta(seconds=12))
    return state.sounds_like_echo(
        Utterance(text=heard, heard_at=now + timedelta(seconds=1)),
        threshold=DEFAULT_ECHO_THRESHOLD,
        window=DEFAULT_ECHO_WINDOW,
    )


def test_a_misheard_prefix_of_my_own_answer_is_an_echo() -> None:
    """이것이 무한 루프를 만들었다. 12일을 11일로 흘려 들었을 뿐이다."""
    assert _echoed(
        "8월 11일 브리핑 입니다",
        "8월 12일 브리핑입니다. 작업 습관, 최근 7일 동안 10번 작업했습니다.",
    )


def test_spacing_differences_do_not_hide_an_echo() -> None:
    """한국어 STT의 띄어쓰기는 신뢰할 수 없다."""
    assert _echoed("등록 된 프로젝트가", "등록된 프로젝트가 없습니다.")


def test_a_real_command_is_not_an_echo() -> None:
    """에코를 너무 세게 잡으면 사용자가 말을 못 하게 된다."""
    assert not _echoed(
        "릴스 만들어줘",
        "8월 12일 브리핑입니다. 작업 습관, 최근 7일 동안 10번 작업했습니다.",
    )


def test_repeating_a_command_after_an_answer_still_works() -> None:
    """같은 명령을 한 번 더 시키는 것은 정당하다."""
    assert not _echoed("오늘 브리핑", "등록된 프로젝트가 없습니다.")
