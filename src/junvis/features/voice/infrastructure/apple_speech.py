"""macOS 내장 음성 인식을 **컴파일 없이** 쓴다.

Swift 헬퍼를 먼저 만들었지만 실제 맥에서 Apple 툴체인이 깨져 있어
컴파일 자체가 되지 않았다(SDK와 컴파일러 버전 불일치). 그런데 우리가
Swift에서 쓰려던 것 — `SFSpeechRecognizer`, `AVAudioEngine` — 은 전부
Objective-C 프레임워크이고, PyObjC로 Python에서 그대로 부를 수 있다.

컴파일러가 필요 없다는 것이 핵심이다. 설치만 되면 동작하고, 깨질 곳이
하나 줄어든다. Swift 헬퍼는 화면 캡처·접근성처럼 **정말로** Swift가
필요한 것들을 위해 남겨 둔다.

    uv pip install -e ".[mac]"

인식은 **온디바이스로 못박는다.** 개인 기억이 애플 서버로 나가면 안 된다.
"""

from __future__ import annotations

import logging
import queue
import threading
from time import monotonic
from collections.abc import Iterator

from junvis.features.voice.domain.model import DEFAULT_WAKE_WORDS, Utterance
from junvis.features.voice.infrastructure.audio import AudioUnavailable
from junvis.features.voice.infrastructure.clap import ClapDetector, root_mean_square

logger = logging.getLogger(__name__)

INSTALL_HINT = (
    "macOS 음성 인식을 쓰려면 PyObjC가 필요합니다:\n"
    '  uv pip install -e ".[mac]"\n'
    "또는 `junvis listen --stdin` 으로 텍스트 입력을 쓰세요."
)

#: 이 아래 신뢰도는 버린다. 무음에서 만들어낸 헛것을 거른다.
MIN_CONFIDENCE = 0.3

#: 런루프를 한 번에 이만큼씩 돌린다. 길면 응답이 굼뜨고 짧으면 CPU를 먹는다.
PUMP_SECONDS = 0.1

#: 받아쓰기가 이만큼 안 바뀌면 한 발화가 끝난 것으로 본다.
#:
#: `isFinal`을 기다리면 안 된다. 연속 스트림에서 그것은 `endAudio()`를
#: 부를 때까지 **영원히 오지 않는다.** 마이크는 열려 있는데 아무 일도
#: 일어나지 않는 상태가 된다. 실제로 그랬다.
SILENCE_SECONDS = 1.2

#: 인식 태스크 하나를 이보다 오래 끌지 않는다. macOS가 1분쯤에서 끊는다.
TASK_SECONDS = 45


def available() -> bool:
    try:
        import AVFoundation  # noqa: F401
        import Speech  # noqa: F401
    except Exception:
        return False
    return True


