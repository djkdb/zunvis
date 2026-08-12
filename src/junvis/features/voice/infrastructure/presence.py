"""상태를 밖으로 내보내는 어댑터들.

`junvis listen`과 오브(`junvis orb`)는 **다른 프로세스**다. 그래서 상태를
파일 하나로 주고받는다. 소켓이나 서버를 세우면 듣기가 화면에 의존하게
되는데, 그건 순서가 거꾸로다 — 화면은 없어도 되는 것이다.

쓰기는 원자적이다. 오브가 반쯤 쓰인 JSON을 읽으면 화면이 깜빡인다.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from junvis.features.voice.domain.model import Presence

logger = logging.getLogger(__name__)

STATE_FILENAME = "presence.json"

#: 이 시간 넘게 갱신이 없으면 오브는 잠든 것으로 본다.
#: `junvis listen`이 죽었는데 화면만 깨어 있는 상태를 막는다.
STALE_SECONDS = 90


class NullPresence:
    """아무것도 보여주지 않는다.

    테스트와, 사람이 보고 있지 않은 경로(MCP 서버·launchd)를 위한 것이다.
    상태를 내보내지 않는 것이 정상인 자리가 분명히 있다.
    """

    def show(self, presence: Presence, text: str = "") -> None:
        return None


class FilePresence:
    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def show(self, presence: Presence, text: str = "") -> None:
        payload = {
            "presence": presence.value,
            "text": text,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._write(json.dumps(payload, ensure_ascii=False))
        except OSError as exc:  # pragma: no cover - 방어적
            logger.debug("상태 파일을 쓰지 못했습니다: %s", exc)

    def _write(self, body: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # 같은 디렉터리에 쓰고 rename 한다. os.replace는 원자적이므로
        # 오브가 반쯤 쓰인 파일을 볼 일이 없다.
        handle, temporary = tempfile.mkstemp(
            dir=self._path.parent, prefix=".presence-", suffix=".json"
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                file.write(body)
            os.replace(temporary, self._path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise


def read_presence(path: Path) -> dict:
    """오브가 읽는 쪽. 없거나 깨졌거나 오래됐으면 잠든 것으로 본다."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _asleep()

    if not isinstance(payload, dict):
        return _asleep()
    if _age_seconds(payload.get("at")) > STALE_SECONDS:
        # 듣기가 죽었다. 마지막 상태로 계속 빛나고 있으면 거짓말이 된다.
        return _asleep()

    presence = str(payload.get("presence", Presence.ASLEEP.value))
    if presence not in {member.value for member in Presence}:
        return _asleep()
    return {"presence": presence, "text": str(payload.get("text", ""))}


def _asleep() -> dict:
    return {"presence": Presence.ASLEEP.value, "text": ""}


def _age_seconds(raw: object) -> float:
    if not isinstance(raw, str):
        return float("inf")
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return float("inf")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - moment).total_seconds()
