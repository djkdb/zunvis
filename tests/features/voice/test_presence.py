"""상태 표시 — 보여주기만 하고 판단에는 끼어들지 않는다."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from junvis.features.voice.domain.model import Presence
from junvis.features.voice.infrastructure.presence import (
    STALE_SECONDS,
    STATE_FILENAME,
    FilePresence,
    NullPresence,
    read_presence,
)


@pytest.fixture()
def presence_path(tmp_path: Path) -> Path:
    return tmp_path / STATE_FILENAME


def test_null_presence_leaves_no_trace(tmp_path: Path) -> None:
    NullPresence().show(Presence.AWAKE, "네?")
    assert list(tmp_path.iterdir()) == []


def test_written_state_is_read_back(presence_path: Path) -> None:
    FilePresence(presence_path).show(Presence.SPEAKING, "오늘 브리핑입니다")

    assert read_presence(presence_path) == {
        "presence": "speaking",
        "text": "오늘 브리핑입니다",
    }


def test_missing_file_reads_as_asleep(presence_path: Path) -> None:
    assert read_presence(presence_path)["presence"] == "asleep"


def test_broken_file_reads_as_asleep(presence_path: Path) -> None:
    """오브가 반쯤 쓰인 JSON을 봐도 깜빡이지 않는다."""
    presence_path.write_text("{잘린", encoding="utf-8")

    assert read_presence(presence_path)["presence"] == "asleep"


def test_stale_state_reads_as_asleep(presence_path: Path) -> None:
    """듣기가 죽었는데 화면만 깨어 있으면 거짓말이 된다."""
    old = datetime.now(timezone.utc) - timedelta(seconds=STALE_SECONDS + 5)
    presence_path.write_text(
        json.dumps({"presence": "awake", "text": "", "at": old.isoformat()}),
        encoding="utf-8",
    )

    assert read_presence(presence_path)["presence"] == "asleep"


def test_unknown_presence_reads_as_asleep(presence_path: Path) -> None:
    presence_path.write_text(
        json.dumps(
            {
                "presence": "황홀경",
                "text": "",
                "at": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    assert read_presence(presence_path)["presence"] == "asleep"


def test_writing_leaves_no_temporary_files(presence_path: Path) -> None:
    """원자적 쓰기의 임시 파일이 남으면 홈이 지저분해진다."""
    presence = FilePresence(presence_path)
    for _ in range(5):
        presence.show(Presence.THINKING, "프로젝트 목록")

    assert [p.name for p in presence_path.parent.iterdir()] == [STATE_FILENAME]
