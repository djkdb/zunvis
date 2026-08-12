"""오브 서버 — 상태를 읽어 주는 창구 하나가 전부다."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from junvis.apps.orb.server import HOST, build_server
from junvis.features.voice.domain.model import Presence
from junvis.features.voice.infrastructure.presence import STATE_FILENAME, FilePresence


@pytest.fixture()
def orb(tmp_path: Path) -> Iterator[tuple[str, FilePresence]]:
    presence_path = tmp_path / STATE_FILENAME
    # 포트 0을 주면 OS가 빈 포트를 고른다. 테스트끼리 충돌하지 않는다.
    server = build_server(presence_path, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{HOST}:{server.server_address[1]}", FilePresence(presence_path)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def fetch(url: str) -> tuple[int, bytes]:
    with urlopen(url, timeout=5) as response:
        return response.status, response.read()


def test_state_starts_asleep(orb) -> None:
    """상태 파일이 없어도 화면은 뜬다. 듣기가 먼저일 필요가 없다."""
    base, _ = orb

    _, body = fetch(f"{base}/state")

    assert json.loads(body)["presence"] == "asleep"


def test_state_follows_the_file(orb) -> None:
    base, presence = orb
    presence.show(Presence.THINKING, "오늘 브리핑")

    _, body = fetch(f"{base}/state")

    assert json.loads(body) == {"presence": "thinking", "text": "오늘 브리핑"}


def test_page_is_served(orb) -> None:
    base, _ = orb

    status, body = fetch(f"{base}/")

    assert status == 200
    assert b"<canvas id=\"sky\">" in body


def test_unknown_path_is_404(orb) -> None:
    base, _ = orb

    with pytest.raises(HTTPError) as caught:
        fetch(f"{base}/secrets")

    assert caught.value.code == 404


def test_state_is_never_cached(orb) -> None:
    """캐시되면 오브가 옛 상태를 계속 보여준다."""
    base, _ = orb

    with urlopen(f"{base}/state", timeout=5) as response:
        assert response.headers["Cache-Control"] == "no-store"
