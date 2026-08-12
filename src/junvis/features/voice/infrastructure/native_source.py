"""네이티브 헬퍼(`junvis-mac`)를 발화 소스로 쓴다.

헬퍼는 stdout에 JSON Lines를 뱉고 여기서는 그것만 읽는다(docs/08 §1).
그래서 헬퍼가 Swift든 무엇이든 이 파일은 바뀌지 않으며, 가짜 헬퍼로
전 경로를 테스트할 수 있다.

**박수 두 번은 이름을 부른 것으로 다룬다.** 새 도메인 개념을 만들지 않고
호출어만 부른 발화로 바꿔 넣으면, 기존 게이트가 "네?" 하고 후속 발화 창을
열어 준다. 게이트를 도메인에 둔 값어치가 여기서 나온다.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from collections.abc import Iterator
from datetime import datetime, timezone

from junvis.features.voice.domain.model import DEFAULT_WAKE_WORDS, Utterance
from junvis.features.voice.infrastructure.audio import AudioUnavailable

logger = logging.getLogger(__name__)

HELPER_BIN_ENV = "JUNVIS_MAC_BIN"
DEFAULT_HELPER = "junvis-mac"

#: 박수 몇 번을 부름으로 볼지.
CLAP_COUNT = 2

#: 이 아래 신뢰도는 버린다. Whisper·Speech 모두 무음에서 헛것을 만든다.
MIN_CONFIDENCE = 0.3


class NativeHelperSource:
    def __init__(
        self,
        *,
        wake_words: tuple[str, ...] = DEFAULT_WAKE_WORDS,
        binary: str | None = None,
        clap_count: int = CLAP_COUNT,
        extra_args: tuple[str, ...] = (),
    ) -> None:
        self._wake_words = wake_words
        self._binary = binary or os.environ.get(HELPER_BIN_ENV) or DEFAULT_HELPER
        self._clap_count = clap_count
        self._extra_args = extra_args

    @property
    def binary(self) -> str:
        return self._binary

    def check(self) -> None:
        """말을 걸고 나서 헬퍼가 없다는 걸 알면 늦다."""
        if shutil.which(self._binary) is None:
            raise AudioUnavailable(
                f"네이티브 헬퍼를 찾지 못했습니다: {self._binary}\n"
                "  ./scripts/build-mac.sh 로 빌드하세요.\n"
                "또는 `junvis listen --stdin` 으로 텍스트 입력을 쓰세요."
            )

    def command(self) -> list[str]:
        return [
            self._binary,
            "listen",
            "--wake",
            ",".join(self._wake_words),
            "--clap",
            str(self._clap_count),
            *self._extra_args,
        ]

    def listen(self) -> Iterator[Utterance]:
        self.check()
        process = subprocess.Popen(
            self.command(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,  # 줄 단위. 버퍼에 갇히면 실시간이 아니다
        )
        try:
            assert process.stdout is not None
            yield from self.parse(process.stdout)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover - 방어적
                process.kill()

    def parse(self, lines: Iterator[str]) -> Iterator[Utterance]:
        """JSON Lines를 발화로 바꾼다. 파서만 따로 테스트할 수 있게 분리했다."""
        for line in lines:
            event = self._decode(line)
            if event is None:
                continue
            utterance = self._to_utterance(event)
            if utterance is not None:
                yield utterance

    # -- 내부 ---------------------------------------------------------------

    @staticmethod
    def _decode(line: str) -> dict | None:
        text = line.strip()
        if not text:
            return None
        try:
            event = json.loads(text)
        except json.JSONDecodeError:
            # 헬퍼가 로그를 stdout에 섞어도 파이프라인이 죽지 않는다.
            logger.debug("헬퍼가 보낸 JSON이 아닌 줄: %r", text[:120])
            return None
        return event if isinstance(event, dict) else None

    def _to_utterance(self, event: dict) -> Utterance | None:
        kind = event.get("type")

        if kind == "transcript":
            text = str(event.get("text", "")).strip()
            confidence = float(event.get("confidence", 1.0) or 0.0)
            if not text or confidence < MIN_CONFIDENCE:
                return None
            return Utterance(
                text=text, heard_at=_moment(event), confidence=confidence
            )

        if kind == "clap":
            if int(event.get("count", 0)) < self._clap_count:
                return None
            # 박수 = 이름을 부른 것. 기존 게이트가 그대로 처리한다.
            return Utterance(text=self._wake_words[0], heard_at=_moment(event))

        if kind == "error":
            logger.warning("네이티브 헬퍼: %s", event.get("message", ""))
        return None


def _moment(event: dict) -> datetime:
    raw = event.get("at")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            pass
    return datetime.now(timezone.utc)
