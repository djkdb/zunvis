"""오브를 띄우는 아주 작은 로컬 서버.

브라우저는 보안상 `file://`에서 다른 파일을 읽지 못한다. 그래서 상태를
읽어 주는 창구가 하나 필요하고, 그게 전부다. 표준 라이브러리만 쓴다 —
화면 하나 때문에 의존성이 늘어나면 안 된다.

**127.0.0.1에만 묶는다.** 개인 기억이 오가는 물건이므로 같은 네트워크의
다른 기기에서 열리면 안 된다.
"""

from __future__ import annotations

import json
import logging
import threading
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from junvis.features.voice.infrastructure.presence import read_presence

logger = logging.getLogger(__name__)

HOST = "127.0.0.1"
DEFAULT_PORT = 4173
PAGE = Path(__file__).with_name("page.html")


class OrbHandler(BaseHTTPRequestHandler):
    #: 인스턴스마다 다르게 채운다(`partial`로 주입).
    presence_path: Path

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler의 규약
        if self.path.startswith("/state"):
            self._json(read_presence(self.presence_path))
        elif self.path in ("/", "/index.html"):
            self._html(PAGE.read_bytes())
        else:
            self.send_error(404)

    def log_message(self, *_args) -> None:
        """0.4초마다 한 줄씩 찍히면 터미널을 볼 수 없다."""
        return None

    # -- 내부 ---------------------------------------------------------------

    def _json(self, payload: dict) -> None:
        self._respond(
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _html(self, body: bytes) -> None:
        self._respond(body, "text/html; charset=utf-8")

    def _respond(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # 상태는 매번 새로 읽어야 한다.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def build_server(presence_path: Path, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    handler = partial(_handler_for, presence_path)
    return ThreadingHTTPServer((HOST, port), handler)


def _handler_for(presence_path: Path, *args, **kwargs):
    class Bound(OrbHandler):
        pass

    Bound.presence_path = presence_path
    return Bound(*args, **kwargs)


def open_later(url: str, delay: float = 0.4) -> None:
    """서버가 뜬 뒤에 브라우저를 연다. 먼저 열면 연결 거부 화면이 뜬다."""

    def go() -> None:
        try:
            webbrowser.open(url)
        except Exception as exc:  # pragma: no cover - 환경마다 다르다
            logger.debug("브라우저를 열지 못했습니다: %s", exc)

    threading.Timer(delay, go).start()
