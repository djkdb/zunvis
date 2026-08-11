"""로컬 git 저장소에서 사실을 읽는다.

GitPython 같은 의존성을 넣지 않고 `git` 명령을 그대로 쓴다. macOS에는
Xcode CLT와 함께 이미 있고, 우리가 필요한 건 읽기 세 가지뿐이다.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from pathlib import Path

from junvis.features.project_brain.application.ports import GitReading
from junvis.features.project_brain.domain.model import CommitRef

logger = logging.getLogger(__name__)

#: 커밋 한 줄을 파싱하기 위한 구분자. 커밋 메시지에 나올 수 없는 문자를 쓴다.
_SEP = "\x1f"
_FORMAT = _SEP.join(["%H", "%s", "%aI", "%an"])

_TIMEOUT_SECONDS = 10


class GitAdapter:
    def read(self, path: Path, *, commit_limit: int = 10) -> GitReading | None:
        if not (path / ".git").exists():
            return None
        return GitReading(
            branch=self._branch(path),
            dirty=self._dirty(path),
            commits=self._commits(path, commit_limit),
            remote_url=self._remote(path),
        )

    # -- 개별 조회 ----------------------------------------------------------

    def _branch(self, path: Path) -> str | None:
        return self._run(path, "rev-parse", "--abbrev-ref", "HEAD")

    def _dirty(self, path: Path) -> bool:
        status = self._run(path, "status", "--porcelain")
        return bool(status)

    def _remote(self, path: Path) -> str | None:
        return self._run(path, "remote", "get-url", "origin")

    def _commits(self, path: Path, limit: int) -> tuple[CommitRef, ...]:
        output = self._run(path, "log", f"-{limit}", f"--pretty=format:{_FORMAT}")
        if not output:
            return ()
        commits: list[CommitRef] = []
        for line in output.splitlines():
            parts = line.split(_SEP)
            if len(parts) != 4:
                continue
            sha, subject, authored, author = parts
            try:
                authored_at = datetime.fromisoformat(authored)
            except ValueError:
                continue
            commits.append(
                CommitRef(sha=sha, subject=subject, authored_at=authored_at, author=author)
            )
        return tuple(commits)

    def _run(self, path: Path, *args: str) -> str | None:
        """git 호출은 실패해도 예외를 밖으로 내보내지 않는다.

        새로 만든 저장소(커밋 0개)나 detached HEAD 같은 정상적인 상황에서도
        git은 0이 아닌 코드를 낸다. 스냅샷 수집이 그것 때문에 멈추면 안 된다.
        """
        try:
            result = subprocess.run(
                ["git", "-C", str(path), *args],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("git %s 실패(%s): %s", args, path, exc)
            return None
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None
