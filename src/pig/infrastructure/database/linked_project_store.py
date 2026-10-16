"""Isolated SQLite schema for new live-linked Projects; no legacy upgrades."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

from pig.application.errors import ApplicationError
from pig.domain.linked_project import (
    LINKED_MODEL_VERSION, LINKED_SCHEMA_VERSION, Experience, FixedRevision,
    LinkedEntry, LinkedProject, Observation,
)


class LinkedProjectStore:
    def __init__(self, data_root: Path):
        self.root = Path(data_root).absolute() / "linked-projects"

    def database_path(self, project_id: str) -> Path:
        try:
            identifier = str(UUID(project_id))
        except ValueError as exc:
            raise ApplicationError("INVALID_PROJECT", "项目标识无效") from exc
        return self.root / identifier / "project.sqlite"

    @contextmanager
    def connect(self, project_id: str):
        path = self.database_path(project_id)
        # Metadata paths are application-owned; reject a substituted parent/link.
        for parent in (self.root, path.parent, path):
            if parent.is_symlink() or getattr(parent.lstat(), "st_file_attributes", 0) & 0x400:
                raise ApplicationError("UNSAFE_PROJECT", "项目存储路径不安全")
        if not path.is_file():
            raise ApplicationError("PROJECT_NOT_FOUND", "项目数据库不存在")
        db = sqlite3.connect(path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=5000")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version != LINKED_SCHEMA_VERSION:
                raise ApplicationError("UNSUPPORTED_PROJECT_SCHEMA", "旧项目不会自动迁移或重建")
            model = db.execute("SELECT model_version FROM project WHERE id=?", (project_id,)).fetchone()
            if model is None or model[0] != LINKED_MODEL_VERSION:
                raise ApplicationError("UNSUPPORTED_PROJECT_SCHEMA", "此项目不属于当前关联模式")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def event(db, kind: str, subject: str, now: str):
        db.execute("INSERT INTO event VALUES (?,?,?,?)", (str(uuid4()), kind, subject, now))

    def create(self, project_id: str, name: str, root: Path, now: str) -> LinkedProject:
        path = self.database_path(project_id)
        path.parent.mkdir(parents=True, exist_ok=False)
        db = sqlite3.connect(path)
        try:
            db.executescript("""
                PRAGMA foreign_keys=ON;
                CREATE TABLE project (
                    id TEXT PRIMARY KEY, model_version TEXT NOT NULL, name TEXT NOT NULL,
                    root_path TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE extra_link (
                    id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE,
                    is_dir INTEGER NOT NULL CHECK(is_dir IN (0,1)), created_at TEXT NOT NULL
                );
                CREATE TABLE observation (
                    file_key TEXT PRIMARY KEY, source_path TEXT NOT NULL, status TEXT NOT NULL,
                    size INTEGER, sha256 TEXT, observed_at TEXT NOT NULL
                );
                CREATE TABLE capture_operation (
                    id TEXT PRIMARY KEY, manifest_version INTEGER NOT NULL DEFAULT 1,
                    file_key TEXT NOT NULL, state TEXT NOT NULL
                      CHECK(state IN ('PREPARING','COMMITTED','FAILED','REVIEWED')),
                    object_key TEXT, started_at TEXT NOT NULL, finished_at TEXT
                );
                CREATE TABLE fixed_revision (
                    id TEXT PRIMARY KEY, file_key TEXT NOT NULL, source_path TEXT NOT NULL,
                    sha256 TEXT NOT NULL CHECK(length(sha256)=64), size INTEGER NOT NULL CHECK(size>=0),
                    object_key TEXT NOT NULL, captured_at TEXT NOT NULL,
                    operation_id TEXT NOT NULL UNIQUE REFERENCES capture_operation(id)
                );
                CREATE INDEX revision_file ON fixed_revision(file_key, captured_at);
                CREATE TABLE experience (
                    id TEXT PRIMARY KEY, revision_id TEXT NOT NULL REFERENCES fixed_revision(id),
                    body TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('DRAFT','CONFIRMED')),
                    author TEXT NOT NULL, created_at TEXT NOT NULL, confirmed_at TEXT,
                    CHECK((status='DRAFT' AND confirmed_at IS NULL) OR
                          (status='CONFIRMED' AND confirmed_at IS NOT NULL))
                );
                CREATE INDEX experience_revision ON experience(revision_id);
                CREATE TABLE event (
                    id TEXT PRIMARY KEY, type TEXT NOT NULL, subject_id TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                );
                PRAGMA user_version=1;
            """)
            db.execute("INSERT INTO project VALUES (?,?,?,?,?)",
                       (project_id, LINKED_MODEL_VERSION, name, str(root), now))
            self.event(db, "PROJECT_LINKED", project_id, now)
            db.commit()
        except BaseException:
            db.close()
            path.unlink(missing_ok=True)
            path.parent.rmdir()
            raise
        db.close()
        return LinkedProject(project_id, name, root, path)

    def get(self, project_id: str) -> LinkedProject:
        try:
            with self.connect(project_id) as db:
                row = db.execute("SELECT * FROM project WHERE id=?", (project_id,)).fetchone()
        except FileNotFoundError as exc:
            raise ApplicationError("PROJECT_NOT_FOUND", "项目数据库不存在") from exc
        return LinkedProject(row["id"], row["name"], Path(row["root_path"]), self.database_path(project_id))

    def projects(self) -> tuple[LinkedProject, ...]:
        if not self.root.exists():
            return ()
        values = []
        for path in self.root.iterdir():
            if path.is_symlink() or not path.is_dir():
                continue
            try:
                values.append(self.get(path.name))
            except (ApplicationError, sqlite3.DatabaseError):
                continue
        return tuple(sorted(values, key=lambda value: value.name.casefold()))

    def add_link(self, project_id: str, value: LinkedEntry, now: str):
        try:
            with self.connect(project_id) as db:
                db.execute("INSERT INTO extra_link VALUES (?,?,?,?)",
                           (value.key[6:].rstrip("/"), str(value.path), int(value.is_dir), now))
                self.event(db, "FILE_LINKED", value.key, now)
        except sqlite3.IntegrityError as exc:
            raise ApplicationError("ALREADY_LINKED", "文件已经关联") from exc

    def extra_links(self, project_id: str) -> tuple[LinkedEntry, ...]:
        with self.connect(project_id) as db:
            rows = db.execute("SELECT * FROM extra_link ORDER BY created_at").fetchall()
        return tuple(LinkedEntry("extra:" + row["id"] + ("/" if row["is_dir"] else ""),
                                 Path(row["path"]).name, Path(row["path"]), bool(row["is_dir"]))
                     for row in rows)

    def previous_observation(self, project_id: str, key: str):
        with self.connect(project_id) as db:
            return db.execute("SELECT * FROM observation WHERE file_key=?", (key,)).fetchone()

    def save_observation(self, project_id: str, path: Path, value: Observation):
        with self.connect(project_id) as db:
            old = db.execute("SELECT status,sha256 FROM observation WHERE file_key=?", (value.file_key,)).fetchone()
            db.execute("""INSERT INTO observation VALUES (?,?,?,?,?,?)
                ON CONFLICT(file_key) DO UPDATE SET source_path=excluded.source_path,
                status=excluded.status, size=excluded.size, sha256=excluded.sha256,
                observed_at=excluded.observed_at""",
                (value.file_key, str(path), value.status, value.size, value.sha256, value.observed_at))
            if old is None or (old["status"], old["sha256"]) != (value.status, value.sha256):
                self.event(db, "FILE_" + ("OBSERVED" if old is None else value.status),
                           value.file_key, value.observed_at)

    def record_open(self, project_id: str, key: str, now: str):
        with self.connect(project_id) as db:
            self.event(db, "FILE_OPENED", key, now)

    def begin_capture(self, project_id: str, operation_id: str, key: str, now: str):
        with self.connect(project_id) as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT id FROM capture_operation WHERE state='PREPARING' LIMIT 1").fetchone():
                raise ApplicationError("CAPTURE_RECOVERY_REQUIRED", "存在中断的固定版本操作，请先检查项目")
            db.execute("INSERT INTO capture_operation VALUES (?,1,?,'PREPARING',NULL,?,NULL)",
                       (operation_id, key, now))

    def commit_capture(self, project_id: str, operation_id: str, value: FixedRevision):
        with self.connect(project_id) as db:
            db.execute("INSERT INTO fixed_revision VALUES (?,?,?,?,?,?,?,?)",
                       (value.id, value.file_key, str(value.source_path), value.sha256, value.size,
                        value.object_key, value.captured_at, operation_id))
            db.execute("UPDATE capture_operation SET state='COMMITTED', object_key=?,finished_at=? WHERE id=?",
                       (value.object_key, value.captured_at, operation_id))
            self.event(db, "REVISION_FIXED", value.id, value.captured_at)

    def fail_capture(self, project_id: str, operation_id: str, object_key: str | None, now: str):
        with self.connect(project_id) as db:
            db.execute("UPDATE capture_operation SET state='FAILED',object_key=?,finished_at=? WHERE id=?",
                       (object_key, now, operation_id))
            self.event(db, "CAPTURE_FAILED", operation_id, now)

    @staticmethod
    def _revision(row) -> FixedRevision:
        return FixedRevision(row["id"], row["file_key"], Path(row["source_path"]), row["sha256"],
                             row["size"], row["object_key"], row["captured_at"])

    def revisions(self, project_id: str, key: str) -> tuple[FixedRevision, ...]:
        with self.connect(project_id) as db:
            rows = db.execute("SELECT * FROM fixed_revision WHERE file_key=? ORDER BY captured_at DESC", (key,)).fetchall()
        return tuple(self._revision(row) for row in rows)

    def revision(self, project_id: str, revision_id: str) -> FixedRevision:
        with self.connect(project_id) as db:
            row = db.execute("SELECT * FROM fixed_revision WHERE id=?", (revision_id,)).fetchone()
        if row is None:
            raise ApplicationError("REVISION_NOT_FOUND", "固定版本不存在")
        return self._revision(row)

    @staticmethod
    def _experience(row) -> Experience:
        return Experience(row["id"], row["revision_id"], row["body"], row["status"],
                          row["author"], row["created_at"], row["confirmed_at"])

    def draft(self, project_id: str, value: Experience):
        with self.connect(project_id) as db:
            db.execute("INSERT INTO experience VALUES (?,?,?,?,?,?,?)",
                       (value.id, value.revision_id, value.body, value.status, value.author,
                        value.created_at, value.confirmed_at))
            self.event(db, "EXPERIENCE_DRAFTED", value.id, value.created_at)

    def experience(self, project_id: str, experience_id: str) -> Experience:
        with self.connect(project_id) as db:
            row = db.execute("SELECT * FROM experience WHERE id=?", (experience_id,)).fetchone()
        if row is None:
            raise ApplicationError("EXPERIENCE_NOT_FOUND", "经验草稿不存在")
        return self._experience(row)

    def confirm(self, project_id: str, experience_id: str, now: str) -> Experience:
        with self.connect(project_id) as db:
            changed = db.execute("UPDATE experience SET status='CONFIRMED',confirmed_at=? WHERE id=? AND status='DRAFT'",
                                 (now, experience_id)).rowcount
            if changed != 1:
                raise ApplicationError("EXPERIENCE_ALREADY_CONFIRMED", "经验已经确认或不存在")
            self.event(db, "EXPERIENCE_CONFIRMED", experience_id, now)
        return self.experience(project_id, experience_id)

    def experiences(self, project_id: str, revision_id: str) -> tuple[Experience, ...]:
        with self.connect(project_id) as db:
            rows = db.execute("SELECT * FROM experience WHERE revision_id=? ORDER BY created_at", (revision_id,)).fetchall()
        return tuple(self._experience(row) for row in rows)

    def pending_captures(self, project_id: str) -> tuple[str, ...]:
        with self.connect(project_id) as db:
            rows = db.execute("SELECT id FROM capture_operation WHERE state='PREPARING'").fetchall()
        return tuple(row["id"] for row in rows)
