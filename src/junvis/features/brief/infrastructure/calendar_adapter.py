"""macOS Calendar.app에서 오늘 일정을 읽는다.

Google Calendar API를 쓰지 않는 이유: Calendar.app이 이미 구독 캘린더를
전부 들고 있고, OAuth 토큰을 하나 더 관리할 이유가 없다.

**기본값은 꺼짐이다.** `JUNVIS_CALENDAR=1`로 켠다. 이유:

1. AppleScript로 Calendar.app에 묻는 것은 느리다(수 초).
2. 첫 실행에서 권한 대화상자가 뜬다. launchd가 매일 아침 백그라운드로
   브리핑을 돌리는데, 거기서 대화상자를 기다리며 멈추면 브리핑이 통째로
   늦어진다.

켜지 않아도 나머지 섹션은 전부 나온다. 제대로 된 해법은 아키텍처 문서의
Swift 헬퍼(`junvis-mac`)에서 EventKit을 쓰는 것이며, 그때 이 어댑터를 교체한다.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from datetime import datetime, timedelta

from junvis.features.brief.domain.digests import CalendarEvent

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10
FIELD_SEP = "\x1f"
RECORD_SEP = "\x1e"

#: 캘린더 조회를 켜는 환경변수. 기본은 꺼짐.
ENABLE_ENV = "JUNVIS_CALENDAR"


def calendar_enabled() -> bool:
    return os.environ.get(ENABLE_ENV, "").strip() not in {"", "0", "false", "no"}

#: Calendar.app에 오늘 0시~24시 사이에 시작하는 이벤트만 묻는다.
_SCRIPT = f"""
set output to ""
set dayStart to (current date)
set hours of dayStart to 0
set minutes of dayStart to 0
set seconds of dayStart to 0
set dayEnd to dayStart + (1 * days)
tell application "Calendar"
    repeat with cal in calendars
        repeat with evt in (every event of cal whose start date is greater than or equal to dayStart and start date is less than dayEnd)
            set output to output & (summary of evt) & "{FIELD_SEP}" & ((start date of evt) as string) & "{FIELD_SEP}" & (location of evt as string) & "{FIELD_SEP}" & (allday event of evt as string) & "{RECORD_SEP}"
        end repeat
    end repeat
end tell
return output
"""


class MacCalendarAdapter:
    def __init__(self, *, timeout: int = TIMEOUT_SECONDS) -> None:
        self._timeout = timeout

    def today(self, now: datetime) -> tuple[CalendarEvent, ...]:
        if platform.system() != "Darwin" or not calendar_enabled():
            return ()
        output = self._run()
        return self.parse(output, now) if output else ()

    def _run(self) -> str | None:
        try:
            result = subprocess.run(
                ["osascript", "-e", _SCRIPT],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("캘린더 조회 실패: %s", exc)
            return None
        if result.returncode != 0:
            logger.debug("캘린더 조회 거부(권한?): %s", result.stderr.strip()[:200])
            return None
        return result.stdout

    @staticmethod
    def parse(output: str, now: datetime) -> tuple[CalendarEvent, ...]:
        """AppleScript 출력을 파싱한다. 파서만 따로 테스트할 수 있게 분리했다."""
        events: list[CalendarEvent] = []
        for record in output.split(RECORD_SEP):
            fields = record.split(FIELD_SEP)
            if len(fields) < 4 or not fields[0].strip():
                continue
            title, raw_start, location, all_day = (f.strip() for f in fields[:4])
            starts_at = _parse_apple_date(raw_start) or now.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            events.append(
                CalendarEvent(
                    title=title,
                    starts_at=starts_at,
                    location="" if location in {"missing value", ""} else location,
                    all_day=all_day.lower() == "true",
                )
            )
        return tuple(sorted(events, key=lambda e: e.starts_at))


#: AppleScript의 `date as string`은 로케일을 따른다. 몇 가지 흔한 형태를 시도한다.
_DATE_FORMATS = (
    "%A, %B %d, %Y at %I:%M:%S %p",
    "%A, %d %B %Y at %H:%M:%S",
    "%Y년 %m월 %d일 %A 오전 %I:%M:%S",
    "%Y년 %m월 %d일 %A 오후 %I:%M:%S",
    "%Y-%m-%d %H:%M:%S",
)


def _parse_apple_date(raw: str) -> datetime | None:
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        if "오후" in raw and parsed.hour < 12:
            parsed += timedelta(hours=12)
        return parsed.astimezone()
    logger.debug("캘린더 날짜 형식을 알 수 없음: %r", raw)
    return None
