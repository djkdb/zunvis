"""project_brain의 애그리게이트.

`Project`가 애그리게이트 루트다. 스냅샷·TODO·메모는 Project를 통해서만
바뀐다. 저장소(Repository)도 Project 단위로만 오간다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from junvis.core.domain.event import DomainEvent, utcnow
from junvis.features.project_brain.domain.context_pack import ContextPack, build_pack
from junvis.features.project_brain.domain.events import (
    ProjectNoteAdded,
    ProjectRegistered,
    ProjectSnapshotRefreshed,
)
from junvis.features.project_brain.domain.value_objects import (
    ProjectId,
    RepoRef,
    Slug,
    TechStack,
    TokenBudget,
)

#: 스냅샷 스캔이 만들어낸 TODO의 출처. 재수집 때 통째로 교체된다.
SOURCE_SCAN = "scan"
#: 사용자가 직접 추가한 TODO. 재수집이 건드리지 않는다.
SOURCE_USER = "user"


@dataclass(frozen=True)
class CommitRef:
    sha: str
    subject: str
    authored_at: datetime
    author: str = ""

    @property
    def short_sha(self) -> str:
        return self.sha[:7]

    def summary(self) -> str:
        return f"{self.short_sha} {self.subject}"


@dataclass(frozen=True)
class IssueRef:
    number: int
    title: str
    state: str = "open"
    url: str = ""

    def summary(self) -> str:
        return f"#{self.number} {self.title}"


@dataclass(frozen=True)
class TodoItem:
    id: str
    text: str
    source: str = SOURCE_USER
    done: bool = False

    @staticmethod
    def create(text: str, source: str = SOURCE_USER) -> TodoItem:
        return TodoItem(id=uuid.uuid4().hex, text=text.strip(), source=source)


@dataclass(frozen=True)
class Note:
    id: str
    text: str
    created_at: datetime


@dataclass(frozen=True)
class ProjectSnapshot:
    """특정 시점의 프로젝트 상태. 불변이며 통째로 교체된다."""

    captured_at: datetime = field(default_factory=utcnow)
    branch: str | None = None
    dirty: bool = False
    readme_excerpt: str = ""
    recent_commits: tuple[CommitRef, ...] = ()
    open_issues: tuple[IssueRef, ...] = ()
    detected_stack: TechStack = field(default_factory=TechStack.empty)
    discovered_todos: tuple[str, ...] = ()


@dataclass
class Project:
    """애그리게이트 루트."""

    id: ProjectId
    slug: Slug
    name: str
    local_path: Path | None = None
    repo: RepoRef | None = None
    purpose: str = ""
    architecture_note: str = ""
    tech_stack: TechStack = field(default_factory=TechStack.empty)
    snapshot: ProjectSnapshot | None = None
    todos: list[TodoItem] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    _events: list[DomainEvent] = field(default_factory=list, repr=False, compare=False)

    # -- 생성 ---------------------------------------------------------------

    @classmethod
    def register(
        cls,
        *,
        slug: Slug,
        name: str,
        local_path: Path | None = None,
        repo: RepoRef | None = None,
        purpose: str = "",
        architecture_note: str = "",
        tech_stack: TechStack | None = None,
        now: datetime | None = None,
        project_id: ProjectId | None = None,
    ) -> Project:
        moment = now or utcnow()
        project = cls(
            id=project_id or ProjectId.new(),
            slug=slug,
            name=name.strip() or slug.value,
            local_path=local_path,
            repo=repo,
            purpose=purpose.strip(),
            architecture_note=architecture_note.strip(),
            tech_stack=tech_stack or TechStack.empty(),
            created_at=moment,
            updated_at=moment,
        )
        project._record(
            ProjectRegistered(
                project_id=project.id.value,
                slug=project.slug.value,
                name=project.name,
                repo_full_name=repo.full_name if repo else None,
            )
        )
        return project

    # -- 행위 ---------------------------------------------------------------

    def describe(
        self,
        *,
        purpose: str | None = None,
        architecture_note: str | None = None,
        now: datetime | None = None,
    ) -> None:
        if purpose is not None:
            self.purpose = purpose.strip()
        if architecture_note is not None:
            self.architecture_note = architecture_note.strip()
        self.updated_at = now or utcnow()

    def refresh(self, snapshot: ProjectSnapshot, *, now: datetime | None = None) -> None:
        """스냅샷을 교체한다.

        감지된 스택은 **누적 병합**한다. 한 번 파악한 사실을 재수집 실패로
        잃지 않기 위해서다. 반면 스캔이 만든 TODO는 통째로 교체한다 —
        코드에서 사라진 TODO가 계속 남아 있으면 안 되기 때문이다.
        """
        self.snapshot = snapshot
        self.tech_stack = self.tech_stack.merged(snapshot.detected_stack)
        self.todos = [
            *(todo for todo in self.todos if todo.source != SOURCE_SCAN),
            *(TodoItem.create(text, SOURCE_SCAN) for text in snapshot.discovered_todos),
        ]
        self.updated_at = now or utcnow()
        self._record(
            ProjectSnapshotRefreshed(
                project_id=self.id.value,
                slug=self.slug.value,
                branch=snapshot.branch,
                commit_count=len(snapshot.recent_commits),
                todo_count=len(snapshot.discovered_todos),
            )
        )

    def remember(self, text: str, *, now: datetime | None = None) -> Note:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("빈 메모는 기억할 수 없습니다")
        moment = now or utcnow()
        note = Note(id=uuid.uuid4().hex, text=cleaned, created_at=moment)
        self.notes.append(note)
        self.updated_at = moment
        self._record(
            ProjectNoteAdded(
                project_id=self.id.value,
                slug=self.slug.value,
                note_id=note.id,
                text=cleaned,
            )
        )
        return note

    def add_todo(self, text: str, *, now: datetime | None = None) -> TodoItem:
        todo = TodoItem.create(text, SOURCE_USER)
        self.todos.append(todo)
        self.updated_at = now or utcnow()
        return todo

    def complete_todo(self, todo_id: str, *, now: datetime | None = None) -> bool:
        for index, todo in enumerate(self.todos):
            if todo.id == todo_id:
                self.todos[index] = TodoItem(todo.id, todo.text, todo.source, done=True)
                self.updated_at = now or utcnow()
                return True
        return False

    # -- 컨텍스트 조립 (이 Context의 심장) -----------------------------------

    def context_pack(self, budget: TokenBudget | None = None) -> ContextPack:
        """에이전트 주입용 컨텍스트를 우선순위대로 조립한다.

        순서: 목적 → 스택 → 아키텍처 → 최근 커밋 → TODO → 이슈 → 메모 → README
        """
        limit = budget or TokenBudget()
        return build_pack(
            slug=self.slug.value,
            name=self.name,
            generated_at=utcnow(),
            candidates=self._context_candidates(),
            budget=limit,
        )

    def _context_candidates(self) -> list[tuple[str, str]]:
        snapshot = self.snapshot
        sections: list[tuple[str, str]] = [
            ("목적", self.purpose),
            ("기술 스택", str(self.tech_stack)),
            ("아키텍처", self.architecture_note),
        ]

        if snapshot:
            head = f"현재 브랜치: {snapshot.branch or '알 수 없음'}"
            if snapshot.dirty:
                head += " (커밋되지 않은 변경 있음)"
            sections.append(("작업 상태", head))
            sections.append(
                ("최근 커밋", "\n".join(f"- {c.summary()}" for c in snapshot.recent_commits))
            )

        sections.append(
            ("TODO", "\n".join(f"- {t.text}" for t in self.todos if not t.done))
        )

        if snapshot:
            sections.append(
                ("열린 이슈", "\n".join(f"- {i.summary()}" for i in snapshot.open_issues))
            )

        sections.append(
            (
                "기억해둔 메모",
                "\n".join(f"- {n.text}" for n in sorted(
                    self.notes, key=lambda n: n.created_at, reverse=True
                )),
            )
        )

        if snapshot:
            sections.append(("README", snapshot.readme_excerpt))

        return sections

    # -- 이벤트 ------------------------------------------------------------

    def _record(self, event: DomainEvent) -> None:
        self._events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        """수집된 이벤트를 넘기고 비운다. 유스케이스가 저장 직후 호출한다."""
        events, self._events = list(self._events), []
        return events
