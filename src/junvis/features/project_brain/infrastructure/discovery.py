"""디스크에서 git 저장소를 찾는다.

프로젝트를 하나씩 손으로 등록하는 것은 시작하는 데 드는 비용이다.
JUNVIS가 아무것도 모르는 상태에서는 브리핑도 릴스 제안도 빈손이므로,
첫 걸음을 가볍게 만드는 것이 실제로 기능을 살린다.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger(__name__)

#: 이 안쪽은 보지 않는다. 남의 코드가 대부분이고, 여기서 시간을 다 쓴다.
SKIP = frozenset(
    {
        "node_modules", ".venv", "venv", "env", "vendor", "target",
        "build", "dist", ".next", ".nuxt", "__pycache__", ".tox",
        "Library", "Applications", ".Trash", ".cache", ".cargo",
        "Pods", "DerivedData", ".gradle", "site-packages",
    }
)

DEFAULT_DEPTH = 3


def find_git_repositories(
    root: Path, *, depth: int = DEFAULT_DEPTH
) -> list[Path]:
    """`root` 아래의 git 저장소를 찾는다. 결과는 경로 순으로 안정적이다.

    **중첩 저장소는 바깥 것만 잡는다.** 서브모듈이나 vendored 저장소까지
    전부 등록하면 목록이 남의 코드로 뒤덮인다.
    """
    root = root.expanduser().resolve()
    if not root.is_dir():
        return []
    return sorted(_walk(root, depth))


def _walk(directory: Path, depth: int) -> Iterator[Path]:
    if (directory / ".git").exists():
        yield directory
        return  # 안쪽은 더 보지 않는다. 서브모듈은 이 프로젝트의 일부다.
    if depth <= 0:
        return

    for child in _children(directory):
        yield from _walk(child, depth - 1)


def _children(directory: Path) -> list[Path]:
    try:
        entries = list(directory.iterdir())
    except (PermissionError, OSError) as exc:
        # 권한 없는 폴더 하나 때문에 전체 탐색이 죽으면 안 된다.
        logger.debug("건너뜁니다 %s: %s", directory, exc)
        return []

    return [
        entry
        for entry in entries
        if entry.is_dir()
        and not entry.is_symlink()  # 순환을 만든다
        and entry.name not in SKIP
        and not entry.name.startswith(".")
    ]
