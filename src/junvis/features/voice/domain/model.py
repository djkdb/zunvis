"""Voice의 판단 파이프라인 — 이 Context에서 실제로 어려운 부분.

마이크를 읽는 일이 아니라 **언제 반응할지 결정하는 일**이 핵심이다.
게이트 1~3(빈 발화·에코·호출어)은 여기서 모델 없이 결정된다.
게이트 4(진짜 명령인가)만 application에서 소형 로컬 모델을 쓴다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from enum import Enum

from junvis.core.domain.event import utcnow

#: 라틴 문자는 단어 경계로, 한글은 부분 일치로 본다.
#: "junvis"가 "junvistest"에 걸리면 안 되지만, 한국어는 조사가 붙어
#: "자비스야"·"자비스가"처럼 나오므로 부분 일치가 맞다.
_LATIN_WORD = re.compile(r"[a-z0-9]+")
_HANGUL = re.compile(r"[가-힣]")

DEFAULT_WAKE_WORDS = ("준비스", "자비스", "junvis", "jarvis")

#: 호출어 앞에 붙는 부름말. 명령 본문이 아니므로 함께 걷어낸다.
#: "헤이 준비스 브리핑"의 명령은 "헤이 브리핑"이 아니라 "브리핑"이다.
ADDRESS_PREFIXES = ("헤이", "야", "hey", "ok", "오케이")

#: 에코로 판정할 유사도. 낮추면 사용자가 따라 말할 때도 막힌다.
DEFAULT_ECHO_THRESHOLD = 0.8
#: 에코 창. 스피커 소리가 마이크로 돌아오는 데 걸리는 시간이면 충분하다.
DEFAULT_ECHO_WINDOW = timedelta(seconds=8)
#: 응답 직후 호출어 없이 말할 수 있는 시간.
DEFAULT_FOLLOW_UP_WINDOW = timedelta(seconds=12)

#: 최근 발화를 몇 개까지 기억할지. 에코 판정에만 쓰므로 짧게 유지한다.
MAX_REMEMBERED_UTTERANCES = 5


def normalize(text: str) -> str:
    """비교용 정규화. 문장부호와 공백 차이로 에코를 놓치지 않게 한다."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w가-힣\s]", "", text.lower())).strip()


class Presence(str, Enum):
    """JUNVIS가 지금 무엇을 하고 있는가 — 사람에게 보여줄 상태.

    로그가 아니다. 말을 걸었을 때 **들었는지 아닌지 즉시 알 수 있어야**
    한다는 요구에서 나온 도메인 개념이다. 음성 인터페이스에서 침묵은
    "무시당했다"와 "생각 중이다"를 구분해 주지 못한다.

    게이트가 이미 이 전이를 전부 알고 있으므로 새로 계산하지 않는다.
    화면에 어떻게 그릴지는 여기서 정하지 않는다(그건 어댑터의 몫).
    """

    ASLEEP = "asleep"
    #: 이름을 들었다. 후속 발화 창이 열려 있다.
    AWAKE = "awake"
    #: 명령을 실행하는 중.
    THINKING = "thinking"
    #: 답을 말하는 중.
    SPEAKING = "speaking"


class GateDecision(str, Enum):
    ACT = "act"
    IGNORE_EMPTY = "ignore_empty"
    IGNORE_ECHO = "ignore_echo"
    IGNORE_NO_WAKE_WORD = "ignore_no_wake_word"
    #: 게이트 4는 application에서 소형 모델이 판정한다.
    IGNORE_NOT_A_COMMAND = "ignore_not_a_command"

    @property
    def is_act(self) -> bool:
        return self is GateDecision.ACT

    @property
    def reason(self) -> str:
        return {
            GateDecision.ACT: "명령으로 인식",
            GateDecision.IGNORE_EMPTY: "빈 발화",
            GateDecision.IGNORE_ECHO: "내가 방금 한 말의 반향",
            GateDecision.IGNORE_NO_WAKE_WORD: "호출어 없음",
            GateDecision.IGNORE_NOT_A_COMMAND: "명령이 아닌 것으로 판단",
        }[self]


@dataclass(frozen=True)
class Utterance:
    text: str
    heard_at: datetime = field(default_factory=utcnow)
    confidence: float = 1.0

    @property
    def normalized(self) -> str:
        return normalize(self.text)

    @property
    def is_blank(self) -> bool:
        return not self.normalized


