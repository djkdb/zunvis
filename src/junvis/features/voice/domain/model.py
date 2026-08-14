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

#: 호출어 퍼지 매칭 문턱. STT는 "자비스"를 "자비수"로 흘려 듣는다.
#: 정확 일치만 보면 그때 JUNVIS는 깨어나지 않는다.
DEFAULT_WAKE_FUZZY = 0.78

#: 이보다 짧은 토큰은 퍼지 매칭하지 않는다.
#: 두 글자는 "준비" vs "준비스"가 0.8로 걸린다 — 흔한 말이 이름이 된다.
MIN_FUZZY_TOKEN = 3
#: 에코 창. 스피커 소리가 마이크로 돌아오는 데 걸리는 시간이면 충분하다.
DEFAULT_ECHO_WINDOW = timedelta(seconds=8)
#: 응답 직후 호출어 없이 말할 수 있는 시간.
DEFAULT_FOLLOW_UP_WINDOW = timedelta(seconds=12)

#: 최근 발화를 몇 개까지 기억할지. 에코 판정에만 쓰므로 짧게 유지한다.
MAX_REMEMBERED_UTTERANCES = 5

#: 말을 끊는 말. 호출어 없이도 통한다 — 끊고 싶은데 이름부터 불러야 하면
#: 그때는 이미 끝까지 들은 뒤다.
STOP_WORDS = ("그만", "됐어", "됐다", "멈춰", "그쳐", "stop", "됐어요", "그만해")


