"""project_brain의 값 객체.

표준 라이브러리만 임포트한다. 이 계층은 SQLite도 git도 MCP도 모른다.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Iterable

from junvis.features.project_brain.domain.errors import InvalidSlug

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_NON_SLUG = re.compile(r"[^a-z0-9._-]+")

_SSH_REMOTE = re.compile(r"^(?:ssh://)?(?:git@)?(?P<host>[^/:]+)[:/](?P<path>.+?)(?:\.git)?/?$")
_HTTP_REMOTE = re.compile(r"^https?://(?:[^@/]+@)?(?P<host>[^/]+)/(?P<path>.+?)(?:\.git)?/?$")


@dataclass(frozen=True, order=True)
class ProjectId:
    value: str

    @staticmethod
    def new() -> ProjectId:
        return ProjectId(uuid.uuid4().hex)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class Slug:
    """사람이 부르는 프로젝트 식별자. 유일하다."""

    value: str

    def __post_init__(self) -> None:
        if not _SLUG_RE.match(self.value):
            raise InvalidSlug(
                f"쓸 수 없는 slug입니다: {self.value!r} "
                "(소문자·숫자로 시작하고 . _ - 만 쓸 수 있으며 64자 이하)"
            )

    @staticmethod
    def from_text(text: str) -> Slug:
        normalized = _NON_SLUG.sub("-", text.strip().lower()).strip("-._")
        if not normalized:
            raise InvalidSlug(f"slug를 만들 수 없습니다: {text!r}")
        return Slug(normalized[:64])

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class RepoRef:
    host: str
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def url(self) -> str:
        return f"https://{self.host}/{self.full_name}"

    @staticmethod
    def parse(remote_url: str | None) -> RepoRef | None:
        """git remote URL을 해석한다. 해석 불가면 None (예외를 던지지 않는다).

        원격이 없는 로컬 전용 프로젝트도 1급 시민이기 때문이다.
        """
        if not remote_url:
            return None
        candidate = remote_url.strip()
        for pattern in (_HTTP_REMOTE, _SSH_REMOTE):
            match = pattern.match(candidate)
            if not match:
                continue
            path = match.group("path").strip("/")
            parts = [p for p in path.split("/") if p]
            if len(parts) < 2:
                continue
            return RepoRef(host=match.group("host"), owner=parts[-2], name=parts[-1])
        return None


@dataclass(frozen=True)
class TechStack:
    items: tuple[str, ...] = ()

    @staticmethod
    def empty() -> TechStack:
        return TechStack(())

    @staticmethod
    def of(values: Iterable[str]) -> TechStack:
        """대소문자를 무시하고 중복을 제거하되 처음 본 표기를 유지한다.

        "Python"과 "python"이 둘 다 남으면 컨텍스트 예산만 축낸다.
        정렬 키를 소문자로 고정해 순서가 결정적이 되게 한다.
        """
        seen: dict[str, str] = {}
        for value in values:
            if not value or not value.strip():
                continue
            cleaned = value.strip()
            seen.setdefault(cleaned.lower(), cleaned)
        return TechStack(tuple(seen[key] for key in sorted(seen)))

    def merged(self, other: TechStack) -> TechStack:
        return TechStack.of([*self.items, *other.items])

    def __iter__(self):
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __bool__(self) -> bool:
        return bool(self.items)

    def __str__(self) -> str:
        return ", ".join(self.items)


@dataclass(frozen=True)
class TokenBudget:
    """Context Pack의 크기 상한.

    토큰 추정은 문자수/4의 거친 근사다. 정확한 토크나이저를 도메인에
    끌어들이면 계층이 오염되므로, 여기서는 예산 개념만 다룬다.
    """

    tokens: int = 2000
    CHARS_PER_TOKEN: int = 4

    def __post_init__(self) -> None:
        if self.tokens <= 0:
            raise ValueError("토큰 예산은 1 이상이어야 합니다")

    @property
    def chars(self) -> int:
        return self.tokens * self.CHARS_PER_TOKEN
