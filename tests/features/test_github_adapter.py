"""M11: GitHub 이슈 어댑터.

네트워크를 타지 않는다. 검증 대상은 HTTP가 아니라 **응답 해석 규칙**이다:
GitHub은 PR도 이슈로 돌려주므로 걸러내야 한다.
"""

from __future__ import annotations

from junvis.features.project_brain.domain.value_objects import RepoRef
from junvis.features.project_brain.infrastructure.github_adapter import GitHubIssueAdapter

REPO = RepoRef("github.com", "djkdb", "zunvis")


class StubAdapter(GitHubIssueAdapter):
    def __init__(self, payload) -> None:
        super().__init__(token="x")
        self.payload = payload
        self.requested: list[str] = []

    def _get(self, url: str):
        self.requested.append(url)
        return self.payload


def test_pull_requests_are_filtered_out() -> None:
    adapter = StubAdapter(
        [
            {"number": 1, "title": "진짜 이슈", "state": "open", "html_url": "u1"},
            {"number": 2, "title": "PR입니다", "pull_request": {"url": "x"}},
            {"number": 3, "title": "또 다른 이슈", "state": "open", "html_url": "u3"},
        ]
    )

    issues = adapter.open_issues(REPO)

    assert [i.number for i in issues] == [1, 3]
    assert issues[0].title == "진짜 이슈"


def test_limit_is_respected_after_filtering() -> None:
    payload = [{"number": n, "title": f"이슈 {n}", "html_url": ""} for n in range(1, 11)]
    assert len(StubAdapter(payload).open_issues(REPO, limit=3)) == 3


def test_network_failure_returns_empty_not_exception() -> None:
    """오프라인은 예외 상황이 아니라 정상 모드 중 하나다."""

    class Offline(GitHubIssueAdapter):
        def _get(self, url: str):
            return None

    assert Offline().open_issues(REPO) == ()


def test_non_github_host_is_skipped() -> None:
    adapter = StubAdapter([{"number": 1, "title": "x", "html_url": ""}])
    assert adapter.open_issues(RepoRef("gitlab.com", "a", "b")) == ()
    assert adapter.requested == []  # 요청조차 보내지 않는다


def test_request_url_and_limit_clamping() -> None:
    adapter = StubAdapter([])
    adapter.open_issues(REPO, limit=500)
    assert "repos/djkdb/zunvis/issues" in adapter.requested[0]
    assert "per_page=100" in adapter.requested[0]  # 상한으로 잘린다


def test_malformed_entries_do_not_crash() -> None:
    issues = StubAdapter([{}, {"number": "7", "title": None}]).open_issues(REPO)
    assert len(issues) == 2
    assert issues[0].number == 0
