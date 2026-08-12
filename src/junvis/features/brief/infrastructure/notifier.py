"""macOS 알림 센터로 한 줄 요약을 보낸다.

launchd가 아침에 브리핑을 돌릴 때, 로그 파일에만 쓰면 아무도 보지 않는다.
"""

from __future__ import annotations

import logging
import platform
import subprocess

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5
TITLE = "JUNVIS"


def _escape(text: str) -> str:
    """AppleScript 문자열 리터럴로 안전하게 넣는다."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def notify(message: str, *, subtitle: str = "") -> bool:
    """보냈으면 True. macOS가 아니거나 실패하면 False (예외를 던지지 않는다)."""
    if platform.system() != "Darwin":
        return False
    script = f'display notification "{_escape(message)}" with title "{TITLE}"'
    if subtitle:
        script += f' subtitle "{_escape(subtitle)}"'
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("알림 전송 실패: %s", exc)
        return False
    return result.returncode == 0
