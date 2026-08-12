"""ProjectRepository의 SQLite 구현 + FTS5 전문 검색."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from junvis.core.persistence.database import Database
from junvis.core.persistence.fts import fts_expression
from junvis.features.project_brain.domain.model import (
    CommitRef,
    IssueRef,
    Note,
    Project,
    ProjectSnapshot,
    TodoItem,
)
from junvis.features.project_brain.domain.repository import ProjectRepository
from junvis.features.project_brain.domain.value_objects import (
    ProjectId,
    RepoRef,
    Slug,
    TechStack,
)


class SqliteProjectRepository(ProjectRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    # -- 쓰기 ---------------------------------------------------------------

    def save(self, project: Project) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO projects
                    (id, slug, name, local_path, repo_host, repo_owner, repo_name,
                     purpose, architecture_note, tech_stack, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    slug = excluded.slug,
                    name = excluded.name,
                    local_path = excluded.local_path,
                    repo_host = excluded.repo_host,
                    repo_owner = excluded.repo_owner,
                    repo_name = excluded.repo_name,
                    purpose = excluded.purpose,
                    architecture_note = excluded.architecture_note,
                    tech_stack = excluded.tech_stack,
                    updated_at = excluded.updated_at
                """,
                (
                    project.id.value,
                    project.slug.value,
                    project.name,
                    str(project.local_path) if project.local_path else None,
                    project.repo.host if project.repo else None,
                    project.repo.owner if project.repo else None,
                    project.repo.name if project.repo else None,
                    project.purpose,
                    project.architecture_note,
                    json.dumps(list(project.tech_stack), ensure_ascii=False),
                    project.created_at.isoformat(),
                    project.updated_at.isoformat(),
                ),
            )
            self._save_snapshot(conn, project)
            self._save_todos(conn, project)
            self._save_notes(conn, project)
            self._reindex(conn, project)

    def _save_snapshot(self, conn, project: Project) -> None:
        conn.execute("DELETE FROM project_snapshots WHERE project_id = ?", (project.id.value,))
        snapshot = project.snapshot
        if snapshot is None:
            return
        conn.execute(
            """
            INSERT INTO project_snapshots
                (project_id, branch, dirty, readme_excerpt, recent_commits,
                 open_issues, detected_stack, discovered_todos, captured_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project.id.value,
                snapshot.branch,
                int(snapshot.dirty),
                snapshot.readme_excerpt,
                json.dumps(
                    [
                        {
                            "sha": c.sha,
                            "subject": c.subject,
                            "authored_at": c.authored_at.isoformat(),
                            "author": c.author,
                        }
                        for c in snapshot.recent_commits
                    ],
                    ensure_ascii=False,
                ),
                json.dumps(
                    [
                        {"number": i.number, "title": i.title, "state": i.state, "url": i.url}
                        for i in snapshot.open_issues
                    ],
                    ensure_ascii=False,
                ),
                json.dumps(list(snapshot.detected_stack), ensure_ascii=False),
                json.dumps(list(snapshot.discovered_todos), ensure_ascii=False),
                snapshot.captured_at.isoformat(),
            ),
        )

    def _save_todos(self, conn, project: Project) -> None:
        conn.execute("DELETE FROM project_todos WHERE project_id = ?", (project.id.value,))
        conn.executemany(
            """
            INSERT INTO project_todos (id, project_id, text, source, done, position)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (todo.id, project.id.value, todo.text, todo.source, int(todo.done), index)
                for index, todo in enumerate(project.todos)
            ],
        )

    def _save_notes(self, conn, project: Project) -> None:
        conn.execute("DELETE FROM project_notes WHERE project_id = ?", (project.id.value,))
        conn.executemany(
            "INSERT INTO project_notes (id, project_id, text, created_at) VALUES (?, ?, ?, ?)",
            [
                (note.id, project.id.value, note.text, note.created_at.isoformat())
                for note in project.notes
            ],
        )

    def _reindex(self, conn, project: Project) -> None:
        conn.execute("DELETE FROM project_search WHERE project_id = ?", (project.id.value,))
        conn.execute(
            """
            INSERT INTO project_search
                (slug, name, purpose, architecture_note, tech_stack, readme, notes, project_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project.slug.value,
                project.name,
                project.purpose,
                project.architecture_note,
                " ".join(project.tech_stack),
                project.snapshot.readme_excerpt if project.snapshot else "",
                " ".join(note.text for note in project.notes),
                project.id.value,
            ),
        )

    def remove(self, project_id: ProjectId) -> bool:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM project_search WHERE project_id = ?", (project_id.value,))
            cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id.value,))
        return cursor.rowcount > 0

    # -- 읽기 ---------------------------------------------------------------

    def get(self, project_id: ProjectId) -> Project | None:
        row = self._db.query_one("SELECT * FROM projects WHERE id = ?", (project_id.value,))
        return self._hydrate(row) if row else None

    def get_by_slug(self, slug: Slug) -> Project | None:
        row = self._db.query_one("SELECT * FROM projects WHERE slug = ?", (slug.value,))
        return self._hydrate(row) if row else None

    def list(self) -> list[Project]:
        rows = self._db.query("SELECT * FROM projects ORDER BY updated_at DESC")
        return [self._hydrate(row) for row in rows]

    def search(self, query: str, limit: int = 10) -> list[Project]:
        expression = fts_expression(query)
        if expression is None:
            return []
        rows = self._db.query(
            """
            SELECT p.*
            FROM project_search s
            JOIN projects p ON p.id = s.project_id
            WHERE project_search MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (expression, limit),
        )
        return [self._hydrate(row) for row in rows]


    # -- 복원 ---------------------------------------------------------------

    def _hydrate(self, row) -> Project:
        project_id = ProjectId(row["id"])
        repo = None
        if row["repo_owner"] and row["repo_name"]:
            repo = RepoRef(
                host=row["repo_host"] or "github.com",
                owner=row["repo_owner"],
                name=row["repo_name"],
            )
        return Project(
            id=project_id,
            slug=Slug(row["slug"]),
            name=row["name"],
            local_path=Path(row["local_path"]) if row["local_path"] else None,
            repo=repo,
            purpose=row["purpose"],
            architecture_note=row["architecture_note"],
            tech_stack=TechStack.of(json.loads(row["tech_stack"])),
            snapshot=self._load_snapshot(project_id),
            todos=self._load_todos(project_id),
            notes=self._load_notes(project_id),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _load_snapshot(self, project_id: ProjectId) -> ProjectSnapshot | None:
        row = self._db.query_one(
            "SELECT * FROM project_snapshots WHERE project_id = ?", (project_id.value,)
        )
        if row is None:
            return None
        return ProjectSnapshot(
            captured_at=datetime.fromisoformat(row["captured_at"]),
            branch=row["branch"],
            dirty=bool(row["dirty"]),
            readme_excerpt=row["readme_excerpt"],
            recent_commits=tuple(
                CommitRef(
                    sha=c["sha"],
                    subject=c["subject"],
                    authored_at=datetime.fromisoformat(c["authored_at"]),
                    author=c.get("author", ""),
                )
                for c in json.loads(row["recent_commits"])
            ),
            open_issues=tuple(
                IssueRef(**issue) for issue in json.loads(row["open_issues"])
            ),
            detected_stack=TechStack.of(json.loads(row["detected_stack"])),
            discovered_todos=tuple(json.loads(row["discovered_todos"])),
        )

    def _load_todos(self, project_id: ProjectId) -> list[TodoItem]:
        rows = self._db.query(
            "SELECT * FROM project_todos WHERE project_id = ? ORDER BY position",
            (project_id.value,),
        )
        return [
            TodoItem(id=r["id"], text=r["text"], source=r["source"], done=bool(r["done"]))
            for r in rows
        ]

    def _load_notes(self, project_id: ProjectId) -> list[Note]:
        rows = self._db.query(
            "SELECT * FROM project_notes WHERE project_id = ? ORDER BY created_at",
            (project_id.value,),
        )
        return [
            Note(id=r["id"], text=r["text"], created_at=datetime.fromisoformat(r["created_at"]))
            for r in rows
        ]
