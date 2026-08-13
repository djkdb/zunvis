"""GitHub 프로필의 저장소 목록을 가져온다.

디스크를 훑는 것(`discovery.py`)과 다른 일이다. 맥에 클론하지 않은 프로젝트,
다른 컴퓨터에서 만든 프로젝트, 예전에 지운 프로젝트가 전부 프로필에는 남아
있다. JUNVIS가 그것을 알아야 "그때 그거 어떻게 됐지"에 답할 수 있다.

의존성을 늘리지 않으려고 urllib만 쓴다.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

from junvis.core.domain.errors import JunvisError
from junvis.features.project_brain.infrastructure.github_auth import resolve_token

logger = logging.getLogger(__name__)

API_ROOT = "https://api.github.com"
#: GitHub Enterprise를 쓰거나 사내 프록시를 거칠 때 바꾼다.
API_ROOT_ENV = "JUNVIS_GITHUB_API"
TIMEOUT_SECONDS = 15
PER_PAGE = 100
#: 한 프로필에 이보다 많으면 손으로 고르는 편이 낫다.
MAX_PAGES = 10


class GitHubUnavailable(JunvisError):
    """목록을 가져오지 못했다. 무엇을 하면 되는지 메시지에 담는다."""


@dataclass(frozen=True)
class RemoteRepo:
    name: str
    full_name: str
    description: str
    clone_url: str
    language: str
    private: bool
    fork: bool
    archived: bool
    pushed_at: datetime | None

    @property
    def owner(self) -> str:
        return self.full_name.split("/")[0] if "/" in self.full_name else ""


class GitHubRepositoryLister:
    def __init__(self, token: str | None = None, api_root: str | None = None) -> None:
        self._token = resolve_token(token)
        root = api_root or os.environ.get(API_ROOT_ENV) or API_ROOT
        self._api_root = root.rstrip("/")

    @property
    def authenticated(self) -> bool:
        return bool(self._token)

    def list_repositories(self, user: str | None = None) -> list[RemoteRepo]:
        """`user`를 주면 그 사람의 공개 저장소, 없으면 내 저장소 전부.

        토큰이 있으면 비공개까지 나온다. 없으면 사용자 이름이 있어야 한다 —
        누구인지 알 방법이 없기 때문이다.
        """
        if not user and not self._token:
            raise GitHubUnavailable(
                "GitHub 사용자 이름이나 토큰이 필요합니다.\n"
                "  junvis scan --github <사용자이름>   공개 저장소만\n"
                "  gh auth login                       비공개까지 (권장)\n"
                "  또는 export GITHUB_TOKEN=..."
            )

        repos: list[RemoteRepo] = []
        for page in range(1, MAX_PAGES + 1):
            batch = self._page(user, page)
            repos.extend(batch)
            if len(batch) < PER_PAGE:
                break
        return repos

    # -- 내부 ---------------------------------------------------------------

    def _page(self, user: str | None, page: int) -> list[RemoteRepo]:
        query = urllib.parse.urlencode(
            {"per_page": PER_PAGE, "page": page, "sort": "pushed"}
            # `affiliation=owner`가 없으면 조직에 초대만 된 저장소까지 딸려 온다.
            | ({"affiliation": "owner"} if not user else {})
        )
        path = f"/users/{urllib.parse.quote(user)}/repos" if user else "/user/repos"
        payload = self._get(f"{self._api_root}{path}?{query}")
        return [_to_repo(item) for item in payload if isinstance(item, dict)]

    def _get(self, url: str) -> list:
        request = urllib.request.Request(url, method="GET")
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("User-Agent", "junvis")
        if self._token:
            request.add_header("Authorization", f"Bearer {self._token}")

        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise GitHubUnavailable(_explain(exc)) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GitHubUnavailable(f"GitHub에 연결하지 못했습니다: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise GitHubUnavailable("GitHub가 이상한 응답을 보냈습니다.") from exc

        if not isinstance(data, list):
            raise GitHubUnavailable("GitHub가 목록이 아닌 것을 보냈습니다.")
        return data


def _explain(error: urllib.error.HTTPError) -> str:
    """상태 코드를 사람이 할 수 있는 일로 바꾼다."""
    if error.code == 404:
        return "그런 사용자가 없습니다. 이름을 확인해 주세요."
    if error.code == 401:
        return "GitHub 토큰이 거부됐습니다. `gh auth login` 을 다시 해 보세요."
    if error.code == 403:
        return (
            "GitHub가 요청을 거부했습니다 (요청 한도일 수 있습니다).\n"
            "  `gh auth login` 으로 로그인하면 한도가 크게 늘어납니다."
        )
    return f"GitHub 오류 {error.code}: {error.reason}"


def _to_repo(item: dict) -> RemoteRepo:
    return RemoteRepo(
        name=str(item.get("name", "")),
        full_name=str(item.get("full_name", "")),
        description=str(item.get("description") or "").strip(),
        clone_url=str(item.get("clone_url") or item.get("html_url") or ""),
        language=str(item.get("language") or ""),
        private=bool(item.get("private")),
        fork=bool(item.get("fork")),
        archived=bool(item.get("archived")),
        pushed_at=_moment(item.get("pushed_at")),
    )


def _moment(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def sort_key(repo: RemoteRepo) -> tuple:
    """최근에 손댄 것이 먼저. 사람이 기대하는 순서다."""
    return (repo.pushed_at or datetime.min.replace(tzinfo=timezone.utc),)