class AppleSpeechSource:
    """마이크 하나를 붙잡고 받아쓰기와 박수를 동시에 본다.

    같은 오디오 탭에서 갈라지는 것이 중요하다. 마이크를 두 번 열면
    macOS가 하나를 거부한다.
    """

    def __init__(
        self,
        *,
        wake_words: tuple[str, ...] = DEFAULT_WAKE_WORDS,
        locale: str = "ko-KR",
        detector: ClapDetector | None = None,
    ) -> None:
        self._wake_words = wake_words
        self._locale = locale
        self._detector = detector or ClapDetector()
        self._queue: queue.Queue[Utterance] = queue.Queue()
        self._elapsed = 0.0
        self._last_text = ""
        self._engine = None
        self._task = None
        self._request = None
        self._recognizer = None
        self._partial = ""
        self._partial_at = 0.0
        self._task_started_at = 0.0
        #: 버퍼에서 샘플을 못 꺼내면 박수만 포기한다. 받아쓰기는 살린다.
        self._claps_work = True

    # -- 준비 ---------------------------------------------------------------

    def check(self) -> None:
        """말을 걸고 나서 안 된다는 걸 알면 늦다."""
        if not available():
            raise AudioUnavailable(INSTALL_HINT)
        self._authorize()

    def _authorize(self) -> None:
        import AVFoundation
        import Speech

        done = threading.Event()
        granted = {"speech": False, "microphone": False}

        def on_speech(status) -> None:
            granted["speech"] = status == Speech.SFSpeechRecognizerAuthorizationStatusAuthorized
            done.set()

        Speech.SFSpeechRecognizer.requestAuthorization_(on_speech)
        self._pump_until(done, seconds=30)
        if not granted["speech"]:
            raise AudioUnavailable(
                "음성 인식 권한이 없습니다.\n"
                "  시스템 설정 → 개인정보 보호 및 보안 → 음성 인식 에서 터미널을 켜세요."
            )

        done = threading.Event()

        def on_microphone(ok) -> None:
            granted["microphone"] = bool(ok)
            done.set()

        AVFoundation.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
            AVFoundation.AVMediaTypeAudio, on_microphone
        )
        self._pump_until(done, seconds=30)
        if not granted["microphone"]:
            raise AudioUnavailable(
                "마이크 권한이 없습니다.\n"
                "  시스템 설정 → 개인정보 보호 및 보안 → 마이크 에서 터미널을 켜세요."
            )

    @staticmethod
    def _pump_until(event: threading.Event, *, seconds: float) -> None:
        """권한 콜백은 런루프에서 온다. 그냥 기다리면 영원히 안 온다."""
        from Foundation import NSDate, NSRunLoop

        loop = NSRunLoop.currentRunLoop()
        waited = 0.0
        while not event.is_set() and waited < seconds:
            loop.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(PUMP_SECONDS))
            waited += PUMP_SECONDS

    # -- 듣기 ---------------------------------------------------------------

    def listen(self) -> Iterator[Utterance]:
        self.check()
        self._start()
        try:
            yield from self._drain_forever()
        finally:
            self.stop()

    def _drain_forever(self) -> Iterator[Utterance]:
        from Foundation import NSDate, NSRunLoop

        loop = NSRunLoop.currentRunLoop()
        while True:
            # 콜백은 런루프에서 돈다. 여기서 조금씩 돌려 주지 않으면
            # 마이크가 열려 있어도 아무 일도 일어나지 않는다.
            loop.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(PUMP_SECONDS))
            self._settle()
            while True:
                try:
                    yield self._queue.get_nowait()
                except queue.Empty:
                    break

    def _settle(self) -> None:
        """말이 멈췄으면 거기까지를 한 발화로 끊는다.

        `isFinal`을 기다리지 않는 이유가 여기 있다(SILENCE_SECONDS 주석).
        """
        now = monotonic()
        if self._partial and now - self._partial_at >= SILENCE_SECONDS:
            text, self._partial = self._partial, ""
            self._queue.put(Utterance(text=text))
            self._restart_task()
            return

        # 말이 없어도 태스크는 늙는다. 조용할 때만 갈아 끼운다 —
        # 말하는 도중에 끊으면 그 발화를 통째로 잃는다.
        if not self._partial and now - self._task_started_at >= TASK_SECONDS:
            self._restart_task()

    def _restart_task(self) -> None:
        """새 요청과 태스크를 건다. 오디오 탭과 엔진은 그대로 둔다."""
        import Speech

        old_request, old_task = self._request, self._task
        request = Speech.SFSpeechAudioBufferRecognitionRequest.alloc().init()
        # 부분 결과를 켠다. 이것이 없으면 아무것도 오지 않는다.
        request.setShouldReportPartialResults_(True)
        # 온디바이스로 못박는다. 개인 기억이 애플 서버로 나가면 안 된다.
        request.setRequiresOnDeviceRecognition_(True)

        self._request = request
        self._partial = ""
        self._task_started_at = monotonic()
        self._task = self._recognizer.recognitionTaskWithRequest_resultHandler_(
            request, self._on_result
        )

        if old_request is not None:
            old_request.endAudio()
        if old_task is not None:
            old_task.cancel()

    def _start(self) -> None:
        import AVFoundation
        import Speech
        from Foundation import NSLocale

        recognizer = Speech.SFSpeechRecognizer.alloc().initWithLocale_(
            NSLocale.localeWithLocaleIdentifier_(self._locale)
        )
        if recognizer is None or not recognizer.isAvailable():
            raise AudioUnavailable(
                f"이 언어의 음성 인식을 쓸 수 없습니다: {self._locale}\n"
                "  시스템 설정 → 키보드 → 받아쓰기 에서 해당 언어를 내려받으세요."
            )

        if not recognizer.supportsOnDeviceRecognition():
            raise AudioUnavailable(
                f"이 맥에는 {self._locale} 온디바이스 음성 인식이 없습니다.\n"
                "  시스템 설정 → 키보드 → 받아쓰기 를 켜고 한국어를 내려받으세요.\n"
                "  (개인 기억이 애플 서버로 나가면 안 되므로 온디바이스만 씁니다.)"
            )
        self._recognizer = recognizer

        engine = AVFoundation.AVAudioEngine.alloc().init()
        node = engine.inputNode()
        audio_format = node.outputFormatForBus_(0)
        sample_rate = audio_format.sampleRate() or 44100.0

        def on_buffer(buffer, _when) -> None:
            try:
                # self._request를 본다. 태스크를 갈아 끼워도 탭은 그대로다.
                request = self._request
                if request is not None:
                    request.appendAudioPCMBuffer_(buffer)
                self._inspect(buffer, sample_rate)
            except Exception as exc:  # pragma: no cover - 오디오 콜백
                logger.debug("오디오 버퍼 처리 실패: %s", exc)

        node.installTapOnBus_bufferSize_format_block_(0, 1024, audio_format, on_buffer)
        self._restart_task()

        engine.prepare()
        ok, error = engine.startAndReturnError_(None)
        if not ok:
            raise AudioUnavailable(f"마이크를 열지 못했습니다: {error}")
        self._engine = engine

    def stop(self) -> None:
        try:
            if self._engine is not None:
                self._engine.inputNode().removeTapOnBus_(0)
                self._engine.stop()
            if self._request is not None:
                self._request.endAudio()
            if self._task is not None:
                self._task.cancel()
        except Exception as exc:  # pragma: no cover - 종료 경로
            logger.debug("정리 중 문제: %s", exc)
        finally:
            self._engine = self._request = self._task = None

    # -- 콜백 ---------------------------------------------------------------

    def _on_result(self, result, error) -> None:
        """부분 결과가 계속 들어온다. 끊는 판단은 `_settle`이 한다.

        부분 결과의 신뢰도는 0이므로 여기서 신뢰도로 거르지 않는다.
        걸러야 할 잡음은 호출어 게이트와 Intent Judge가 이미 막는다.
        """
        if error is not None:
            logger.debug("받아쓰기: %s", error)
            return
        if result is None:
            return

        text = str(result.bestTranscription().formattedString()).strip()
        if not text or text == self._partial:
            return
        self._partial = text
        self._partial_at = monotonic()

    @staticmethod
    def _confidence(transcription) -> float:
        segments = transcription.segments()
        if not segments:
            return 1.0
        total = sum(float(segment.confidence()) for segment in segments)
        return total / len(segments)

    def _inspect(self, buffer, sample_rate: float) -> None:
        if not self._claps_work:
            return
        frames = int(buffer.frameLength())
        if frames <= 0:
            return

        samples = self._samples(buffer, frames)
        if samples is None:
            # 이 맥에서는 원시 샘플을 못 꺼낸다. 박수만 포기하고
            # 받아쓰기는 계속한다 — 절반이라도 되는 편이 낫다.
            logger.warning("박수 감지를 끕니다. 호출어는 그대로 동작합니다.")
            self._claps_work = False
            return

        self._elapsed += frames / sample_rate
        self._detector.expire(self._elapsed)
        if self._detector.feed(root_mean_square(samples), self._elapsed) is not None:
            # 박수 = 이름을 부른 것. 기존 게이트가 그대로 처리한다.
            self._queue.put(Utterance(text=self._wake_words[0]))

    @staticmethod
    def _samples(buffer, frames: int):
        """PyObjC가 float 포인터를 넘겨주는 방식이 버전마다 다르다.

        되는 것을 찾을 때까지 시도한다. 전부 실패하면 None을 돌려주고
        호출자가 박수만 포기한다.
        """
        try:
            channel = buffer.floatChannelData()[0]
        except Exception:
            return None

        for extract in (
            lambda: channel.as_tuple(frames),
            lambda: [channel[index] for index in range(frames)],
        ):
            try:
                return extract()
            except Exception:
                continue
        return None
