"""GitHub 토큰을 한 곳에서 찾는다.

이슈 조회와 저장소 목록이 서로 다른 방법으로 토큰을 찾으면, 한쪽은 되고
한쪽은 안 되는 상태가 생긴다. 사용자에게는 설명할 수 없는 일이다.

`gh` CLI를 마지막에 물어보는 이유: 개발자 대부분은 `gh auth login`을 해
두었고 그 토큰은 환경변수가 아니라 키체인에 있다. 환경변수만 보면 "이미
로그인했는데 왜 안 되지"가 된다.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

TOKEN_ENV_VARS = ("JUNVIS_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")

#: `gh`가 키체인을 여는 데 걸리는 시간. 넘으면 없는 것으로 본다.
GH_TIMEOUT_SECONDS = 5


def resolve_token(explicit: str | None = None) -> str | None:
    """명시값 → 환경변수 → `gh auth token` 순으로 찾는다."""
    if explicit:
        return explicit
    for name in TOKEN_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return value
    return _token_from_gh()


def _token_from_gh() -> str | None:
    if shutil.which("gh") is None:
        return None
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.debug("gh auth token 실패: %s", exc)
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
