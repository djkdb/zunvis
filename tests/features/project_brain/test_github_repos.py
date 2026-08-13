"""GitHub 프로필 저장소 목록.

진짜 GitHub을 부르지 않는다. 로컬에 가짜 API를 띄우고 계약만 본다 —
어떤 경로를 부르는지, 페이지를 어떻게 잇는지, 실패를 어떻게 설명하는지.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from junvis.features.project_brain.infrastructure.github_repos import (
    PER_PAGE,
    GitHubRepositoryLister,
    GitHubUnavailable,
)


def repo(name: str, **overrides) -> dict:
    payload = {
        "name": name,
        "full_name": f"djkdb/{name}",
        "description": f"{name} 설명",
        "clone_url": f"https://github.com/djkdb/{name}.git",
        "language": "Python",
        "private": False,
        "fork": False,
        "archived": False,
        "pushed_at": "2026-08-13T03:00:00Z",
    }
    payload.update(overrides)
    return payload


class FakeGitHub:
    def __init__(self) -> None:
        self.pages: dict[int, list[dict]] = {}
        self.status = 200
        self.requests: list[tuple[str, dict]] = []
        self.auth: list[str | None] = []


@pytest.fixture()
def github() -> Iterator[tuple[str, FakeGitHub]]:
    state = FakeGitHub()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            state.requests.append((parsed.path, query))
            state.auth.append(self.headers.get("Authorization"))

            if state.status != 200:
                self.send_error(state.status)
                return
            page = int(query.get("page", "1"))
            body = json.dumps(state.pages.get(page, [])).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_a_username_lists_public_repositories(github) -> None:
    root, state = github
    state.pages[1] = [repo("zunvis"), repo("reels-editor")]

    repos = GitHubRepositoryLister(token="", api_root=root).list_repositories("djkdb")

    assert [r.name for r in repos] == ["zunvis", "reels-editor"]
    path, query = state.requests[0]
    assert path == "/users/djkdb/repos"
    assert query["sort"] == "pushed"


def test_a_token_lists_my_own_repositories(github) -> None:
    """비공개까지 나온다. 그래서 누구인지 물을 필요가 없다."""
    root, state = github
    state.pages[1] = [repo("secret", private=True)]

    repos = GitHubRepositoryLister(token="t0ken", api_root=root).list_repositories()

    assert repos[0].private
    assert state.requests[0][0] == "/user/repos"
    # 조직에 초대만 된 저장소까지 딸려 오면 목록이 남의 것으로 뒤덮인다.
    assert state.requests[0][1]["affiliation"] == "owner"
    assert state.auth[0] == "Bearer t0ken"


def test_pages_are_followed(github) -> None:
    root, state = github
    state.pages[1] = [repo(f"p{index}") for index in range(PER_PAGE)]
    state.pages[2] = [repo("마지막")]

    repos = GitHubRepositoryLister(token="t", api_root=root).list_repositories()

    assert len(repos) == PER_PAGE + 1
    assert repos[-1].name == "마지막"


def test_a_short_page_stops_the_walk(github) -> None:
    root, state = github
    state.pages[1] = [repo("하나")]

    GitHubRepositoryLister(token="t", api_root=root).list_repositories()

    assert len(state.requests) == 1


def test_without_a_name_or_token_it_says_what_to_do() -> None:
    """누구인지 알 방법이 없다. 조용히 빈 목록을 주면 안 된다."""
    with pytest.raises(GitHubUnavailable, match="gh auth login"):
        GitHubRepositoryLister(token="").list_repositories()


def test_an_unknown_user_is_explained(github) -> None:
    root, state = github
    state.status = 404

    with pytest.raises(GitHubUnavailable, match="사용자가 없습니다"):
        GitHubRepositoryLister(token="", api_root=root).list_repositories("없는사람")


def test_a_rate_limit_points_at_logging_in(github) -> None:
    root, state = github
    state.status = 403

    with pytest.raises(GitHubUnavailable, match="gh auth login"):
        GitHubRepositoryLister(token="", api_root=root).list_repositories("djkdb")


def test_a_rejected_token_is_explained(github) -> None:
    root, state = github
    state.status = 401

    with pytest.raises(GitHubUnavailable, match="거부"):
        GitHubRepositoryLister(token="bad-token", api_root=root).list_repositories()


def test_forks_and_archives_are_flagged_not_dropped(github) -> None:
    """무엇을 뺄지는 어댑터가 정하지 않는다. 부르는 쪽이 정한다."""
    root, state = github
    state.pages[1] = [repo("포크", fork=True), repo("보관", archived=True)]

    repos = GitHubRepositoryLister(token="t", api_root=root).list_repositories()

    assert [r.fork for r in repos] == [True, False]
    assert [r.archived for r in repos] == [False, True]


def test_missing_fields_do_not_crash(github) -> None:
    """설명이 없는 저장소는 흔하다. null이 그대로 온다."""
    root, state = github
    state.pages[1] = [{"name": "민숭민숭", "description": None, "language": None}]

    [only] = GitHubRepositoryLister(token="t", api_root=root).list_repositories()

    assert only.name == "민숭민숭"
    assert only.description == ""
    assert only.pushed_at is None
