"""말하기.

macOS `say`를 쓰는 이유: 기본 내장이라 설치가 필요 없다. 1단계 분석에서
Piper(60MB)를 좋게 봤지만, 그것은 품질을 올리고 싶을 때의 선택이지
시작점이 아니다. `TtsPort` 뒤에 있으므로 나중에 교체하면 된다.

## 왜 기다리지 않는가

처음에는 `speak()`가 끝날 때까지 블로킹했다. 그러면 **말하는 동안 마이크를
한 번도 읽지 않는다.** 긴 브리핑이 시작되면 끝날 때까지 손도 못 댄다.

지금은 시작만 하고 돌아온다. 듣기 루프가 계속 돌아서 "그만"을 들을 수 있고,
말을 끊고 다른 것을 시킬 수도 있다. 끝까지 기다려야 하는 쪽(`junvis say`)은
`wait()`를 부른다.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 60
VOICE_ENV = "JUNVIS_VOICE"
RATE_ENV = "JUNVIS_VOICE_RATE"


class MacSayTts:
    """macOS 내장 `say`. 이 저장소에서는 검증되지 않는다(Linux 컨테이너)."""

    #: 실제로 소리가 나는가. `junvis say`가 사용자에게 사실대로 말하기 위해 필요하다.
    audible = True

    def __init__(self, voice: str | None = None, rate: int | None = None) -> None:
        self._voice = voice or os.environ.get(VOICE_ENV)
        raw_rate = rate if rate is not None else os.environ.get(RATE_ENV)
        self._rate = int(raw_rate) if raw_rate else None
        self._process: subprocess.Popen | None = None

    @property
    def speaking(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def speak(self, text: str) -> bool:
        """말하기를 **시작한다.** 끝날 때까지 기다리지 않는다."""
        if not text.strip() or platform.system() != "Darwin":
            return False
        self.stop()  # 앞말이 남아 있으면 겹친다

        command = ["say"]
        if self._voice:
            command += ["-v", self._voice]
        if self._rate:
            command += ["-r", str(self._rate)]
        command.append(text)
        try:
            self._process = subprocess.Popen(
                command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("say 실패: %s", exc)
            self._process = None
            return False
        return True

    def stop(self) -> None:
        """말하는 중이면 끊는다. 아니면 아무 일도 없다."""
        process, self._process = self._process, None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:  # pragma: no cover - 방어적
            process.kill()

    def wait(self) -> None:
        if self._process is None:
            return
        try:
            self._process.wait(timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:  # pragma: no cover - 방어적
            self.stop()


class NullTts:
    """말하지 않고 기록만 한다.

    비-macOS 환경과 테스트가 같은 경로를 쓴다. `--quiet`로 화면만 볼 때도 쓴다.

    `speak()`가 True를 돌려주는 것은 "받아들였다"는 뜻이지 "소리가 났다"는
    뜻이 아니다. 음성 파이프라인은 이걸로 끊기면 안 되기 때문이다.
    실제로 들렸는지는 `audible`이 답한다.
    """

    audible = False
    speaking = False

    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.stopped = 0

    def speak(self, text: str) -> bool:
        if not text.strip():
            return False
        self.spoken.append(text)
        return True

    def stop(self) -> None:
        self.stopped += 1

    def wait(self) -> None:
        return None


def default_tts() -> MacSayTts | NullTts:
    return MacSayTts() if platform.system() == "Darwin" else NullTts()
