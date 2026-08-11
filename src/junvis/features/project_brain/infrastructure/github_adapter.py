"""GitHub 이슈 조회 (M11).

의존성을 늘리지 않으려고 urllib만 쓴다. 토큰은 환경변수에서 읽되,
없어도 공개 저장소는 읽을 수 있어야 한다. 어떤 실패도 스냅샷 수집
전체를 무너뜨리지 않는다 — 오프라인이 정상 상태 중 하나이기 때문이다.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

from junvis.features.project_brain.domain.model import IssueRef
from junvis.features.project_brain.domain.value_objects import RepoRef

logger = logging.getLogger(__name__)

API_ROOT = "https://api.github.com"
TIMEOUT_SECONDS = 8
TOKEN_ENV_VARS = ("JUNVIS_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")


class GitHubIssueAdapter:
    def __init__(self, token: str | None = None, api_root: str = API_ROOT) -> None:
        self._token = token or self._token_from_env()
        self._api_root = api_root.rstrip("/")

    @staticmethod
    def _token_from_env() -> str | None:
        for name in TOKEN_ENV_VARS:
            value = os.environ.get(name)
            if value:
                return value
        return None

    def open_issues(self, repo: RepoRef, *, limit: int = 10) -> tuple[IssueRef, ...]:
        if "github.com" not in repo.host:
            return ()
        url = (
            f"{self._api_root}/repos/{repo.owner}/{repo.name}/issues"
            f"?state=open&per_page={max(1, min(limit, 100))}"
        )
        payload = self._get(url)
        if payload is None:
            return ()

        issues: list[IssueRef] = []
        for item in payload:
            # GitHub은 PR도 이슈로 돌려준다. 우리가 원하는 건 이슈뿐이다.
            if "pull_request" in item:
                continue
            issues.append(
                IssueRef(
                    number=int(item.get("number", 0)),
                    title=str(item.get("title", "")).strip(),
                    state=str(item.get("state", "open")),
                    url=str(item.get("html_url", "")),
                )
            )
            if len(issues) >= limit:
                break
        return tuple(issues)

    def _get(self, url: str) -> list[dict] | None:
        request = urllib.request.Request(url, method="GET")
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("User-Agent", "junvis")
        if self._token:
            request.add_header("Authorization", f"Bearer {self._token}")
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            logger.debug("GitHub 이슈 조회 실패(%s): %s", url, exc)
            return None
        return data if isinstance(data, list) else None
