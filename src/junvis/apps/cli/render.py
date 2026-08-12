"""CLI 출력 형식.

여러 명령이 같은 요약을 찍는다. 형식이 흩어지면 같은 것이 화면마다
달라 보인다.
"""

from __future__ import annotations

from junvis.features.creator.application.dto import ContentSummary
from junvis.features.memory.application.dto import MemoryView
from junvis.features.project_brain.application.dto import ProjectSummary

STATUS_LABEL = {
    "suggested": "제안",
    "drafted": "초안",
    "published": "발행됨",
    "dismissed": "버림",
}


def print_project(summary: ProjectSummary) -> None:
    print(f"{summary.slug} — {summary.name}")
    if summary.purpose:
        print(f"  목적   : {summary.purpose}")
    if summary.repo_full_name:
        print(f"  저장소 : {summary.repo_full_name}")
    if summary.tech_stack:
        print(f"  스택   : {', '.join(summary.tech_stack)}")
    if summary.branch:
        print(f"  브랜치 : {summary.branch}{' (변경 있음)' if summary.dirty else ''}")
    if summary.last_commit:
        print(f"  최근   : {summary.last_commit}")
    if summary.open_todo_count:
        print(f"  TODO   : {summary.open_todo_count}건")


def print_content(summary: ContentSummary) -> None:
    label = STATUS_LABEL.get(summary.status, summary.status)
    print(f"[{label}] {summary.subject}  ({summary.id[:8]})")
    if summary.hook:
        print(f"  Hook   : {summary.hook}")
    if summary.scene_count:
        print(f"  장면   : {summary.scene_count}개 · {summary.duration_seconds}초")
    if summary.source_project_slug:
        print(f"  프로젝트: {summary.source_project_slug}")
    if summary.published_url:
        print(f"  발행   : {summary.published_url}")


def print_memory(view: MemoryView) -> None:
    marks = []
    if view.pinned:
        marks.append("고정")
    if view.scope != "user":
        marks.append(view.scope)
    if view.subject:
        marks.append(view.subject)
    suffix = f"  [{', '.join(marks)}]" if marks else ""
    print(f"- {view.text}{suffix}  ({view.short_id})")
