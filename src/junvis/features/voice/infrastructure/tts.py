"""말하기.

macOS `say`를 쓰는 이유: 기본 내장이라 설치가 필요 없다. 1단계 분석에서
Piper(60MB)를 좋게 봤지만, 그것은 품질을 올리고 싶을 때의 선택이지
시작점이 아니다. `TtsPort` 뒤에 있으므로 나중에 교체하면 된다.
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

    def speak(self, text: str) -> bool:
        if not text.strip() or platform.system() != "Darwin":
            return False
        command = ["say"]
        if self._voice:
            command += ["-v", self._voice]
        if self._rate:
            command += ["-r", str(self._rate)]
        command.append(text)
        try:
            result = subprocess.run(
                command, capture_output=True, timeout=TIMEOUT_SECONDS, check=False
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("say 실패: %s", exc)
            return False
        return result.returncode == 0


class NullTts:
    """말하지 않고 기록만 한다.

    비-macOS 환경과 테스트가 같은 경로를 쓴다. `--quiet`로 화면만 볼 때도 쓴다.

    `speak()`가 True를 돌려주는 것은 "받아들였다"는 뜻이지 "소리가 났다"는
    뜻이 아니다. 음성 파이프라인은 이걸로 끊기면 안 되기 때문이다.
    실제로 들렸는지는 `audible`이 답한다.
    """

    audible = False

    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str) -> bool:
        if not text.strip():
            return False
        self.spoken.append(text)
        return True


def default_tts() -> MacSayTts | NullTts:
    return MacSayTts() if platform.system() == "Darwin" else NullTts()
