"""Trace에서 작업 습관을 뽑아낸다.

설계 §5.2에서 "Trace는 로그가 아니라 개인화의 원재료"라고 했던 것이
처음으로 현금화되는 지점이다.

집계를 SQL이 아니라 파이썬에서 하는 이유: 저장된 시각은 UTC인데 사용자가
알고 싶은 것은 **자기 시간대의** 활동 시간대다. SQLite의 `localtime`은
서버 TZ에 의존해 조용히 틀린 답을 낸다.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from junvis.core.persistence.database import Database
from junvis.features.brief.domain.digests import HabitDigest

WINDOW_DAYS = 7
#: 개인 규모에서 7일치가 이보다 많을 일은 없다. 폭주 방지용 상한.
MAX_ROWS = 5000
TOP_TOOLS = 3

#: 브리핑 자신의 실행은 사용자 활동이 아니다.
#: launchd가 매일 아침 브리핑을 돌리므로, 이걸 세면 "가장 활발한 시간대"가
#: 결국 브리핑 시각으로 수렴한다. 자기 집계로 통계를 오염시키지 않는다.
EXCLUDED_REQUESTS = frozenset({"brief.compose"})


class TraceHabitAnalyzer:
    def __init__(self, db: Database) -> None:
        self._db = db

    def digest(self, now: datetime) -> HabitDigest | None:
        since = now - timedelta(days=WINDOW_DAYS)
        placeholders = ", ".join("?" for _ in EXCLUDED_REQUESTS)
        rows = self._db.query(
            f"""
            SELECT occurred_at, outcome, request
            FROM traces
            WHERE occurred_at >= ? AND request NOT IN ({placeholders})
            ORDER BY occurred_at DESC
            LIMIT ?
            """,
            (since.isoformat(), *sorted(EXCLUDED_REQUESTS), MAX_ROWS),
        )
        if not rows:
            return None

        hours: Counter[int] = Counter()
        requests: Counter[str] = Counter()
        failures = 0

        for row in rows:
            if row["outcome"] != "ok":
                failures += 1
            requests[row["request"]] += 1
            moment = self._parse(row["occurred_at"])
            if moment is not None:
                # 저장은 UTC, 관심은 로컬 시간대.
                hours[moment.astimezone().hour] += 1

        return HabitDigest(
            runs_last_7d=len(rows),
            failures_last_7d=failures,
            busiest_hour=hours.most_common(1)[0][0] if hours else None,
            top_tools=tuple(name for name, _ in requests.most_common(TOP_TOOLS)),
        )

    @staticmethod
    def _parse(raw: str) -> datetime | None:
        try:
            return datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            return None