def normalize(text: str) -> str:
    """비교용 정규화. 문장부호와 공백 차이로 에코를 놓치지 않게 한다."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w가-힣\s]", "", text.lower())).strip()


def loose(token: str) -> re.Pattern[str]:
    """글자 사이에 공백이 끼어도 찾아내는 패턴.

    `squash`가 비교용이라면 이쪽은 **제거용**이다. 원문에서 호출어를
    걷어낼 때는 공백을 지운 사본이 아니라 원문 위치를 알아야 한다.
    "자비 스 프로젝트"에서 "자비 스"를 지워야 명령이 "프로젝트"가 된다.
    """
    letters = [re.escape(ch) for ch in token if not ch.isspace()]
    return re.compile(r"\s*".join(letters), re.IGNORECASE)


#: 한글 음절 분해용. 유니코드가 산술로 정의해 두었으므로 표가 필요 없다.
_HANGUL_BASE = 0xAC00
_CHOSUNG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNGSUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONGSUNG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"


def jamo(text: str) -> str:
    """한글을 자모로 편다.

    음절 단위로 비교하면 유사도가 뭉툭하다. "자비스"와 "자비수"는 세 글자
    중 하나가 다르니 0.667이고, 이름을 흘려 들은 것치고는 너무 낮게 나온다.
    자모로 펴면 ㅅㅜ와 ㅅㅡ의 차이 — 모음 하나 — 로 드러나 0.833이 된다.

    STT의 오인식은 대개 이런 모양이다. 음절이 통째로 바뀌는 것이 아니라
    모음이나 받침 하나가 흔들린다.
    """
    out = []
    for char in text:
        code = ord(char) - _HANGUL_BASE
        if 0 <= code < 11172:
            out.append(_CHOSUNG[code // 588])
            out.append(_JUNGSUNG[(code % 588) // 28])
            final = _JONGSUNG[code % 28]
            if final != " ":
                out.append(final)
        else:
            out.append(char)
    return "".join(out)


def partial_ratio(short: str, long: str) -> float:
    """짧은 쪽이 긴 쪽 **어디엔가** 얼마나 들어 있는가.

    `SequenceMatcher`를 통째로 쓰면 길이 차이에 유사도가 묻힌다. 긴 대답
    안에서 들린 만큼의 창을 훑어 최고점을 찾는다 — 에코가 앞이든 중간이든
    잡힌다. `rapidfuzz.partial_ratio`가 하는 일과 같고, 의존성을 늘리지
    않으려고 표준 라이브러리로 쓴다.
    """
    if not short or not long:
        return 0.0
    if len(short) > len(long):
        short, long = long, short

    best = 0.0
    for start in range(len(long) - len(short) + 1):
        window = long[start : start + len(short)]
        best = max(best, SequenceMatcher(None, short, window).ratio())
        if best == 1.0:
            break
    return best


def squash(text: str) -> str:
    """띄어쓰기를 지운 비교용 형태.

    **한국어 STT의 띄어쓰기는 신뢰할 수 없다.** 실제로 이렇게 나왔다.

        "릴스 만들어줘"        →  "릴 스 만들어 줘"
        "등록된 프로젝트가"     →  "등록 된 프로젝트가"

    사람에게는 같은 말이다. 그래서 호출어를 찾을 때도, 에코를 판정할 때도
    공백을 없앤 것끼리 본다. 라틴 문자는 단어 경계가 의미를 가지므로
    (`junvis`가 `junvistest`에 걸리면 안 된다) 이 함수를 쓰지 않는다.
    """
    return normalize(text).replace(" ", "")


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
    #: 말하는 중에 "그만"을 들었다. 실행이 아니라 중단이다.
    STOP = "stop"
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
            GateDecision.STOP: "그만하라고 하셔서 멈췄습니다",
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
    def squashed(self) -> str:
        return squash(self.text)

    @property
    def is_blank(self) -> bool:
        return not self.normalized


@dataclass(frozen=True)
class WakeWordConfig:
    words: tuple[str, ...] = DEFAULT_WAKE_WORDS
    echo_threshold: float = DEFAULT_ECHO_THRESHOLD
    echo_window: timedelta = DEFAULT_ECHO_WINDOW
    follow_up_window: timedelta = DEFAULT_FOLLOW_UP_WINDOW
    wake_fuzzy: float = DEFAULT_WAKE_FUZZY

    @staticmethod
    def with_words(words: tuple[str, ...]) -> WakeWordConfig:
        cleaned = tuple(normalize(w) for w in words if normalize(w))
        return WakeWordConfig(words=cleaned or DEFAULT_WAKE_WORDS)

    def contains_wake_word(self, utterance: Utterance) -> bool:
        """문장 어디에 있든 인식한다.

        "자비스 브리핑"도 "오늘 브리핑 좀, 자비스"도 통과해야 한다.
        """
        words = set(_LATIN_WORD.findall(utterance.normalized))
        squashed = utterance.squashed
        for wake in self.words:
            target = normalize(wake)
            if not target:
                continue
            if _HANGUL.search(target):
                # "자비 스 프로젝트"도 부른 것이다.
                if squash(target) in squashed:
                    return True
            elif target in words:
                return True
        return self._sounds_like_my_name(utterance)

    def _sounds_like_my_name(self, utterance: Utterance) -> bool:
        """STT가 이름을 흘려 들었을 때를 건진다.

        "자비스"가 "자비수"로 오면 정확 일치는 못 잡는다. 토큰 하나씩
        호출어와 견줘 충분히 비슷하면 부른 것으로 본다.

        **짧은 토큰은 보지 않는다.** "준비"와 "준비스"는 0.8로 걸리는데,
        흔한 말이 이름이 되면 아무 때나 깨어난다.
        """
        for token in utterance.normalized.split():
            if len(token) < MIN_FUZZY_TOKEN:
                continue
            for wake in self.words:
                target = normalize(wake)
                if len(target) < MIN_FUZZY_TOKEN:
                    continue
                ratio = SequenceMatcher(None, jamo(target), jamo(token)).ratio()
                if ratio >= self.wake_fuzzy:
                    return True
        return False

    def is_stop_command(self, utterance: Utterance) -> bool:
        """말을 끊으라는 말인가.

        모델에게 묻지 않는다. 끊는 데 몇 초가 걸리면 끊는 의미가 없다.
        """
        squashed = squash(self.strip_wake_word(utterance))
        return any(squash(word) == squashed for word in STOP_WORDS)

    def strip_wake_word(self, utterance: Utterance) -> str:
        """명령 본문만 남긴다.

        호출어뿐 아니라 부름말("헤이", "야")도 걷어낸다. 그것이 명령에
        남으면 라우터가 엉뚱한 규칙에 걸릴 수 있고, 모델에게도 잡음이다.
        """
        text = utterance.text
        for token in (*self.words, *ADDRESS_PREFIXES):
            text = loose(token).sub(" ", text)
        return re.sub(r"\s+", " ", text).strip(" ,.!?~")


@dataclass(frozen=True)
class SpokenLine:
    text: str
    spoken_at: datetime

    @property
    def normalized(self) -> str:
        return normalize(self.text)

    @property
    def squashed(self) -> str:
        return squash(self.text)


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
        heard = utterance.squashed
        if not heard:
            return False
        for line in self.recent_spoken:
            if utterance.heard_at - line.spoken_at > window:
                continue
            spoken = line.squashed
            if not spoken:
                continue
            # 짧은 발화는 유사도가 튀므로 포함 관계도 함께 본다.
            if heard in spoken or spoken in heard:
                return True
            # 에코는 대답의 **일부만** 잘려 돌아온다. 앞이든 중간이든.
            # 전체와 비교하면 길이 차이에 유사도가 묻히므로 부분 비교를 쓴다.
            if partial_ratio(heard, spoken) >= threshold:
                return True
        return False


def gate(
    utterance: Utterance,
    config: WakeWordConfig,
    state: ListenerState,
    *,
    speaking: bool = False,
) -> GateDecision:
    """게이트 1~3. 모델을 부르기 전에 걸러낼 수 있는 것을 전부 걸러낸다.

    순서가 중요하다. 에코 판정이 호출어 판정보다 **먼저**여야 한다 —
    JUNVIS가 "자비스가 뭘 도와드릴까요"라고 말했을 때 그 소리가 돌아오면
    호출어를 포함하고 있기 때문이다.

    `speaking`은 JUNVIS가 지금 말하는 중인지다. 그때는 마이크로 들어오는
    것의 대부분이 자기 목소리라 규칙이 하나 더 붙는다(아래).
    """
    if utterance.is_blank:
        return GateDecision.IGNORE_EMPTY

    # 정지는 에코 판정보다 먼저다. "그만"은 짧아서 긴 대답 안 어딘가와
    # 우연히 닮을 수 있는데, 그때 못 멈추면 사용자는 갇힌다.
    if speaking and config.is_stop_command(utterance):
        return GateDecision.STOP

    if state.sounds_like_echo(
        utterance, threshold=config.echo_threshold, window=config.echo_window
    ):
        return GateDecision.IGNORE_ECHO

    if speaking:
        # 말하는 동안에는 **이름을 불러야** 끼어들 수 있다. 후속 발화 창은
        # 여기서 통하지 않는다 — 창이 열린 채 자기 목소리가 돌아오면
        # 에코 필터를 한 번만 빠져나가도 무한 루프가 된다. 실제로 그랬다.
        return (
            GateDecision.ACT
            if config.contains_wake_word(utterance)
            else GateDecision.IGNORE_ECHO
        )

    if config.contains_wake_word(utterance):
        return GateDecision.ACT
    if state.is_awake(utterance.heard_at):
        return GateDecision.ACT  # 후속 발화 창
    return GateDecision.IGNORE_NO_WAKE_WORD
