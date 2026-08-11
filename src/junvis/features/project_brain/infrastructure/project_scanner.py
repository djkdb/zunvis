"""파일 시스템에서 README·기술스택·TODO를 읽어낸다.

깊이를 제한한다. 개인 기기에서 프로젝트 트리를 통째로 걷는 것은
ScreenPipe가 상시 녹화로 디스크를 태우는 것과 같은 종류의 실수다.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from junvis.features.project_brain.application.ports import ScanResult
from junvis.features.project_brain.domain.value_objects import TechStack

logger = logging.getLogger(__name__)

README_NAMES = ("README.md", "readme.md", "README.MD", "README.rst", "README.txt", "README")
TODO_NAMES = ("TODO.md", "todo.md", "TODO.txt")

MAX_README_CHARS = 1500
MAX_TODOS = 20

#: 배지·앵커만 있는 줄은 컨텍스트 예산 낭비다.
_BADGE_LINE = re.compile(r"^\s*(\[!\[|!\[|<p align|<img |<a href|<div align)")
_CHECKBOX = re.compile(r"^\s*[-*]\s*\[ \]\s*(?P<text>.+?)\s*$")
_HEADING_ANCHOR = re.compile(r"<a name=.*?</a>", re.DOTALL)

#: 마커 파일 → 기술스택 이름. 최상위와 한 단계 아래까지만 본다.
MARKERS: dict[str, str] = {
    "package.json": "Node.js",
    "tsconfig.json": "TypeScript",
    "pyproject.toml": "Python",
    "requirements.txt": "Python",
    "Pipfile": "Python",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "Package.swift": "Swift",
    "Gemfile": "Ruby",
    "pom.xml": "Java",
    "build.gradle": "Gradle",
    "build.gradle.kts": "Kotlin",
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose",
    "compose.yaml": "Docker Compose",
    "uv.lock": "uv",
    "pnpm-lock.yaml": "pnpm",
    "bun.lockb": "Bun",
    "Makefile": "Make",
}

#: 접두사로 판별하는 설정 파일들(확장자가 여러 개라 이름이 고정되지 않는다).
PREFIX_MARKERS: dict[str, str] = {
    "next.config": "Next.js",
    "vite.config": "Vite",
    "tailwind.config": "Tailwind CSS",
    "svelte.config": "Svelte",
    "nuxt.config": "Nuxt",
    "astro.config": "Astro",
}

DIR_MARKERS: dict[str, str] = {
    ".github/workflows": "GitHub Actions",
    "supabase": "Supabase",
    ".xcodeproj": "Xcode",
    "Sources": "Swift",
}

#: package.json 의존성에서 곧바로 알아볼 수 있는 것들.
NPM_PACKAGES: dict[str, str] = {
    "next": "Next.js",
    "react": "React",
    "vue": "Vue",
    "svelte": "Svelte",
    "tailwindcss": "Tailwind CSS",
    "electron": "Electron",
    "express": "Express",
    "@modelcontextprotocol/sdk": "MCP",
    "openai": "OpenAI SDK",
    "@anthropic-ai/sdk": "Anthropic SDK",
    "ollama": "Ollama",
}


class ProjectScanner:
    def scan(self, path: Path) -> ScanResult:
        return ScanResult(
            readme_excerpt=self._readme(path),
            stack=self._stack(path),
            todos=self._todos(path),
        )

    # -- README -------------------------------------------------------------

    def _readme(self, path: Path) -> str:
        for name in README_NAMES:
            candidate = path / name
            if not candidate.is_file():
                continue
            try:
                raw = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.debug("README를 읽지 못함(%s): %s", candidate, exc)
                return ""
            return self._clean_readme(raw)
        return ""

    @staticmethod
    def _clean_readme(raw: str) -> str:
        raw = _HEADING_ANCHOR.sub("", raw)
        kept = [line for line in raw.splitlines() if not _BADGE_LINE.match(line)]
        text = "\n".join(kept).strip()
        # 빈 줄이 3개 이상 이어지면 하나로 줄인다.
        text = re.sub(r"\n{3,}", "\n\n", text)
        if len(text) <= MAX_README_CHARS:
            return text
        return text[:MAX_README_CHARS].rstrip() + "\n…"

    # -- 기술 스택 ----------------------------------------------------------

    def _stack(self, path: Path) -> TechStack:
        found: set[str] = set()
        for entry in self._shallow_entries(path):
            if entry.is_file():
                if entry.name in MARKERS:
                    found.add(MARKERS[entry.name])
                for prefix, label in PREFIX_MARKERS.items():
                    if entry.name.startswith(prefix):
                        found.add(label)
            elif entry.is_dir():
                for marker, label in DIR_MARKERS.items():
                    if entry.name == marker or entry.name.endswith(marker):
                        found.add(label)

        if (path / ".github" / "workflows").is_dir():
            found.add("GitHub Actions")
        found.update(self._from_package_json(path))
        return TechStack.of(found)

    @staticmethod
    def _shallow_entries(path: Path) -> list[Path]:
        """최상위 + 한 단계 아래까지만. 그 아래는 보지 않는다."""
        entries: list[Path] = []
        try:
            top = [e for e in path.iterdir() if not e.name.startswith(".git")]
        except OSError:
            return entries
        entries.extend(top)
        for entry in top:
            if not entry.is_dir() or entry.name in {"node_modules", "venv", ".venv", "dist"}:
                continue
            try:
                entries.extend(entry.iterdir())
            except OSError:
                continue
        return entries

    @staticmethod
    def _from_package_json(path: Path) -> set[str]:
        manifest = path / "package.json"
        if not manifest.is_file():
            return set()
        try:
            data = json.loads(manifest.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            return set()
        names = {
            *data.get("dependencies", {}),
            *data.get("devDependencies", {}),
        }
        return {label for pkg, label in NPM_PACKAGES.items() if pkg in names}

    # -- TODO ---------------------------------------------------------------

    def _todos(self, path: Path) -> tuple[str, ...]:
        """TODO.md와 README의 미완료 체크박스를 모은다.

        소스 코드의 `# TODO:` 주석까지 긁으면 노이즈가 압도한다.
        의도적으로 사람이 쓴 목록만 본다.
        """
        collected: list[str] = []
        sources = [path / name for name in TODO_NAMES]
        sources.extend(path / name for name in README_NAMES)
        for candidate in sources:
            if not candidate.is_file():
                continue
            try:
                content = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in content.splitlines():
                match = _CHECKBOX.match(line)
                if match:
                    text = match.group("text").strip()
                    if text and text not in collected:
                        collected.append(text)
                if len(collected) >= MAX_TODOS:
                    return tuple(collected)
        return tuple(collected)
