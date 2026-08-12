"""git 저장소 찾기 — 첫 걸음을 가볍게 만드는 일."""

from __future__ import annotations

from pathlib import Path

from junvis.features.project_brain.infrastructure.discovery import (
    find_git_repositories,
)


def repo(root: Path, *parts: str) -> Path:
    path = root.joinpath(*parts)
    (path / ".git").mkdir(parents=True)
    return path


def test_finds_repositories(tmp_path: Path) -> None:
    first = repo(tmp_path, "dev", "zunvis")
    second = repo(tmp_path, "dev", "reels-editor")

    assert find_git_repositories(tmp_path) == sorted([first, second])


def test_a_directory_without_git_is_not_a_project(tmp_path: Path) -> None:
    (tmp_path / "dev" / "그냥폴더").mkdir(parents=True)

    assert find_git_repositories(tmp_path) == []


def test_nested_repositories_are_left_alone(tmp_path: Path) -> None:
    """서브모듈까지 등록하면 목록이 남의 코드로 뒤덮인다."""
    outer = repo(tmp_path, "dev", "zunvis")
    (outer / "vendor-lib" / ".git").mkdir(parents=True)

    assert find_git_repositories(tmp_path) == [outer]


def test_heavy_directories_are_skipped(tmp_path: Path) -> None:
    """node_modules 안을 뒤지면 거기서 시간을 다 쓴다."""
    (tmp_path / "app" / "node_modules" / "pkg" / ".git").mkdir(parents=True)
    real = repo(tmp_path, "app2")

    assert find_git_repositories(tmp_path) == [real]


def test_depth_is_bounded(tmp_path: Path) -> None:
    deep = repo(tmp_path, "a", "b", "c", "d", "e")

    assert find_git_repositories(tmp_path, depth=2) == []
    assert find_git_repositories(tmp_path, depth=6) == [deep]


def test_a_missing_root_is_not_an_error(tmp_path: Path) -> None:
    assert find_git_repositories(tmp_path / "없는곳") == []


def test_symlinks_are_not_followed(tmp_path: Path) -> None:
    """순환을 만든다. 한 번 걸리면 영영 안 끝난다."""
    real = repo(tmp_path, "dev", "zunvis")
    (tmp_path / "shortcut").symlink_to(tmp_path / "dev")

    assert find_git_repositories(tmp_path) == [real]
