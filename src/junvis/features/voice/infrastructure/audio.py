"""발화를 하나씩 내놓는 소스.

`StdinSource`가 장식이 아닌 이유: 어떤 STT를 쓰든 파이프로 연결하면 JUNVIS가
동작한다. 판단 파이프라인이 오디오 스택과 분리되어 있다는 증거이기도 하다.

`SoxWhisperSource`는 이 저장소에서 검증되지 않는다 — 컨테이너에 마이크가 없다.
상시 대기 마이크와 온디바이스 Wake word는 Swift 헬퍼(`junvis-mac`)의 몫이며,
그때 이 파일의 구현만 교체하면 판단 파이프라인은 그대로 쓴다.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

from junvis.core.domain.errors import JunvisError
from junvis.features.voice.domain.model import Utterance

logger = logging.getLogger(__name__)

WHISPER_MODEL_ENV = "JUNVIS_WHISPER_MODEL"
WHISPER_BIN_ENV = "JUNVIS_WHISPER_BIN"
DEFAULT_WHISPER_BIN = "whisper-cli"

#: 무음이 이만큼 이어지면 발화가 끝난 것으로 본다.
SILENCE_SECONDS = 1.5
#: 한 번에 녹음할 최대 길이. 무한정 붙잡고 있지 않게 한다.
MAX_RECORD_SECONDS = 30


class AudioUnavailable(JunvisError):
    """녹음이나 인식에 필요한 도구가 없다."""


def _easier_path() -> str:
    """맥에서는 이 길이 더 쉽다. 막힌 사람에게 그 사실을 알려준다.

    네이티브 헬퍼는 macOS 내장 음성 인식을 쓴다 — brew도, 모델 내려받기도
    필요 없고 상시 대기와 박수까지 된다. 여기서 안내하지 않으면 사용자는
    굳이 어려운 길로 간다.
    """
    if sys.platform != "darwin":
        return ""
    return (
        "\n\n더 쉬운 길: 맥 내장 음성 인식을 쓰면 위의 것들이 필요 없습니다.\n"
        "  ./scripts/build-mac.sh   그다음  junvis listen --native"
    )


class StdinSource:
    """표준입력 한 줄 = 발화 하나."""

    def __init__(self, stream=None) -> None:
        self._stream = stream or sys.stdin

    def listen(self) -> Iterator[Utterance]:
        for line in self._stream:
            text = line.strip()
            if text:
                yield Utterance(text=text)


class SoxWhisperSource:
    """sox로 녹음하고 whisper.cpp로 받아쓴다.

    필요한 것:
        brew install sox whisper-cpp
        JUNVIS_WHISPER_MODEL=/path/to/ggml-base.bin
    """

    def __init__(
        self,
        *,
        model_path: str | None = None,
        whisper_bin: str | None = None,
        language: str = "auto",
    ) -> None:
        self._model_path = model_path or os.environ.get(WHISPER_MODEL_ENV, "")
        self._whisper_bin = (
            whisper_bin or os.environ.get(WHISPER_BIN_ENV) or DEFAULT_WHISPER_BIN
        )
        self._language = language

    def check(self) -> None:
        """부족한 것을 **미리** 알려준다. 말을 걸고 나서 알면 늦다."""
        missing = [name for name in ("sox", self._whisper_bin) if not shutil.which(name)]
        if missing:
            raise AudioUnavailable(
                f"필요한 도구가 없습니다: {', '.join(missing)}\n"
                "  brew install sox whisper-cpp"
                f"{_easier_path()}\n"
                "또는 `junvis listen --stdin` 으로 텍스트 입력을 쓰세요."
            )
        if not self._model_path or not Path(self._model_path).is_file():
            raise AudioUnavailable(
                f"Whisper 모델을 찾을 수 없습니다. {WHISPER_MODEL_ENV}를 설정하세요.\n"
                "  예: export JUNVIS_WHISPER_MODEL=~/models/ggml-base.bin"
                f"{_easier_path()}"
            )

    def listen(self) -> Iterator[Utterance]:
        self.check()
        while True:
            audio = self._record()
            if audio is None:
                continue
            try:
                text = self._transcribe(audio)
            finally:
                audio.unlink(missing_ok=True)
            if text:
                yield Utterance(text=text)

    def _record(self) -> Path | None:
        path = Path(tempfile.mkstemp(suffix=".wav", prefix="junvis-")[1])
        command = [
            "sox", "-d", "-q", "-t", "wav", str(path),
            "rate", "16k", "channels", "1",
            # 앞쪽 무음을 잘라내고, 끝에서 무음이 이어지면 멈춘다.
            "silence", "1", "0.1", "3%", "1", f"{SILENCE_SECONDS}t", "3%",
            "trim", "0", str(MAX_RECORD_SECONDS),
        ]
        try:
            subprocess.run(command, capture_output=True, check=False, timeout=MAX_RECORD_SECONDS + 10)
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("녹음 실패: %s", exc)
            path.unlink(missing_ok=True)
            return None
        if not path.exists() or path.stat().st_size < 1024:
            path.unlink(missing_ok=True)
            return None
        return path

    def _transcribe(self, audio: Path) -> str:
        command = [
            self._whisper_bin,
            "-m", self._model_path,
            "-f", str(audio),
            "-l", self._language,
            "-nt",  # 타임스탬프 없이 본문만
        ]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, check=False, timeout=120
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("받아쓰기 실패: %s", exc)
            return ""
        if result.returncode != 0:
            logger.debug("whisper 오류: %s", result.stderr.strip()[:200])
            return ""
        return clean_transcript(result.stdout)


#: whisper가 무음 구간에서 만들어내는 대표적인 환각들.
#: 1단계 분석에서 isair/jarvis의 알려진 한계로 지적된 문제다.
HALLUCINATIONS = (
    "[음악]",
    "[박수]",
    "(음악)",
    "감사합니다",
    "시청해주셔서 감사합니다",
    "thank you for watching",
    "thanks for watching",
    "[music]",
    "[applause]",
    "you",
)


def clean_transcript(raw: str) -> str:
    """받아쓰기 결과를 다듬는다.

    무음 구간에서 나오는 상투적 환각을 걸러낸다. 이걸 안 하면 조용한
    방에서 JUNVIS가 혼자 "감사합니다"에 반응한다.
    """
    lines = [line.strip() for line in raw.splitlines()]
    text = " ".join(line for line in lines if line)
    text = " ".join(text.split())
    if not text:
        return ""
    lowered = text.lower().strip(" .!?~")
    if lowered in HALLUCINATIONS:
        return ""
    return text