@dataclass(frozen=True)
class WakeWordConfig:
    words: tuple[str, ...] = DEFAULT_WAKE_WORDS
    echo_threshold: float = DEFAULT_ECHO_THRESHOLD
    echo_window: timedelta = DEFAULT_ECHO_WINDOW
    follow_up_window: timedelta = DEFAULT_FOLLOW_UP_WINDOW

    @staticmethod
    def with_words(words: tuple[str, ...]) -> WakeWordConfig:
        cleaned = tuple(normalize(w) for w in words if normalize(w))
        return WakeWordConfig(words=cleaned or DEFAULT_WAKE_WORDS)

    def contains_wake_word(self, utterance: Utterance) -> bool:
        """문장 어디에 있든 인식한다.

        "자비스 브리핑"도 "오늘 브리핑 좀, 자비스"도 통과해야 한다.
        """
        text = utterance.normalized
        words = set(_LATIN_WORD.findall(text))
        for wake in self.words:
            target = normalize(wake)
            if not target:
                continue
            if _HANGUL.search(target):
                if target in text:
                    return True
            elif target in words:
                return True
        return False

    def strip_wake_word(self, utterance: Utterance) -> str:
        """명령 본문만 남긴다.

        호출어뿐 아니라 부름말("헤이", "야")도 걷어낸다. 그것이 명령에
        남으면 라우터가 엉뚱한 규칙에 걸릴 수 있고, 모델에게도 잡음이다.
        """
        text = utterance.text
        for token in (*self.words, *ADDRESS_PREFIXES):
            text = re.sub(re.escape(token), " ", text, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", text).strip(" ,.!?~")


@dataclass(frozen=True)
class SpokenLine:
    text: str
    spoken_at: datetime

    @property
    def normalized(self) -> str:
        return normalize(self.text)


@dataclass(frozen=True)
class ListenerState:
    """불변 상태. 에코 창과 후속 발화 창이 언제 열리고 닫히는지를
    시계 없이 검증할 수 있게 한다."""

    recent_spoken: tuple[SpokenLine, ...] = ()
    awake_until: datetime | None = None

    def with_spoken(self, text: str, at: datetime, follow_up: timedelta) -> ListenerState:
        """JUNVIS가 말했다. 에코를 막고, 후속 발화 창을 연다."""
        lines = (*self.recent_spoken, SpokenLine(text, at))
        return ListenerState(
            recent_spoken=lines[-MAX_REMEMBERED_UTTERANCES:],
            awake_until=at + follow_up,
        )

    def is_awake(self, now: datetime) -> bool:
        return self.awake_until is not None and now < self.awake_until

    def sounds_like_echo(
        self, utterance: Utterance, *, threshold: float, window: timedelta
    ) -> bool:
        heard = utterance.normalized
        if not heard:
            return False
        for line in self.recent_spoken:
            if utterance.heard_at - line.spoken_at > window:
                continue
            spoken = line.normalized
            if not spoken:
                continue
            # 짧은 발화는 유사도가 튀므로 포함 관계도 함께 본다.
            if heard in spoken or spoken in heard:
                return True
            if SequenceMatcher(None, heard, spoken).ratio() >= threshold:
                return True
        return False


def gate(
    utterance: Utterance, config: WakeWordConfig, state: ListenerState
) -> GateDecision:
    """게이트 1~3. 모델을 부르기 전에 걸러낼 수 있는 것을 전부 걸러낸다.

    순서가 중요하다. 에코 판정이 호출어 판정보다 **먼저**여야 한다 —
    JUNVIS가 "자비스가 뭘 도와드릴까요"라고 말했을 때 그 소리가 돌아오면
    호출어를 포함하고 있기 때문이다.
    """
    if utterance.is_blank:
        return GateDecision.IGNORE_EMPTY
    if state.sounds_like_echo(
        utterance, threshold=config.echo_threshold, window=config.echo_window
    ):
        return GateDecision.IGNORE_ECHO
    if config.contains_wake_word(utterance):
        return GateDecision.ACT
    if state.is_awake(utterance.heard_at):
        return GateDecision.ACT  # 후속 발화 창
    return GateDecision.IGNORE_NO_WAKE_WORD
